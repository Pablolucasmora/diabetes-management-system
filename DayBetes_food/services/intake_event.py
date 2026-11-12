"""Use cases of `intake_event` shared by more than one endpoint (code_conventions.md §1.2)."""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime, time

from DayBetes_food.database.queries import (
    confirm_intake_event,
    create_injection_for_event,
    create_intake_event,
    create_intake_plate,
    create_manual_intake,
    create_portion_detail,
    delete_intake_event,
    delete_portion_detail,
    ensure_default_plate,
    get_intake_event,
    get_intake_plate,
    get_meal_type_schedule,
    get_planned_intake_event,
    list_portions_by_event,
    scale_plate_portion_amounts,
    update_intake_event,
)
from DayBetes_food.domain.constants import IntakeEventState, MealType, PortionDestination, PortionOrigin
from DayBetes_food.domain.fridge import LeftoverPlan
from DayBetes_food.domain.intake_event import (
    INTAKE_EVENT_INGESTED_AMOUNT_MAX_G,
    IntakeEventCreate,
    IntakeEventRead,
    IntakeEventUpdate,
)
from DayBetes_food.domain.intake_plate import IntakePlateCreate, PlateEaten, auto_offset_minutes, eaten_fraction
from DayBetes_food.domain.manual_intake import ManualIntakeCreate, QuickAddRequest
from DayBetes_food.domain.meal_type_schedule import resolve_meal_type_for_time
from DayBetes_food.domain.portion_detail import (
    PortionDetailCreate,
    PortionDetailRead,
    calculate_macro_summary_metrics,
    portion_intake_amount,
)
from DayBetes_food.errors import ConflictError, NotFoundError, ValidationError
from DayBetes_food.services.fridge import return_to_fridge, store_plate_leftovers
from DayBetes_food.time_utils import APP_TIMEZONE, local_naive_to_utc_aware, local_now, to_local, utc_now


def _portions_by_plate(portions: list[PortionDetailRead]) -> dict[int, list[PortionDetailRead]]:
    by_plate: dict[int, list[PortionDetailRead]] = defaultdict(list)
    for portion in portions:
        by_plate[portion.plate_id].append(portion)
    return dict(by_plate)


def _plate_fractions(
    by_plate: dict[int, list[PortionDetailRead]], eaten: Sequence[PlateEaten]
) -> dict[int, float]:
    """What was eaten of each plate with ingredients (measurement §4.4). A plate the
    request leaves out was eaten whole; one that is not in the meal, or repeated, is
    a 422 (§7.9)."""
    eaten_by_plate: dict[int, PlateEaten] = {}
    for entry in eaten:
        if entry.plate_id not in by_plate or entry.plate_id in eaten_by_plate:
            raise ValidationError("eaten_plate_not_in_meal")
        eaten_by_plate[entry.plate_id] = entry
    return {
        plate_id: eaten_fraction(eaten_by_plate.get(plate_id), sum(portion_intake_amount(p) for p in plate_portions))
        for plate_id, plate_portions in by_plate.items()
    }


def plates_with_leftovers(
    connection, user_id: int, event_id: int, eaten: Sequence[PlateEaten]
) -> list[tuple[int, float, list[PortionDetailRead]]]:
    """The plates of a planned meal not eaten whole, as `(plate_id, fraction eaten,
    portions)`, in the meal's order: what the leftovers pop-up offers to save
    before confirming (frontend_conventions.md §7.14). It writes nothing.

    Raises:
        ValidationError: an eaten entry is out of range or not of this meal.
    """
    by_plate = _portions_by_plate(list_portions_by_event(connection, user_id, event_id))
    fractions = _plate_fractions(by_plate, eaten)
    return [
        (plate_id, fractions[plate_id], by_plate[plate_id])
        for plate_id in by_plate
        if fractions[plate_id] < 1.0
    ]


