from fasthtml.common import *
from DayBetes_food.components.cart.cart_main import cart_main, cart_events_list
from DayBetes_food.components.cart.cart_components import CartCard, MacrosSummary
from DayBetes_food.components.cart.cart_shared import calculate_macro_summary_metrics, portion_intake_amount
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
from DayBetes_food.http_errors import app_error_headers
from DayBetes_food.errors import (
    AppError,
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
    """
    Respuesta de error del carrito: status semántico + aviso visible.

    Las acciones del carrito son ediciones en línea, no un formulario de
    guardado, así que **no** usan la excepción de `code_conventions.md` §9.5
    (`200` + fragmento dentro del formulario): conservan el status de su
    categoría (`422` validación, `404` inexistente, `409` conflicto, §3.2/§3.5/
    §3.6 de error_conventions.md) y devuelven cuerpo vacío, porque htmx no debe
    hacer swap de un error sobre la tarjeta.

    Para que el error no sea invisible —htmx ignora el cuerpo de un `4xx`, así
    que sin esto el usuario ve exactamente lo mismo que si no hubiera pulsado
    nada— la respuesta declara el mensaje público en cabeceras y, además, en el
    evento `appError` de `HX-Trigger`. `static/js/app_toast.js` lo pinta en el
    `#app_toast` del layout (decisión 2026-09-10, hallazgo 37 de
    audit/audit_intake_event.md; error_conventions.md §7: "no devolver un
    cuerpo vacío para un error que el usuario necesita ver").

    `error` puede ser una clase de `DayBetes_food/errors.py` o una instancia; el
    código y el mensaje por defecto salen siempre del catálogo central, nunca se
    inventan por endpoint (error_conventions.md §8.3).

    Las cabeceras las construye `http_errors.app_error_headers`, el mismo punto
    que usa el middleware de `main.py`: incluye el `X-Request-ID` que §7 exige
    en toda respuesta de error —estas rutas **devuelven** el error en vez de
    levantarlo, así que no pasan por el boundary global que lo añadía
    (hallazgo 50)— y sanea el mensaje a latin-1, la codificación de cabecera de
    Starlette, para que un guion largo o unas comillas tipográficas no
    conviertan el `4xx` en un `500` (hallazgo 51).
    """
    if isinstance(error, type) and issubclass(error, AppError):
        error = error()
    return HTMLResponse(
        "",
        status_code=error.status_code,
        headers=app_error_headers(request, error, message),
    )


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
    # Las tandas de todos los eventos en una sola consulta, ya ordenadas por la
    # query (§4.6.1); aquí solo se reparten por evento, sin reordenar.
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
    Refresco de la página completa del carrito. Reservado para las acciones
    que no tienen un elemento de UI propio en el carrito (archive/restore,
    hallazgo n/a: no están enlazadas desde ninguna tarjeta hoy). Las acciones
    que sí se disparan desde el carrito usan un refresco local: la tarjeta
    (`_card_response`), la lista (`_events_list_response`) o, si el evento
    deja de estar planificado, `_removal_response` (decisión 2026-09-10,
    refresco local del carrito).
    """
    return render_fragment(_load_cart_main(connection))


def _events_list_response(connection, user_id: int):
    """
    Refresca solo #cart_events_list. Es el target de meal_hour, la única
    acción que puede reordenar la lista (orden `meal_time DESC`).
    """
    events, portions_by_event, plates_by_event = _load_events_and_portions(connection, user_id)
    return render_fragment(cart_events_list(events, portions_by_event, plates_by_event))


def _card_response(request: Request, connection, user_id: int, event_id: int):
    """
    Refresca solo #cart_card_event_{id}. Target por defecto para cualquier
    edición dentro de una tarjeta que no cambia si el evento sigue en
    'planned' ni su posición en la lista.
    """
    event = get_intake_event(connection, user_id, event_id)
    if not event:
        return _error(request, NotFoundError, "Esta comida ya no existe.")
    portions = list_portions_by_event(connection, user_id, event_id)
    plates = list_intake_plates(connection, event_id)
    return render_fragment(CartCard(event, portions, plates))


def _portion_event_id(connection, user_id: int, portion, *, require_planned: bool = True) -> int:
    """Resuelve la porción a su evento comprobando propiedad y estado (§5.3, §6.9.3).

    Las rutas de porción viajan por `portion_id`, así que el evento nunca viene
    de la URL: se deriva de la porción, cuyo ownership ya validó
    `get_portion_detail` dentro del SQL.

    `require_planned=False` para las acciones válidas sobre un evento consumido
    (measurement_conventions.md §6.9.3).

    Raises:
        NotFoundError: la porción no es de un evento (receta/nevera).
        NotFoundError/ConflictError: del evento, según `get_planned_intake_event`.
    """
    if portion.destination is not PortionDestination.INTAKE_EVENT:
        raise NotFoundError("portion_not_in_event")
    if require_planned:
        get_planned_intake_event(connection, user_id, portion.destination_id)
    elif not get_intake_event(connection, user_id, portion.destination_id):
        raise NotFoundError("intake_event_not_found")
    return portion.destination_id


def _plate_event_id(connection, user_id: int, plate_id: int, *, require_planned: bool = True) -> int:
    """Resuelve la tanda a su evento comprobando la propiedad en el SQL (§5.3).

    Las rutas de ingrediente viajan por `plate_id`, así que el evento nunca
    viene de la URL: se deriva de la tanda, que `get_intake_plate` valida
    contra el usuario dueño del evento.

    `require_planned=False` para las acciones que también son válidas sobre un
    evento ya consumido (measurement_conventions.md §6.9.3).

    Raises:
        NotFoundError: la tanda no existe o no es del usuario.
        ConflictError: se exigía 'planned' y el evento ya está confirmado.
    """
    plate = get_intake_plate(connection, user_id, plate_id)
    if require_planned:
        get_planned_intake_event(connection, user_id, plate.intake_event_id)
    return plate.intake_event_id


def _removal_response(connection, user_id: int):
    """
    El evento ya salió de 'planned' (borrado o confirmado): su tarjeta se
    elimina devolviendo cuerpo vacío sobre el mismo target
    (#cart_card_event_{id}, outerHTML → nodo eliminado). Si no queda ningún
    evento planificado, se añade un swap OOB de #cart_body con el estado
    "carrito vacío", sin recargar el resto de la página (decisión
    2026-09-10, refresco local del carrito).
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
    """Valida un offset en minutos en el boundary (§7.5).

    Entero y dentro de la cota de cordura de measurement_conventions.md §4.5
    (`-300..300`), la misma que declara el CHECK de `intake_plate`: escribir
    fuera de rango daría un error de base de datos en vez de un 422.

    Raises:
        ValidationError: no es entero o se sale del rango.
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
    Parser estricto para los booleanos de transporte HTML de esta ruta
    (checkboxes con `value="true"`): campo ausente o vacío -> `False` (así es
    como un checkbox sin marcar llega, el formulario no envía el campo);
    `"true"` -> `True`; cualquier otro valor presente es una entrada inválida
    y se rechaza en vez de convertirse en `False` en silencio (§7.6,
    decisión 2026-09-10; hallazgo 31 de audit/audit_intake_event.md).
    """
    normalized = (raw_value or "").strip().lower()
    if normalized == "":
        return False
    if normalized == "true":
        return True
    raise ValidationError("boolean_not_recognized")


def _parse_ingested_unit(raw_value: str) -> AmountInputUnit:
    """
    Parser estricto de la unidad de la cantidad ingerida del `/confirm`.

    Mismo criterio que `_parse_strict_bool` (§7.6/§7.7): el conjunto es
    cerrado y vive en `domain/` (`AmountInputUnit`, restringido para este
    boundary por `INTAKE_EVENT_INGESTED_UNITS`); cualquier otro valor
    —incluido el vacío— se rechaza con `422` en vez de degradarse al `else`
    de gramos. Sin esto, `ingested_unit=kg` con `ingested_value=0.05`
    confirmaba la comida como 0,05 g y sobrescribía `plate_amount`, que es un
    dato clínico irrecuperable (hallazgo 47 de audit/audit_intake_event.md).
    """
    normalized = (raw_value or "").strip()
    try:
        unit = AmountInputUnit(normalized)
    except ValueError as exc:
        raise ValidationError("ingested_unit_not_recognized") from exc
    if unit not in INTAKE_EVENT_INGESTED_UNITS:
        raise ValidationError("ingested_unit_not_accepted_here")
    return unit


def _resync_consumed_event_metrics(connection, user_id: int, event_id: int, portions) -> None:
    """
    Recalcula el snapshot de métricas de un evento ya `consumed`.

    `amount_confidence`, `quality_confidence` y los seis `*_uncertainty` se
    calculan una sola vez en `/confirm` a partir de las porciones del evento.
    Las porciones de un evento consumido **son editables** (decisión
    2026-09-10, hallazgo 48), así que toda escritura sobre ellas tiene que
    reescribir ese snapshot: si no, el evento queda con métricas que ya no
    corresponden a sus porciones.

    Las métricas son proporciones ponderadas por cantidad, así que se calculan
    sobre las porciones tal y como están guardadas (ya escaladas por la
    fracción consumida en el `confirm`, §6.9.1); una escala uniforme no las
    altera. `ingested_amount` no se toca aquí porque estos flags no cambian
    `plate_amount`; la ruta que llegue a cambiarlo deberá recalcularlo también.

    No hace nada si el evento sigue en `planned`: ahí el snapshot todavía no
    existe y lo escribe el `confirm`.
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
            # Valor presente y bien formado como petición, contenido inválido:
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
                    # "fecha inválida" es validation_error → 422, no 400.
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
            # §7.3: no truncar silenciosamente; el exceso se rechaza como
            # validation_error (decisión 2026-09-09).
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

        Mismo contrato que /name: se guarda al salir del campo, la cadena vacía
        borra la nota (§7.3) y el exceso de longitud se rechaza con 422 en vez
        de truncarse (hallazgo 44 de audit/audit_intake_event.md,
        decisión 2026-09-10).
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

        # Parsear zona
        if not zone or not zone.strip():
            return _error(request, ValidationError, "Elige una zona de inyección.")
        try:
            parsed_zone = InjectionZone(zone.strip().lower())
        except ValueError:
            return _error(request, ValidationError, "Esa zona de inyección no existe.")

        # Registrar zona
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
    def post(request: Request, portion_id: int, amount_g: str = ""):
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        try:
            amount = _to_float(amount_g)
        except (TypeError, ValueError):
            # Cantidad no numérica: validation_error → 422.
            return _error(request, ValidationError, "La cantidad no es un número válido.")

        with get_connection() as connection:
            try:
                portion = get_portion_detail(connection, int(user_id), portion_id)
                event_id = _portion_event_id(connection, int(user_id), portion)
                with connection.transaction():
                    # update_portion_amount valida finitud, > 0 y cota superior
                    # (T2.7): una cantidad 0 o inválida es 422 y no borra nada
                    # (T0.7: el borrado tiene ruta propia).
                    update_portion_amount(connection, int(user_id), portion_id, amount, commit=False)
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
        """Mueve una porción a otra tanda del mismo evento, o a una nueva.

        `target_plate_id` vacío o "0" es la opción `+ New plate` del selector
        (frontend_conventions.md §7.5): la tanda se crea en el acto, hereda el
        offset de la porción de origen y la recibe.
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

    def _portion_flag_route(request: Request, portion_id: int, field_name: str, raw_value: str, label: str):
        """
        Cuerpo común de los tres booleanos de porción (strictly_weighed,
        macros_quality, is_cooked_weight): mismo contrato HTMX
        (target #macros_summary_event_{id}, swap outerHTML) y mismo mapeo de
        errores, como exige §9.5 ("las acciones equivalentes deben usar el
        mismo patrón").

        A diferencia de sus rutas hermanas de cantidad/offset, acepta también un
        evento `consumed`: las porciones de un evento confirmado son editables
        (decisión 2026-09-10, hallazgo 48). La contrapartida es que el snapshot
        de métricas del evento, calculado en el `confirm`, deja de
        corresponder a sus porciones, así que se recalcula y se reescribe en la
        misma transacción que el flag.
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        try:
            value = _parse_strict_bool(raw_value)
        except ValidationError:
            return _error(request, ValidationError, f"No se ha entendido la casilla '{label}'.")
        with get_connection() as connection:
            try:
                # require_planned=False: un evento consumido sigue siendo
                # editable en estos tres campos (decisión 2026-09-10).
                portion = get_portion_detail(connection, int(user_id), portion_id)
                event_id = _portion_event_id(connection, int(user_id), portion, require_planned=False)
            except NotFoundError:
                return _error(request, NotFoundError, _INGREDIENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, _EVENT_NOT_PLANNED)
            event = get_intake_event(connection, int(user_id), event_id)
            if not event:
                return _error(request, NotFoundError, _EVENT_GONE)
            is_consumed = event.state == IntakeEventState.CONSUMED
            try:
                # Escribir el flag y reescribir el snapshot son una sola
                # operación: si el recálculo falla, el flag tampoco se guarda
                # (§2.3, §6.5). Para un evento 'planned' no hay snapshot que
                # tocar todavía —lo escribe el confirm—, así que la
                # transacción envuelve solo la escritura del flag.
                with connection.transaction():
                    update_portion_flag(connection, int(user_id), portion_id, field_name, value, commit=False)
                    portions = list_portions_by_event(connection, int(user_id), event_id)
                    if is_consumed:
                        _resync_consumed_event_metrics(connection, int(user_id), event_id, portions)
            except NotFoundError:
                return _error(request, NotFoundError, _INGREDIENT_GONE)
            if is_consumed:
                # El fragmento debe mostrar el snapshot recién guardado, no el
                # que se leyó antes de recalcularlo.
                event = get_intake_event(connection, int(user_id), event_id)
                if not event:
                    return _error(request, NotFoundError, _EVENT_GONE)
            return render_fragment(Div(MacrosSummary(event, portions), id=f"macros_summary_event_{event_id}"))

    @rt("/cart/portion/{portion_id}/strictly_weighed")
    def post(request: Request, portion_id: int, strictly_weighed: str = ""):
        return _portion_flag_route(request, portion_id, "strictly_weighed", strictly_weighed, "Strictly weighted")

    @rt("/cart/portion/{portion_id}/macros_quality")
    def post(request: Request, portion_id: int, macros_quality: str = ""):
        return _portion_flag_route(request, portion_id, "macros_quality", macros_quality, "Macros quality")

    @rt("/cart/portion/{portion_id}/is_cooked_weight")
    def post(request: Request, portion_id: int, is_cooked_weight: str = ""):
        return _portion_flag_route(request, portion_id, "is_cooked_weight", is_cooked_weight, "Cooked weight")

    @rt("/cart/event/{event_id}/plate")
    def post(request: Request, event_id: int):
        """`+ Add plate`: crea una tanda vacía al final del evento.

        Nace sin nombre —lo derivará de sus ingredientes (§4.6.3)— y sin
        offset: lo hereda del que el usuario escriba en su cabecera antes de
        añadir nada, o queda en NULL si añade primero y lo ajusta después.
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
        """Nombre propio de la tanda. Vacío lo borra y vuelve al derivado (§4.6.3)."""
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        clean_name = (name or "").strip()
        if len(clean_name) > INTAKE_PLATE_NAME_MAX_LENGTH:
            # §7.3: el exceso se rechaza con 422, nunca se trunca.
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
        """Offset plantilla de la tanda.

        No reescribe sus porciones: eso es `Apply all` (§4.6.2). Solo cambia lo
        que heredarán los alimentos que se añadan después.
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
        """`Apply all`: fija el offset de la tanda y lo propaga a sus porciones.

        Mismo endpoint para el botón de la cabecera y para el de una fila
        (frontend_conventions.md §7.4): en los dos casos el valor enviado pasa a
        ser el de la tanda y el de todas sus filas.
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
        """Borra una tanda vacía. Con ingredientes dentro responde 409 (§4.6.5)."""
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)
        with get_connection() as connection:
            try:
                # require_planned=False para que el único ConflictError posible
                # sea el RESTRICT de una tanda con ingredientes, y no se
                # confunda con "el evento ya no está en el carrito".
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
        Confirma el evento (planned -> consumed). ingested_value/ingested_unit
        representan cuánto del plato servido se ha comido realmente:
        - vacío -> se asume el 100% (todo el plato).
        - ingested_unit == "%" -> fracción = ingested_value / 100.
        - ingested_unit == "g" -> fracción = ingested_value / total_amount
          (suma en vivo de plate_amount, calculada en este mismo request).
        No hay más unidades: cualquier otro valor es 422, nunca gramos por
        defecto (hallazgo 47).
        fracción debe quedar en [0, 1]; fuera de rango es 422.
        Ver measurement_conventions.md §4.4/§6.9.1 (decisión 2026-09-10).
        """
        if request.headers.get("HX-Request") != "true":
            return _error(request, AuthorizationError, _NOT_HTMX)
        user_id = get_current_user_id()
        if not user_id:
            return _error(request, AuthenticationError, _NO_SESSION)

        # 1) Validación del payload HTTP que no depende del estado de la base
        # (§7.1): se hace antes de abrir nada.
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
                # No numérico: validation_error → 422 (hallazgo 33: mismo
                # comportamiento aquí que en el resto de la ruta).
                return _error(request, ValidationError, "La cantidad ingerida no es un número válido.")
            # NaN/Infinity no deben guardarse: rechazo explícito (hallazgo 32),
            # no depender solo de que la comparación de fracción los descarte.
            if not math.isfinite(value) or value < 0:
                return _error(request, ValidationError, "La cantidad ingerida no es un número válido.")

        with get_connection() as connection:
            # 2) Autorizar antes de leer nada del evento (§5.3; cierra el hallazgo 19).
            try:
                get_planned_intake_event(connection, int(user_id), event_id)
            except NotFoundError:
                return _error(request, NotFoundError, _EVENT_GONE)
            except ConflictError:
                return _error(request, ConflictError, "Esta comida ya está confirmada.")

            try:
                # 3) Todo lo que depende del estado de la base ocurre dentro de
                # la misma transacción: leer las porciones fuera dejaba una
                # ventana en la que otra petición podía insertar una porción
                # que se escalaría sin haber contado en total_amount, así que
                # el ingested_amount guardado no correspondía a la suma real de
                # plate_amount (hallazgo 46, punto 11 de §13).
                with connection.transaction():
                    portions = list_portions_by_event(connection, int(user_id), event_id)
                    if not portions:
                        # Regla dependiente del estado de la base (§7.10): un evento sin
                        # porciones no puede confirmarse; transición de estado no
                        # permitida → conflict (error_conventions.md §3.6). Hallazgo 34
                        # de audit/audit_intake_event.md, decisión 2026-09-10.
                        raise ConflictError("intake_event_without_portions")
                    total_amount = sum(portion_intake_amount(p) for p in portions)
                    if not math.isfinite(total_amount) or total_amount > INTAKE_EVENT_INGESTED_AMOUNT_MAX_G:
                        # Defensa en profundidad: total_amount se calcula en vivo a partir
                        # de portion_detail (fuera del alcance de esta tabla), pero un
                        # ingested_amount derivado de él sigue teniendo que respetar el
                        # límite de cordura de esta tabla (§6.9.2, hallazgo 32/35).
                        raise ValidationError("total_amount_out_of_range")

                    if value is None:
                        fraction = 1.0
                    elif unit is AmountInputUnit.PERCENT:
                        fraction = value / 100.0
                    else:
                        # Única rama restante: gramos, ya validada arriba.
                        if total_amount <= 0:
                            # No hay nada que consumir: gramos > 0 no es interpretable.
                            raise ValidationError("total_amount_not_positive")
                        fraction = value / total_amount
                    if not (0.0 <= fraction <= 1.0):
                        raise ValidationError("fraction_out_of_range")

                    # amount_confidence/quality_confidence/*_uncertainty son proporciones:
                    # una escala uniforme de todas las porciones no las cambia, así que se
                    # calculan sobre las porciones servidas, antes de escalarlas (§6.9.1).
                    update_fields = calculate_macro_summary_metrics(portions)
                    update_fields["ingested_amount"] = total_amount * fraction
                    update_payload = IntakeEventUpdate(**update_fields)

                    # 4) Ownership + idempotencia en una sola sentencia (§6.6).
                    confirm_intake_event(
                        connection, user_id=int(user_id), event_id=event_id, commit=False
                    )
                    # 5) Sobrescribe plate_amount = plate_amount * fracción para todas
                    # las porciones del evento, en una sola sentencia SQL (§6.9.1).
                    scale_event_portion_amounts(
                        connection, int(user_id), event_id, fraction, commit=False
                    )
                    # 6) Resto de escrituras, ya dentro de la misma transacción.
                    update_intake_event(
                        connection, user_id=int(user_id), event_id=event_id, data=update_payload, commit=False
                    )
                    # 7) Inyección automática: devuelve id o None (evento sin insulina).
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
