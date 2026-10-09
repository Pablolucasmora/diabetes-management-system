from fasthtml.common import *
from DayBetes_food.components.cart.cart_main import cart_main, cart_events_list
from DayBetes_food.components.cart.cart_components import CartCard, MacrosSummary, PortionTriStateFlag
from DayBetes_food.components.cart.cart_shared import (
    calculate_macro_summary_metrics,
    portion_intake_amount,
    portion_name,
)
from DayBetes_food.components.ui import render_fragment, render_page
from datetime import datetime
import math
from DayBetes_food.database.connection import get_connection
from DayBetes_food.time_utils import local_naive_to_utc_aware, local_today, to_local, APP_TIMEZONE
from DayBetes_food.database.queries import (
    delete_portion_detail,
    get_portion_detail,
    list_portions_by_event,
    list_portions_by_events,
    move_portion_to_plate,
    scale_event_portion_amounts,
    update_portion_amount,
    update_portion_flag,
    update_portion_offset,
    apply_plate_offset_to_portions,
    create_intake_plate,
    delete_intake_plate,
    get_intake_plate,
    list_intake_plates,
    list_intake_plates_by_events,
    update_intake_plate,
    update_intake_plate_name,
    set_injection_zone,
    create_injection_for_event,
    confirm_intake_event,
    delete_intake_event,
    archive_intake_event,
    restore_intake_event,
    get_intake_event,
    get_planned_intake_event,
    list_planned_intake_events,
    update_intake_event_name,
    update_intake_event_notes,
    update_intake_event,
)
from DayBetes_food.domain.constants import (
    AmountInputUnit,
    InjectionZone,
    IntakeEventState,
    MealType,
    PortionDestination,
    PortionOrigin,
)
from DayBetes_food.domain.intake_event import (
    INTAKE_EVENT_INGESTED_AMOUNT_MAX_G,
    INTAKE_EVENT_INGESTED_UNITS,
    INTAKE_EVENT_NAME_MAX_LENGTH,
    INTAKE_EVENT_NOTES_MAX_LENGTH,
    IntakeEventUpdate,
)
from DayBetes_food.domain.intake_plate import (
    INTAKE_PLATE_NAME_MAX_LENGTH,
    INTAKE_PLATE_OFFSET_MAX_MINUTES,
    INTAKE_PLATE_OFFSET_MIN_MINUTES,
    IntakePlateCreate,
    IntakePlateUpdate,
)
from DayBetes_food.domain.portion_detail import amount_to_grams
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    MalformedRequestError,
    NotFoundError,
    ValidationError,
)
from DayBetes_food.auth.context import get_current_user_id


def _no_user_cart():
    return Div(H2("No users"), cls="flex flex-col items-center")


def _error(request: Request, error, message: str = ""):
    """Alias de `http_errors.app_error_response` (helper compartido, §7.1)."""
    return app_error_response(request, error, message)


def _load_events_and_portions(connection, user_id: int):
    """
    Loads the planned events and their portions for a user (§1.4: components
    don't query). Shared by the full-cart render and the local #cart_events_list
    refresh so both stay in sync with a single query pattern.
    """
    events = list_planned_intake_events(connection, user_id)
    event_ids = [event.id for event in events]
    all_portions = list_portions_by_events(connection, user_id, event_ids)
    portions_by_event = {event_id: [] for event_id in event_ids}
    for portion in all_portions:
        portions_by_event.setdefault(portion.destination_id, []).append(portion)
    # The plates of every event in a single query, already ordered by the
    # query (§4.6.1); here they are only distributed by event, never reordered.
    plates_by_event = {event_id: [] for event_id in event_ids}
    for plate in list_intake_plates_by_events(connection, event_ids):
        plates_by_event.setdefault(plate.intake_event_id, []).append(plate)
    return events, portions_by_event, plates_by_event


def _load_cart_main(connection):
    user_id = get_current_user_id()
    if not user_id:
        return _no_user_cart()
    events, portions_by_event, plates_by_event = _load_events_and_portions(connection, int(user_id))
    return cart_main(events, portions_by_event, plates_by_event)


def _cart_response(connection):
    """
    Full refresh of the cart page. Reserved for the actions that have no UI
    element of their own in the cart (archive/restore, finding n/a: no card
    links to them today). The actions triggered from the cart use a local
    refresh: the card (`_card_response`), the list (`_events_list_response`)
    or, if the event stops being planned, `_removal_response` (decision
    2026-09-10, local cart refresh).
    """
    return render_fragment(_load_cart_main(connection))