def confirm_planned_event(
    connection,
    user_id: int,
    event_id: int,
    *,
    eaten: Sequence[PlateEaten] = (),
    leftovers: Sequence[LeftoverPlan] = (),
) -> None:
    """Move a planned event to consumed (measurement_conventions.md §6.9.1).

    The single confirm path, used by the cart and by the rescue pop-up
    (frontend_conventions.md §9.6). It runs inside the caller's transaction
    and never commits: the caller opens `connection.transaction()`, which is
    what makes reading the portions and scaling them a single unit (finding
    46 of audit/audit_intake_event.md).

    `eaten` says how much of each plate was eaten (decision 2026-11-07, per
    plate): a plate left out was eaten whole. `leftovers` says what to do with
    what was left of a plate not eaten whole: it is stored, before the portions
    are scaled, into new containers (§4.8.5).

    Raises:
        ConflictError("intake_event_without_portions"): nothing to confirm.
        ConflictError: the event is no longer planned.
        NotFoundError: the event does not exist or is not the user's.
        ValidationError: total or fraction out of range, or a plate that is not
            of this meal or has nothing left.
    """
    portions = list_portions_by_event(connection, user_id, event_id)
    if not portions:
        # Rule that depends on the database state (§7.10): an event
        # without portions cannot be confirmed; a disallowed state
        # transition → conflict (error_conventions.md §3.6). Finding 34
        # of audit/audit_intake_event.md, decision 2026-09-10.
        raise ConflictError("intake_event_without_portions")
    total_amount = sum(portion_intake_amount(p) for p in portions)
    if not math.isfinite(total_amount) or total_amount > INTAKE_EVENT_INGESTED_AMOUNT_MAX_G:
        # Defense in depth: total_amount is computed live from
        # portion_detail (outside this table's scope), but an
        # ingested_amount derived from it must still respect this
        # table's sanity limit (§6.9.2, finding 32/35).
        raise ValidationError("total_amount_out_of_range")

    by_plate = _portions_by_plate(portions)
    fractions = _plate_fractions(by_plate, eaten)
    plans: dict[int, LeftoverPlan] = {}
    for plan in leftovers:
        if fractions.get(plan.plate_id, 1.0) >= 1.0 or plan.plate_id in plans:
            raise ValidationError("leftover_plate_without_leftovers")
        plans[plan.plate_id] = plan

    # amount_confidence is a proportion of the eaten amounts: with a different
    # fraction per plate, scaling changes it, so it is computed on the portions
    # as they will be stored (§6.9.1, decision 2026-11-07). quality_confidence
    # and *_coverage are not stored: they are computed live (§6.9.4).
    eaten_portions = [replace(p, amount=p.amount * fractions[p.plate_id]) for p in portions]
    update_payload = IntakeEventUpdate(
        ingested_amount=sum(portion_intake_amount(p) for p in eaten_portions),
        amount_confidence=calculate_macro_summary_metrics(eaten_portions)["amount_confidence"],
    )

    # Ownership + idempotency in a single statement (§6.6).
    confirm_intake_event(connection, user_id=user_id, event_id=event_id, commit=False)
    for plate_id, plate_portions in by_plate.items():
        if plate_id in plans:
            store_plate_leftovers(connection, user_id, plate_portions, fractions[plate_id], plans[plate_id])
        if fractions[plate_id] < 1.0:
            # amount = amount * fraction for the whole plate, in one statement (§6.9.1).
            scale_plate_portion_amounts(connection, user_id, plate_id, fractions[plate_id], commit=False)
    update_intake_event(connection, user_id=user_id, event_id=event_id, data=update_payload, commit=False)
    # Automatic injection: returns an id or None (event without insulin).
    create_injection_for_event(connection, user_id=user_id, intake_event_id=event_id, commit=False)


def delete_planned_event(connection, user_id: int, event_id: int) -> None:
    """Delete a planned meal (decision 2026-09-08), giving back to their containers
    what was taken from them (measurement §4.8.6). Runs inside the caller's
    transaction, like `confirm_planned_event`.

    Raises:
        NotFoundError: it does not exist or is not the user's.
        ConflictError: it is no longer planned.
    """
    get_planned_intake_event(connection, user_id, event_id)
    return_to_fridge(connection, user_id, list_portions_by_event(connection, user_id, event_id))
    delete_intake_event(connection, user_id=user_id, event_id=event_id, commit=False)


