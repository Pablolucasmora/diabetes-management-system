"""Use cases of `intake_event` shared by more than one endpoint (code_conventions.md §1.2)."""

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace

from DayBetes_food.database.queries import (
    confirm_intake_event,
    create_injection_for_event,
    delete_intake_event,
    delete_portion_detail,
    get_planned_intake_event,
    list_portions_by_event,
    scale_plate_portion_amounts,
    update_intake_event,
)
from DayBetes_food.domain.fridge import LeftoverPlan
from DayBetes_food.domain.intake_event import INTAKE_EVENT_INGESTED_AMOUNT_MAX_G, IntakeEventUpdate
from DayBetes_food.domain.intake_plate import PlateEaten, eaten_fraction
from DayBetes_food.domain.portion_detail import (
    PortionDetailRead,
    calculate_macro_summary_metrics,
    portion_intake_amount,
)
from DayBetes_food.errors import ConflictError, ValidationError
from DayBetes_food.services.fridge import return_to_fridge, store_plate_leftovers


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