def _events_list_response(connection, user_id: int):
    """
    Refresh only #cart_events_list. It is the target of meal_hour, the only
    action that can reorder the list (order `meal_time DESC`).
    """
    events, portions_by_event, plates_by_event = _load_events_and_portions(connection, user_id)
    return render_fragment(cart_events_list(events, portions_by_event, plates_by_event))


def _card_response(request: Request, connection, user_id: int, event_id: int):
    """
    Refresh only #cart_card_event_{id}. Default target for any edit inside a
    card that changes neither whether the event is still 'planned' nor its
    position in the list.
    """
    event = get_intake_event(connection, user_id, event_id)
    if not event:
        return _error(request, NotFoundError, "Esta comida ya no existe.")
    portions = list_portions_by_event(connection, user_id, event_id)
    plates = list_intake_plates(connection, event_id)
    return render_fragment(CartCard(event, portions, plates))


def _portion_event_id(connection, user_id: int, portion, *, require_planned: bool = True) -> int:
    """Resolve a portion to its event, checking ownership and state (§5.3, §6.9.3).

    Portion routes travel by `portion_id`, so the event never comes from the
    URL: it is derived from the portion, whose ownership `get_portion_detail`
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


def _plate_event_id(connection, user_id: int, plate_id: int, *, require_planned: bool = True) -> int:
    """Resolve a plate to its event, checking ownership in the SQL (§5.3).

    Ingredient routes travel by `plate_id`, so the event never comes from the
    URL: it is derived from the plate, which `get_intake_plate` validates
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


def _removal_response(connection, user_id: int):
    """
    The event has left 'planned' (deleted or confirmed): its card is removed
    by returning an empty body on the same target (#cart_card_event_{id},
    outerHTML → node removed). If no planned event is left, an OOB swap of
    #cart_body with the "empty cart" state is added, without reloading the
    rest of the page (decision 2026-09-10, local cart refresh).
    """
    remaining = list_planned_intake_events(connection, user_id)
    if remaining:
        return render_fragment("")
    return render_fragment(cart_main([], {}, oob=True))


def _to_float(value: str):
    """
    Convert a string to a float, handling comma as decimal separator.
    """

    normalized = (value or "").strip().replace(",", ".")
    return float(normalized)