def delete_planned_portion(connection, user_id: int, portion: PortionDetailRead) -> None:
    """Delete an ingredient of a planned meal, already resolved by the caller, giving
    it back to its container if it came from one (measurement §4.8.6). Runs inside
    the caller's transaction."""
    return_to_fridge(connection, user_id, [portion])
    delete_portion_detail(connection, user_id, portion.id, commit=False)


# Edits of a planned meal shared by the cart and the assistant (code_conventions.md §8.12).


def portion_event_id(connection, user_id: int, portion: PortionDetailRead, *, require_planned: bool = True) -> int:
    """Resolve a portion to its event, checking ownership and state (§5.3, §6.9.3).

    Portion actions travel by `portion_id`, so the event never comes from the
    request: it is derived from the portion, whose ownership `get_portion_detail`
    already validated inside the SQL.

    `require_planned=False` for the actions valid on a consumed event
    (measurement_conventions.md §6.9.3).

    Raises:
        NotFoundError: the portion does not belong to an event (recipe/fridge).
        NotFoundError/ConflictError: from the event, as `get_planned_intake_event` decides.
    """
    if portion.destination is not PortionDestination.INTAKE_EVENT:
        raise NotFoundError("portion_not_in_event")
    if require_planned:
        get_planned_intake_event(connection, user_id, portion.destination_id)
    elif not get_intake_event(connection, user_id, portion.destination_id):
        raise NotFoundError("intake_event_not_found")
    return portion.destination_id


def plate_event_id(connection, user_id: int, plate_id: int, *, require_planned: bool = True) -> int:
    """Resolve a plate to its event, checking ownership in the SQL (§5.3).

    Plate actions travel by `plate_id`, so the event never comes from the
    request: it is derived from the plate, which `get_intake_plate` validates
    against the user who owns the event.

    `require_planned=False` for the actions that are also valid on an already
    consumed event (measurement_conventions.md §6.9.3).

    Raises:
        NotFoundError: the plate does not exist or is not the user's.
        ConflictError: 'planned' was required and the event is already confirmed.
    """
    plate = get_intake_plate(connection, user_id, plate_id)
    if require_planned:
        get_planned_intake_event(connection, user_id, plate.intake_event_id)
    return plate.intake_event_id


def update_meal_time(
    connection, user_id: int, event_id: int, local_time: time, local_date: date | None, *, commit: bool = True
) -> None:
    """Move a planned meal to a local time and, optionally, date; without a date it
    keeps its own day (code_conventions.md §10.4).

    Raises:
        NotFoundError: the meal does not exist or is not the user's.
        ConflictError: it is no longer planned.
        ValidationError: the resulting time is not valid.
    """
    event = get_intake_event(connection, user_id, event_id)
    if not event or not event.meal_time:
        raise NotFoundError("intake_event_not_found")
    chosen_date = local_date or to_local(event.meal_time).date()
    update_intake_event(
        connection,
        user_id=user_id,
        event_id=event_id,
        data=IntakeEventUpdate(
            meal_time=local_naive_to_utc_aware(datetime.combine(chosen_date, local_time)),
            timezone_at_event=APP_TIMEZONE.key,
        ),
        commit=commit,
    )


# Where a food added to the cart goes (measurement_conventions.md §4.6.1, §7.7).
# Shared by the adds of Food and by the assistant (code_conventions.md §8.12).


def default_meal_type_now(connection, user_id: int) -> MealType | None:
    """Automatic `meal_type` for an `intake_event` created without going through
    the cart (adding a food directly), from the current local time and the
    user's time slots (or the defaults if they have not customized them in
    /settings/meal_type_schedule).

    It is computed when the row is created, and not in the component that
    shows it: the `<select>` in `EventHeader` (cart_components.py) must be able
    to trust that `event.meal_type` already is the real value, never one it has
    to infer at render time (code_conventions.md §7.14, decision 2026-09-11).
    """
    overrides = get_meal_type_schedule(connection, user_id)
    return resolve_meal_type_for_time(local_now().time(), overrides)


def new_plate_offset_minutes(event: IntakeEventRead | None) -> int | None:
    """Offset of a new plate (measurement_conventions.md §4.5, §4.6.2). From then
    on its portions inherit it, which avoids correcting them one by one."""
    return auto_offset_minutes(event.meal_time if event else None, utc_now())


def resolve_target_event(connection, user_id: int, chosen_event_id: int | None) -> tuple[int, bool]:
    """Planned event a food goes to, and whether it was created now: the chosen one
    (checked in SQL, NotFoundError or ConflictError otherwise) or, with no id, a new
    one with the automatic meal_type (§7.14). Runs inside the caller's transaction."""
    if chosen_event_id:
        return get_planned_intake_event(connection, user_id, chosen_event_id), False
    event_id = create_intake_event(
        connection,
        IntakeEventCreate(
            user_id=user_id,
            state=IntakeEventState.PLANNED,
            meal_type=default_meal_type_now(connection, user_id),
        ),
        commit=False,
    )
    return event_id, True


def resolve_event_plate(
    connection, user_id: int, event_id: int, plate_choice: int | None, offset_minutes: int | None
) -> int:
    """Plate a food added to an event goes to (§4.6.1, §7.7).

    - A specific id: that plate, checking inside the SQL that it belongs to
      the user and to the event (§5.3); the request's `event_id` is not proof.
    - `0`: the selector's `+ New plate` option, which creates the plate on the spot.
    - `None`: the event's last plate and, if there is none, a first one
      created implicitly.

    Raises:
        NotFoundError: the plate does not exist, is not the user's or belongs to another event.
    """
    if plate_choice:
        plate = get_intake_plate(connection, user_id, plate_choice)
        if plate.intake_event_id != int(event_id):
            raise NotFoundError(f"Intake plate {plate_choice} does not belong to event {event_id}")
        return plate.id
    if plate_choice == 0:
        return create_intake_plate(
            connection,
            IntakePlateCreate(intake_event_id=int(event_id), offset_minutes=offset_minutes),
            commit=False,
        )
    return ensure_default_plate(connection, int(event_id), offset_minutes=offset_minutes, commit=False)


def add_quick_add_to_meal(
    connection, user_id: int, request: QuickAddRequest, event_id: int, plate_choice: int | None
) -> int:
    """Create a quick add and its portion in a planned meal (code_conventions.md
    §11.2.3), inside the caller's transaction: row + portion, all or nothing (§2.3).

    A quick add stores only what its form asks: the weight becomes
    default_portion, its U1 and U2 (study §6.3) are the ones given, or NULL, and
    everything else stays NULL. The portion is born with the quick add's own U2
    (measurement §6.11). Repeating it creates another quick add (§9.6).

    Returns:
        The id of the new `manual_intake` row.
    """
    offset_minutes = new_plate_offset_minutes(get_intake_event(connection, user_id, event_id))
    plate_id = resolve_event_plate(connection, user_id, event_id, plate_choice, offset_minutes)
    manual_intake_id = create_manual_intake(
        connection,
        ManualIntakeCreate(
            created_by=user_id,
            origin_root_id=None,
            name=request.name,
            description=request.description,
            subtype=None,
            origin=None,
            default_portion=request.weight_g,
            nutrients=request.nutrients,
            glycemic_index=None,
            ig_confidence=None,
            macros_confidence=None,
            macros_source=request.macros_source,
            default_amount_method=request.amount_method,
            is_quick_add=True,
        ),
        commit=False,
    )
    create_portion_detail(
        connection,
        user_id,
        PortionDetailCreate(
            origin=PortionOrigin.MANUAL_INTAKE,
            origin_id=manual_intake_id,
            destination=PortionDestination.INTAKE_EVENT,
            destination_id=event_id,
            plate_id=plate_id,
            amount=request.weight_g,
            amount_method=request.amount_method,
        ),
        commit=False,
    )
    return manual_intake_id