def _parse_offset_minutes(raw_value: str) -> int:
    """Validate an offset in minutes at the boundary (§7.5).

    An integer within the sanity bound of measurement_conventions.md §4.5
    (`-300..300`), the same one the `intake_plate` CHECK declares: writing
    out of range would give a database error instead of a 422.

    Raises:
        ValidationError: it is not an integer or is out of range.
    """
    try:
        value = int((raw_value or "").strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError("El offset debe ser un número entero de minutos.") from exc
    if not (INTAKE_PLATE_OFFSET_MIN_MINUTES <= value <= INTAKE_PLATE_OFFSET_MAX_MINUTES):
        raise ValidationError(
            f"El offset debe estar entre {INTAKE_PLATE_OFFSET_MIN_MINUTES} y "
            f"{INTAKE_PLATE_OFFSET_MAX_MINUTES} minutos."
        )
    return value


def _parse_strict_bool(raw_value: str) -> bool:
    """
    Strict parser for this route's HTML transport booleans (checkboxes with
    `value="true"`): missing or empty field -> `False` (that is how an
    unchecked checkbox arrives, the form does not send the field); `"true"`
    -> `True`; any other value present is invalid input and is rejected
    instead of silently becoming `False` (§7.6, decision 2026-09-10; finding
    31 of audit/audit_intake_event.md).
    """
    normalized = (raw_value or "").strip().lower()
    if normalized == "":
        return False
    if normalized == "true":
        return True
    raise ValidationError("boolean_not_recognized")


def _parse_tristate_bool(raw_value: str):
    """Strict parser of the `strictly_weighed` tri-state (§7.4/§7.6).

    Different from `_parse_strict_bool` on purpose: in a checkbox, absence is
    `False`, but in a three-state control, absence is "no data" (`None`).
    `"true"` -> `True`, `"false"` -> `False`, `""` -> `None`, anything else ->
    `422`. The client does not decide the transition: it sends the value the
    server computed when rendering (decision 2026-09-18).
    """
    normalized = (raw_value or "").strip().lower()
    if normalized == "":
        return None
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValidationError("tristate_not_recognized")


def _parse_ingested_unit(raw_value: str) -> AmountInputUnit:
    """
    Strict parser of the ingested amount unit of `/confirm`.

    Same criterion as `_parse_strict_bool` (§7.6/§7.7): the set is closed and
    lives in `domain/` (`AmountInputUnit`, restricted for this boundary by
    `INTAKE_EVENT_INGESTED_UNITS`); any other value —including empty— is
    rejected with `422` instead of degrading into the grams `else`. Without
    this, `ingested_unit=kg` with `ingested_value=0.05` confirmed the meal as
    0.05 g and overwrote `amount`, which is unrecoverable clinical data
    (finding 47 of audit/audit_intake_event.md).
    """
    normalized = (raw_value or "").strip()
    try:
        unit = AmountInputUnit(normalized)
    except ValueError as exc:
        raise ValidationError("ingested_unit_not_recognized") from exc
    if unit not in INTAKE_EVENT_INGESTED_UNITS:
        raise ValidationError("ingested_unit_not_accepted_here")
    return unit


def _parse_amount_unit(raw_value: str) -> AmountInputUnit:
    """Strict parser of the cart amount unit (§7.7).

    It accepts the members of `AmountInputUnit` (central enum, §11); `PERCENT`
    is not a mass and is not accepted on this route. Any other value,
    including empty, is a 422 instead of being interpreted as grams.
    """
    normalized = (raw_value or "").strip().lower()
    try:
        unit = AmountInputUnit(normalized)
    except ValueError as exc:
        raise ValidationError("amount_unit_not_recognized") from exc
    if unit is AmountInputUnit.PERCENT:
        raise ValidationError("amount_unit_not_admitted")
    return unit


def _resync_consumed_event_metrics(connection, user_id: int, event_id: int, portions) -> None:
    """
    Recompute the metrics snapshot of an already `consumed` event.

    `amount_confidence`, `quality_confidence` and the six `*_uncertainty` are
    computed once in `/confirm` from the event's portions. The portions of a
    consumed event **are editable** (decision 2026-09-10, finding 48), so
    every write on them has to rewrite that snapshot: otherwise the event is
    left with metrics that no longer match its portions.

    The metrics are amount-weighted proportions, so they are computed on the
    portions as stored (already scaled by the fraction consumed at
    `confirm`, §6.9.1); a uniform scale does not alter them.
    `ingested_amount` is not touched here because these flags do not change
    `amount`; any route that does change it must recompute it too.

    It does nothing if the event is still `planned`: the snapshot does not
    exist yet there, and `confirm` writes it.
    """
    update_intake_event(
        connection,
        user_id=user_id,
        event_id=event_id,
        data=IntakeEventUpdate(**calculate_macro_summary_metrics(portions)),
        commit=False,
    )


_NOT_HTMX = "Esta acción solo puede ejecutarse desde el carrito."
_NO_SESSION = "Tu sesión ha caducado. Vuelve a iniciar sesión."
_EVENT_GONE = "Esta comida ya no existe."
_EVENT_NOT_PLANNED = "Esta comida ya no está en el carrito."
_INGREDIENT_FAILED = "No se ha podido actualizar el ingrediente."
_INGREDIENT_GONE = "Este ingrediente ya no existe."
_INGREDIENT_AMOUNT_INVALID = (
    "La cantidad debe ser mayor que 0 y como máximo 100000 g. "
    "Para quitar el ingrediente usa el icono de borrar."
)
_PLATE_GONE = "Este plato ya no existe."
_PLATE_NOT_EMPTY = "Mueve o borra sus ingredientes antes de eliminar el plato."
_PLATE_FAILED = "No se ha podido actualizar el plato."


def setup_cart_routes(rt):
    @rt("/cart")
    def get(req):
        """
        Render cart page (cart_main), without the cart button (show_cart=False), when request to /cart
        """
        return render_page(req, _load_cart_main, show_cart=False)

    @rt("/cart/event/{event_id}/meal_hour")
    def post(request: Request, event_id: int, meal_hour: str = "", meal_date: str = ""):
        """
        Update meal_hour from a specific event, returning the response to the request
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        try:
            parsed_time = datetime.strptime(meal_hour, "%H:%M").time()
        except ValueError:
            # Value present and well formed as a request, invalid content:
            # validation_error → 422 (error_conventions.md §3.2).
            return _error(request, ValidationError, "La hora de la comida no es válida.")

        with get_connection() as connection:
            event = get_intake_event(connection, int(user_id), event_id)
            if not event or not event.meal_time:
                return _error(request, NotFoundError, _EVENT_GONE)
            current_local = to_local(event.meal_time)
            if meal_date:
                try:
                    chosen_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
                except ValueError:
                    # "invalid date" is validation_error → 422, not 400.
                    return _error(request, ValidationError, "La fecha de la comida no es válida.")
            else:
                chosen_date = current_local.date() if current_local else local_today()
            updated = local_naive_to_utc_aware(datetime.combine(chosen_date, parsed_time))
            try:
                update_intake_event(
                    connection,
                    user_id=int(user_id),
                    event_id=event_id,
                    data=IntakeEventUpdate(meal_time=updated, timezone_at_event=APP_TIMEZONE.key),
                )
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            except ValidationError:
                return _error(request, ValidationError, "La hora de la comida no es válida.")
            return _events_list_response(connection, int(user_id))

    @rt("/cart/event/{event_id}/meal_type")
    def post(request: Request, event_id: int, meal_type: str = ""):
        """
        Update meal_type from a specific event, returning the response to the request
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        clean_meal_type = (meal_type or "").strip()
        if not clean_meal_type:
            return _error(request, ValidationError, "Elige un tipo de comida.")
        try:
            parsed = MealType(clean_meal_type)
        except ValueError:
            return _error(request, ValidationError, "Ese tipo de comida no existe.")
        with get_connection() as connection:
            try:
                update_intake_event(
                    connection,
                    user_id=int(user_id),
                    event_id=event_id,
                    data=IntakeEventUpdate(meal_type=parsed),
                )
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            except ValidationError:
                return _error(request, ValidationError, "Ese tipo de comida no existe.")
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/event/{event_id}/name")
    def post(request: Request, event_id: int, event_name: str = ""):
        """
        Update event meal name, returning the response to the request
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        clean_name = (event_name or "").strip()
        if len(clean_name) > INTAKE_EVENT_NAME_MAX_LENGTH:
            # §7.3: never truncate silently; the excess is rejected as
            # validation_error (decision 2026-09-09).
            return _error(request, 
                ValidationError,
                f"El nombre no puede pasar de {INTAKE_EVENT_NAME_MAX_LENGTH} caracteres.",
            )
        with get_connection() as connection:
            try:
                update_intake_event_name(
                    connection,
                    user_id=int(user_id),
                    event_id=event_id,
                    name=clean_name or None,
                )
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            except ValidationError:
                return _error(request, ValidationError, "El nombre de la comida no es válido.")
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/event/{event_id}/notes")
    def post(request: Request, event_id: int, notes: str = ""):
        """
        Update the meal note, returning the refreshed card.

        Same contract as /name: it is saved when leaving the field, the empty
        string clears the note (§7.3) and excess length is rejected with 422
        instead of being truncated (finding 44 of audit/audit_intake_event.md,
        decision 2026-09-10).
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        clean_notes = (notes or "").strip()
        if len(clean_notes) > INTAKE_EVENT_NOTES_MAX_LENGTH:
            return _error(request, 
                ValidationError,
                f"La nota no puede pasar de {INTAKE_EVENT_NOTES_MAX_LENGTH} caracteres.",
            )
        with get_connection() as connection:
            try:
                update_intake_event_notes(
                    connection,
                    user_id=int(user_id),
                    event_id=event_id,
                    notes=clean_notes or None,
                )
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            except ValidationError:
                return _error(request, ValidationError, "La nota no es válida.")
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/event/{event_id}/delete")
    def post(request: Request, event_id: int):
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            try:
                delete_intake_event(connection, user_id=int(user_id), event_id=event_id)
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, 
                    ConflictError,
                    "Una comida ya confirmada no se borra: archívala en su lugar.",
                )
            except ValidationError:
                return _error(request, ValidationError)
            return _removal_response(connection, int(user_id))

    @rt("/cart/event/{event_id}/archive")
    def post(request: Request, event_id: int):
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            try:
                archive_intake_event(connection, user_id=int(user_id), event_id=event_id)
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, 
                    ConflictError,
                    "Solo se archivan las comidas ya confirmadas.",
                )
            except ValidationError:
                return _error(request, ValidationError)
            return _cart_response(connection)

    @rt("/cart/event/{event_id}/restore")
    def post(request: Request, event_id: int):
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            try:
                restore_intake_event(connection, user_id=int(user_id), event_id=event_id)
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, "Esta comida no está archivada.")
            except ValidationError:
                return _error(request, ValidationError)
            return _cart_response(connection)

    @rt("/cart/event/{event_id}/eating_out")
    def post(request: Request, event_id: int, eating_out: str = ""):
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        try:
            value = _parse_strict_bool(eating_out)
        except ValidationError:
            return _error(request, ValidationError, "No se ha entendido la casilla 'Eating out'.")
        with get_connection() as connection:
            try:
                update_intake_event(
                    connection,
                    user_id=int(user_id),
                    event_id=event_id,
                    data=IntakeEventUpdate(eating_out=value),
                )
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            except ValidationError:
                return _error(request, ValidationError, "No se ha entendido la casilla 'Eating out'.")
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/event/{event_id}/insulin_dose")
    def post(request: Request, event_id: int, insulin_dose: str = ""):
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        try:
            value = _parse_strict_bool(insulin_dose)
        except ValidationError:
            return _error(request, ValidationError, "No se ha entendido la casilla 'Insulin'.")
        with get_connection() as connection:
            try:
                update_intake_event(
                    connection,
                    user_id=int(user_id),
                    event_id=event_id,
                    data=IntakeEventUpdate(insulin_dose=value),
                )
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            except ValidationError:
                return _error(request, ValidationError, "No se ha entendido la casilla 'Insulin'.")
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/event/{event_id}/injection_zone")
    def post(request: Request, event_id: int, zone: str = ""):
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)

        # Parse the zone
        if not zone or not zone.strip():
            return _error(request, ValidationError, "Elige una zona de inyección.")
        try:
            parsed_zone = InjectionZone(zone.strip().lower())
        except ValueError:
            return _error(request, ValidationError, "Esa zona de inyección no existe.")

        # Record the zone
        with get_connection() as connection:
            try:
                set_injection_zone(
                    connection,
                    user_id=int(user_id),
                    intake_event_id=event_id,
                    zone=parsed_zone,
                )
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            except ValidationError:
                return _error(request, ValidationError, "Esa zona de inyección no existe.")
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/portion/{portion_id}/amount")
    def post(request: Request, portion_id: int, amount_value: str = "", amount_unit: str = AmountInputUnit.GRAMS.value):
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        try:
            unit = _parse_amount_unit(amount_unit)
        except ValidationError as error:
            return _error(request, ValidationError, str(error))
        try:
            value = _to_float(amount_value)
        except (TypeError, ValueError):
            # Non-numeric amount: validation_error → 422.
            return _error(request, ValidationError, "La cantidad no es un número válido.")

        with get_connection() as connection:
            try:
                portion = get_portion_detail(connection, int(user_id), portion_id)
                event_id = _portion_event_id(connection, int(user_id), portion)
                grams = amount_to_grams(value, unit, portion.source.unit_g)
                with connection.transaction():
                    # update_portion_amount validates finiteness, > 0 and the upper
                    # bound (T2.7): a 0 or invalid amount is a 422 and deletes
                    # nothing (T0.7: deletion has its own route).
                    update_portion_amount(connection, int(user_id), portion_id, grams, commit=False)
            except NotFoundError:
                return _error(request, NotFoundError, _INGREDIENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            except ValidationError:
                return _error(request, ValidationError, _INGREDIENT_AMOUNT_INVALID)
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/portion/{portion_id}/offset")
    def post(request: Request, portion_id: int, offset_minutes: str = ""):
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        try:
            value = _parse_offset_minutes(offset_minutes)
        except ValidationError as error:
            return _error(request, ValidationError, str(error))
        with get_connection() as connection:
            try:
                portion = get_portion_detail(connection, int(user_id), portion_id)
                event_id = _portion_event_id(connection, int(user_id), portion)
                with connection.transaction():
                    update_portion_offset(connection, int(user_id), portion_id, value, commit=False)
            except NotFoundError:
                return _error(request, NotFoundError, _INGREDIENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            except ValidationError as error:
                return _error(request, ValidationError, str(error))
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/portion/{portion_id}/delete")
    def post(request: Request, portion_id: int):
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            try:
                portion = get_portion_detail(connection, int(user_id), portion_id)
                event_id = _portion_event_id(connection, int(user_id), portion)
                with connection.transaction():
                    delete_portion_detail(connection, int(user_id), portion_id, commit=False)
            except NotFoundError:
                return _error(request, NotFoundError, _INGREDIENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/portion/{portion_id}/move")
    def post(request: Request, portion_id: int, target_plate_id: str = ""):
        """Move a portion to another plate of the same event, or to a new one.

        An empty or "0" `target_plate_id` is the selector's `+ New plate` option
        (frontend_conventions.md §7.5): the plate is created on the spot,
        inherits the offset of the source portion and receives it.
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)

        with get_connection() as connection:
            try:
                portion = get_portion_detail(connection, int(user_id), portion_id)
                event_id = _portion_event_id(connection, int(user_id), portion)
            except NotFoundError:
                return _error(request, NotFoundError, _INGREDIENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)

            raw_target = (target_plate_id or "").strip()
            try:
                with connection.transaction():
                    if raw_target.isdigit() and int(raw_target) != 0:
                        target_id = int(raw_target)
                    else:
                        target_id = create_intake_plate(
                            connection,
                            IntakePlateCreate(
                                intake_event_id=event_id,
                                offset_minutes=portion.offset_minutes,
                            ),
                            commit=False,
                        )
                    move_portion_to_plate(connection, int(user_id), portion_id, target_id, commit=False)
            except NotFoundError:
                return _error(request, NotFoundError, _PLATE_GONE)
            except ValidationError:
                return _error(request, ValidationError, _INGREDIENT_FAILED)
            return _card_response(request, connection, int(user_id), event_id)

    def _portion_flag_route(request: Request, portion_id: int, field_name: str, raw_value: str, label: str, *, tristate: bool = False):
        """
        Common body of the two portion booleans (strictly_weighed,
        is_cooked_weight; macros_quality is the food's since 2026-10-09,
        measurement §6.11): same HTMX contract
        (target #macros_summary_event_{id}, swap outerHTML) and same error
        mapping, as §9.5 requires ("equivalent actions must use the same
        pattern").

        `tristate=True` for strictly_weighed, which accepts "no data" (`None`,
        decision 2026-09-18); `is_cooked_weight` has two states.

        Unlike its sibling amount/offset routes, it also accepts a `consumed`
        event: the portions of a confirmed event are editable (decision
        2026-09-10, finding 48). The trade-off is that the event's metrics
        snapshot, computed at `confirm`, no longer matches its portions, so it
        is recomputed and rewritten in the same transaction as the flag.
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        try:
            value = _parse_tristate_bool(raw_value) if tristate else _parse_strict_bool(raw_value)
        except ValidationError:
            return _error(request, ValidationError, f"No se ha entendido la casilla '{label}'.")
        with get_connection() as connection:
            try:
                # require_planned=False: a consumed event stays editable in
                # these three fields (decision 2026-09-10).
                portion = get_portion_detail(connection, int(user_id), portion_id)
                event_id = _portion_event_id(connection, int(user_id), portion, require_planned=False)
            except NotFoundError:
                return _error(request, NotFoundError, _INGREDIENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            event = get_intake_event(connection, int(user_id), event_id)
            if not event:
                return _error(request, NotFoundError, _EVENT_GONE)
            # measurement_conventions.md §5.2: a manual dish has no cooking
            # factor, so its portions are never cooked-weighed. Unchecking is
            # still allowed.
            if (
                field_name == "is_cooked_weight"
                and value is True
                and portion.origin is PortionOrigin.MANUAL_INTAKE
            ):
                return _error(request, ValidationError, "Cooked weight only applies to catalog foods.")
            # Decision 2026-09-24 / R4: ticking the box on a catalog food with no
            # factor is rejected; unchecking is always allowed, and a portion that
            # already had it TRUE keeps the control to be unmarked.
            if (
                field_name == "is_cooked_weight"
                and value is True
                and portion.origin is PortionOrigin.CATALOG
                and portion.source.cooking_factor is None
                and not portion.is_cooked_weight
            ):
                return _error(
                    request,
                    ValidationError,
                    "This food has no cooking factor, so it cannot be weighed cooked.",
                )
            is_consumed = event.state == IntakeEventState.CONSUMED
            try:
                # Writing the flag and rewriting the snapshot are a single
                # operation: if the recompute fails, the flag is not saved
                # either (§2.3, §6.5). For a 'planned' event there is no
                # snapshot to touch yet —confirm writes it—, so the
                # transaction only wraps the flag write.
                with connection.transaction():
                    update_portion_flag(connection, int(user_id), portion_id, field_name, value, commit=False)
                    portions = list_portions_by_event(connection, int(user_id), event_id)
                    if is_consumed:
                        _resync_consumed_event_metrics(connection, int(user_id), event_id, portions)
            except NotFoundError:
                return _error(request, NotFoundError, _INGREDIENT_GONE)
            if field_name == "is_cooked_weight":
                # Part of the uniqueness key (4.6.4, decision 2026-09-23):
                # toggling it can merge the row into another one or change the
                # difference labels, so the whole card is repainted.
                return _card_response(request, connection, int(user_id), event_id)
            if is_consumed:
                # The fragment must show the snapshot just saved, not the one
                # read before recomputing it.
                event = get_intake_event(connection, int(user_id), event_id)
                if not event:
                    return _error(request, NotFoundError, _EVENT_GONE)
            summary = Div(MacrosSummary(event, portions), id=f"macros_summary_event_{event_id}")
            if not tristate:
                # A native checkbox already shows its own new state.
                return render_fragment(summary)
            # The tri-state control carries the next state in `hx_vals`, so it
            # must be repainted from the saved row, out of band next to the
            # summary (9.5 cart HTMX contract); otherwise it keeps sending the
            # same value and shows a state the row no longer has
            # (frontend_conventions.md 6).
            saved = next(p for p in portions if p.id == portion_id)
            return render_fragment(
                (summary, PortionTriStateFlag(event_id, saved, field_name, portion_name(saved), oob=True))
            )

    @rt("/cart/portion/{portion_id}/strictly_weighed")
    def post(request: Request, portion_id: int, value: str = ""):
        return _portion_flag_route(request, portion_id, "strictly_weighed", value, "Strictly weighted", tristate=True)

    @rt("/cart/portion/{portion_id}/is_cooked_weight")
    def post(request: Request, portion_id: int, is_cooked_weight: str = ""):
        return _portion_flag_route(request, portion_id, "is_cooked_weight", is_cooked_weight, "Cooked weight")

    @rt("/cart/event/{event_id}/plate")
    def post(request: Request, event_id: int):
        """`+ Add plate`: create an empty plate at the end of the event.

        It is born without a name —it will derive it from its ingredients
        (§4.6.3)— and without an offset: it inherits the one the user types in
        its header before adding anything, or stays NULL if they add first and
        adjust it afterwards.
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            try:
                get_planned_intake_event(connection, int(user_id), event_id)
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            create_intake_plate(connection, IntakePlateCreate(intake_event_id=event_id))
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/plate/{plate_id}/name")
    def post(request: Request, plate_id: int, name: str = ""):
        """Own name of the plate. Empty clears it and goes back to the derived one (§4.6.3)."""
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        clean_name = (name or "").strip()
        if len(clean_name) > INTAKE_PLATE_NAME_MAX_LENGTH:
            # §7.3: the excess is rejected with 422, never truncated.
            return _error(
                request,
                ValidationError,
                f"El nombre del plato no puede superar {INTAKE_PLATE_NAME_MAX_LENGTH} caracteres.",
            )
        with get_connection() as connection:
            try:
                event_id = _plate_event_id(connection, int(user_id), plate_id, require_planned=False)
                update_intake_plate_name(connection, plate_id, clean_name or None)
            except NotFoundError:
                return _error(request, NotFoundError, _PLATE_GONE)
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/plate/{plate_id}/offset")
    def post(request: Request, plate_id: int, offset_minutes: str = ""):
        """Template offset of the plate.

        It does not rewrite its portions: that is `Apply all` (§4.6.2). It only
        changes what the foods added afterwards will inherit.
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        try:
            value = _parse_offset_minutes(offset_minutes)
        except ValidationError as error:
            return _error(request, ValidationError, str(error))
        with get_connection() as connection:
            try:
                event_id = _plate_event_id(connection, int(user_id), plate_id, require_planned=False)
                update_intake_plate(connection, plate_id, IntakePlateUpdate(offset_minutes=value))
            except NotFoundError:
                return _error(request, NotFoundError, _PLATE_GONE)
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/plate/{plate_id}/apply_offset")
    def post(request: Request, plate_id: int, offset_minutes: str = ""):
        """`Apply all`: set the plate's offset and propagate it to its portions.

        Same endpoint for the header button and for a row's button
        (frontend_conventions.md §7.4): in both cases the value sent becomes the
        plate's and that of all its rows.
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        try:
            value = _parse_offset_minutes(offset_minutes)
        except ValidationError as error:
            return _error(request, ValidationError, str(error))
        with get_connection() as connection:
            try:
                event_id = _plate_event_id(connection, int(user_id), plate_id, require_planned=False)
            except NotFoundError:
                return _error(request, NotFoundError, _PLATE_GONE)
            if not apply_plate_offset_to_portions(connection, plate_id, value):
                return _error(request, MalformedRequestError, _PLATE_FAILED)
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/plate/{plate_id}/delete")
    def post(request: Request, plate_id: int):
        """Delete an empty plate. With ingredients inside it answers 409 (§4.6.5)."""
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            try:
                # require_planned=False so that the only possible ConflictError
                # is the RESTRICT of a plate with ingredients, and it is not
                # confused with "the event is no longer in the cart".
                event_id = _plate_event_id(connection, int(user_id), plate_id, require_planned=False)
                delete_intake_plate(connection, plate_id)
            except NotFoundError:
                return _error(request, NotFoundError, _PLATE_GONE)
            except ConflictError:
                return _error(request, ConflictError, _PLATE_NOT_EMPTY)
            return _card_response(request, connection, int(user_id), event_id)

    @rt("/cart/event/{event_id}/confirm")
    def post(
        request: Request,
        event_id: int,
        ingested_value: str = "",
        ingested_unit: str = AmountInputUnit.GRAMS.value,
    ):
        """
        Confirm the event (planned -> consumed). ingested_value/ingested_unit
        represent how much of the served plate was actually eaten:
        - empty -> 100% is assumed (the whole plate).
        - ingested_unit == "%" -> fraction = ingested_value / 100.
        - ingested_unit == "g" -> fraction = ingested_value / total_amount
          (live sum of amount, computed in this same request).
        There are no other units: any other value is a 422, never grams by
        default (finding 47).
        The fraction must end up in (0, 1] (decision 2026-09-22); out of range is a 422.
        See measurement_conventions.md §4.4/§6.9.1 (decision 2026-09-10).
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)

        # 1) Validation of the HTTP payload that does not depend on the database
        # state (§7.1): it happens before opening anything.
        try:
            unit = _parse_ingested_unit(ingested_unit)
        except ValidationError:
            return _error(request, ValidationError, "La unidad de la cantidad ingerida no es válida.")
        raw_value = (ingested_value or "").strip()
        value = None
        if raw_value != "":
            try:
                value = _to_float(raw_value)
            except (TypeError, ValueError):
                # Non-numeric: validation_error → 422 (finding 33: same
                # behaviour here as in the rest of the route).
                return _error(request, ValidationError, "La cantidad ingerida no es un número válido.")
            # NaN/Infinity must not be stored: explicit rejection (finding 32),
            # instead of relying only on the fraction comparison to discard them.
            if not math.isfinite(value) or value < 0:
                return _error(request, ValidationError, "La cantidad ingerida no es un número válido.")

        with get_connection() as connection:
            # 2) Authorize before reading anything from the event (§5.3; closes finding 19).
            try:
                get_planned_intake_event(connection, int(user_id), event_id)
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, "Esta comida ya está confirmada.")

            try:
                # 3) Everything that depends on the database state happens
                # inside the same transaction: reading the portions outside it
                # left a window in which another request could insert a
                # portion that would be scaled without having counted in
                # total_amount, so the stored ingested_amount did not match the
                # real sum of amount (finding 46, item 11 of §13).
                with connection.transaction():
                    portions = list_portions_by_event(connection, int(user_id), event_id)
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

                    if value is None:
                        fraction = 1.0
                    elif unit is AmountInputUnit.PERCENT:
                        fraction = value / 100.0
                    else:
                        # Única rama restante: gramos, ya validada arriba.
                        if total_amount <= 0:
                            # There is nothing to consume: grams > 0 cannot be interpreted.
                            raise ValidationError("total_amount_not_positive")
                        fraction = value / total_amount
                    # (0, 1] since decision 2026-09-22: eating nothing is not a
                    # confirm; an event nobody ate is deleted, not confirmed.
                    if not (0.0 < fraction <= 1.0):
                        raise ValidationError("fraction_out_of_range")

                    # amount_confidence/quality_confidence/*_uncertainty are proportions:
                    # a uniform scale of every portion does not change them, so they are
                    # computed on the served portions, before scaling them (§6.9.1).
                    update_fields = calculate_macro_summary_metrics(portions)
                    update_fields["ingested_amount"] = total_amount * fraction
                    update_payload = IntakeEventUpdate(**update_fields)

                    # 4) Ownership + idempotency in a single statement (§6.6).
                    confirm_intake_event(
                        connection, user_id=int(user_id), event_id=event_id, commit=False
                    )
                    # 5) Overwrite amount = amount * fraction for every portion
                    # of the event, in a single SQL statement (§6.9.1).
                    scale_event_portion_amounts(
                        connection, int(user_id), event_id, fraction, commit=False
                    )
                    # 6) The rest of the writes, already inside the same transaction.
                    update_intake_event(
                        connection, user_id=int(user_id), event_id=event_id, data=update_payload, commit=False
                    )
                    # 7) Automatic injection: returns an id or None (event without insulin).
                    create_injection_for_event(
                        connection, user_id=int(user_id), intake_event_id=event_id, commit=False
                    )
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError as error:
                if str(error) == "intake_event_without_portions":
                    return _error(request, 
                        ConflictError,
                        "No puedes confirmar una comida sin ingredientes.",
                    )
                return _error(request, ConflictError, "Esta comida ya está confirmada.")
            except ValidationError:
                return _error(request, ValidationError, "La cantidad ingerida no es válida.")
            return _removal_response(connection, int(user_id))
