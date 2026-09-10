from fasthtml.common import *
from DayBetes_food.components.cart.cart_main import cart_main
from DayBetes_food.components.cart.cart_components import MacrosSummary
from DayBetes_food.components.cart.cart_shared import calculate_macro_summary_metrics, portion_intake_amount
from DayBetes_food.components.ui import render_fragment, render_page
from datetime import datetime
from DayBetes_food.database.connection import get_connection
from DayBetes_food.time_utils import local_naive_to_utc_aware, local_today, to_local, APP_TIMEZONE
from DayBetes_food.database.queries import (
    consolidate_event_portion_group_amount,
    delete_event_portion_group,
    get_portion_detail_by_event,
    get_portion_detail_by_events,
    scale_event_portion_amounts,
    update_event_portion_group_field,
)
from DayBetes_food.database.queries.intake_event import (
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
    update_intake_event,
)
from DayBetes_food.domain.constants import InjectionZone, MealType
from DayBetes_food.domain.intake_event import INTAKE_EVENT_NAME_MAX_LENGTH, IntakeEventUpdate
from DayBetes_food.errors import ValidationError, NotFoundError, ConflictError
from DayBetes_food.auth.context import get_current_user_id


def _no_user_cart():
    return Div(H2("No users"), cls="flex flex-col items-center")


def _load_cart_main(connection):
    """
    Loads the planned events and their portions for the current user and
    renders cart_main with data already fetched (§1.4: components don't query).
    """
    user_id = get_current_user_id()
    if not user_id:
        return _no_user_cart()

    events = list_planned_intake_events(connection, int(user_id))
    event_ids = [event.id for event in events]
    all_portions = get_portion_detail_by_events(connection, event_ids)
    portions_by_event = {event_id: [] for event_id in event_ids}
    for portion in all_portions:
        portions_by_event.setdefault(portion["intake_event_id"], []).append(portion)

    return cart_main(events, portions_by_event)


def _cart_response(connection, status: int = 200):
    """
    Helper function to generate a consistent response for cart updates.
    """
    if status >= 400:
        return HTMLResponse("", status_code=status)
    return render_fragment(_load_cart_main(connection))


def _to_float(value: str):
    """
    Convert a string to a float, handling comma as decimal separator.
    """

    normalized = (value or "").strip().replace(",", ".")
    return float(normalized)


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
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        try:
            parsed_time = datetime.strptime(meal_hour, "%H:%M").time()
        except ValueError:
            # Valor presente y bien formado como petición, contenido inválido:
            # validation_error → 422 (error_conventions.md §3.2).
            return HTMLResponse(status_code=422)

        with get_connection() as connection:
            event = get_intake_event(connection, int(user_id), event_id)
            if not event or not event.meal_time:
                return HTMLResponse(status_code=404)
            current_local = to_local(event.meal_time)
            if meal_date:
                try:
                    chosen_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
                except ValueError:
                    # "fecha inválida" es validation_error → 422, no 400.
                    return HTMLResponse(status_code=422)
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
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return _cart_response(connection, status=200)

    @rt("/cart/event/{event_id}/meal_type")
    def post(request: Request, event_id: int, meal_type: str = ""):
        """
        Update meal_type from a specific event, returning the response to the request
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        clean_meal_type = (meal_type or "").strip()
        if not clean_meal_type:
            return HTMLResponse(status_code=422)
        try:
            parsed = MealType(clean_meal_type)
        except ValueError:
            return HTMLResponse(status_code=422)
        with get_connection() as connection:
            try:
                update_intake_event(
                    connection,
                    user_id=int(user_id),
                    event_id=event_id,
                    data=IntakeEventUpdate(meal_type=parsed),
                )
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return _cart_response(connection, status=200)

    @rt("/cart/event/{event_id}/name")
    def post(request: Request, event_id: int, event_name: str = ""):
        """
        Update event meal name, returning the response to the request
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        clean_name = (event_name or "").strip()
        if len(clean_name) > INTAKE_EVENT_NAME_MAX_LENGTH:
            # §7.3: no truncar silenciosamente; el exceso se rechaza como
            # validation_error (decisión 2026-09-09).
            return HTMLResponse(status_code=422)
        with get_connection() as connection:
            try:
                update_intake_event_name(
                    connection,
                    user_id=int(user_id),
                    event_id=event_id,
                    name=clean_name or None,
                )
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return _cart_response(connection, status=200)

    @rt("/cart/event/{event_id}/macros_summary")
    def get(request: Request, event_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        with get_connection() as connection:
            event = get_intake_event(connection, int(user_id), event_id)
            if not event:
                return HTMLResponse(status_code=404)
            portions = get_portion_detail_by_event(connection, event_id)
            return render_fragment(
                Div(
                    MacrosSummary(event, portions),
                    id=f"macros_summary_event_{event_id}",
                )
            )

    @rt("/cart/event/{event_id}/delete")
    def post(request: Request, event_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        with get_connection() as connection:
            try:
                delete_intake_event(connection, user_id=int(user_id), event_id=event_id)
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return _cart_response(connection, status=200)

    @rt("/cart/event/{event_id}/archive")
    def post(request: Request, event_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        with get_connection() as connection:
            try:
                archive_intake_event(connection, user_id=int(user_id), event_id=event_id)
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return _cart_response(connection, status=200)

    @rt("/cart/event/{event_id}/restore")
    def post(request: Request, event_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        with get_connection() as connection:
            try:
                restore_intake_event(connection, user_id=int(user_id), event_id=event_id)
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return _cart_response(connection, status=200)

    @rt("/cart/event/{event_id}/eating_out")
    def post(request: Request, event_id: int, eating_out: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        value = (eating_out or "").strip().lower() == "true"
        with get_connection() as connection:
            try:
                update_intake_event(
                    connection,
                    user_id=int(user_id),
                    event_id=event_id,
                    data=IntakeEventUpdate(eating_out=value),
                )
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return _cart_response(connection, status=200)

    @rt("/cart/event/{event_id}/insulin_dose")
    def post(request: Request, event_id: int, insulin_dose: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        value = (insulin_dose or "").strip().lower() == "true"
        with get_connection() as connection:
            try:
                update_intake_event(
                    connection,
                    user_id=int(user_id),
                    event_id=event_id,
                    data=IntakeEventUpdate(insulin_dose=value),
                )
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return _cart_response(connection, status=200)

    @rt("/cart/event/{event_id}/injection_zone")
    def post(request: Request, event_id: int, zone: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)

        # Parsear zona
        if not zone or not zone.strip():
            return HTMLResponse(status_code=422)
        try:
            parsed_zone = InjectionZone(zone.strip().lower())
        except ValueError:
            return HTMLResponse(status_code=422)

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
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return _cart_response(connection, status=200)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/amount")
    def post(request: Request, event_id: int, origin: str, origin_id: int, amount_g: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        try:
            amount = _to_float(amount_g)
        except (TypeError, ValueError):
            # Cantidad no numérica: validation_error → 422.
            return HTMLResponse(status_code=422)

        with get_connection() as connection:
            try:
                get_planned_intake_event(connection, int(user_id), event_id)
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            if amount <= 0:
                ok = delete_event_portion_group(connection, event_id, origin, origin_id)
            else:
                ok = consolidate_event_portion_group_amount(connection, event_id, origin, origin_id, amount)
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/offset")
    def post(request: Request, event_id: int, origin: str, origin_id: int, offset_minutes: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        try:
            value = int(offset_minutes)
        except (TypeError, ValueError):
            # Offset no entero: validation_error → 422.
            return HTMLResponse(status_code=422)
        with get_connection() as connection:
            try:
                get_planned_intake_event(connection, int(user_id), event_id)
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            ok = update_event_portion_group_field(connection, event_id, origin, origin_id, "offset_minutes", value)
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/strictly_weighed")
    def post(request: Request, event_id: int, origin: str, origin_id: int, strictly_weighed: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        value = (strictly_weighed or "").strip().lower() == "true"
        with get_connection() as connection:
            event = get_intake_event(connection, int(user_id), event_id)
            if not event:
                return HTMLResponse("", status_code=404)
            ok = update_event_portion_group_field(connection, event_id, origin, origin_id, "strictly_weighed", value)
            if not ok:
                return HTMLResponse("", status_code=400)
            portions = get_portion_detail_by_event(connection, event_id)
            return render_fragment(Div(MacrosSummary(event, portions), id=f"macros_summary_event_{event_id}"))

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/macros_quality")
    def post(request: Request, event_id: int, origin: str, origin_id: int, macros_quality: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        value = (macros_quality or "").strip().lower() == "true"
        with get_connection() as connection:
            event = get_intake_event(connection, int(user_id), event_id)
            if not event:
                return HTMLResponse("", status_code=404)
            ok = update_event_portion_group_field(connection, event_id, origin, origin_id, "macros_quality", value)
            if not ok:
                return HTMLResponse("", status_code=400)
            portions = get_portion_detail_by_event(connection, event_id)
            return render_fragment(Div(MacrosSummary(event, portions), id=f"macros_summary_event_{event_id}"))

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/is_cooked_weight")
    def post(request: Request, event_id: int, origin: str, origin_id: int, is_cooked_weight: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        value = (is_cooked_weight or "").strip().lower() == "true"
        with get_connection() as connection:
            event = get_intake_event(connection, int(user_id), event_id)
            if not event:
                return HTMLResponse("", status_code=404)
            ok = update_event_portion_group_field(connection, event_id, origin, origin_id, "is_cooked_weight", value)
            if not ok:
                return HTMLResponse("", status_code=400)
            portions = get_portion_detail_by_event(connection, event_id)
            return render_fragment(Div(MacrosSummary(event, portions), id=f"macros_summary_event_{event_id}"))

    @rt("/cart/event/{event_id}/confirm")
    def post(
        request: Request,
        event_id: int,
        ingested_value: str = "",
        ingested_unit: str = "g",
    ):
        """
        Confirma el evento (planned -> consumed). ingested_value/ingested_unit
        representan cuánto del plato servido se ha comido realmente:
        - vacío -> se asume el 100% (todo el plato).
        - ingested_unit == "%" -> fracción = ingested_value / 100.
        - ingested_unit == "g" -> fracción = ingested_value / total_amount
          (suma en vivo de plate_amount, calculada en este mismo request).
        fracción debe quedar en [0, 1]; fuera de rango es 422.
        Ver measurement_conventions.md §4.4/§6.9.1 (decisión 2026-09-10).
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)

        with get_connection() as connection:
            # 0) Autorizar antes de leer nada del evento (§5.3; cierra el hallazgo 19).
            try:
                get_planned_intake_event(connection, int(user_id), event_id)
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)

            portions = get_portion_detail_by_event(connection, event_id)
            total_amount = sum(portion_intake_amount(p) for p in portions)

            raw_value = (ingested_value or "").strip()
            if raw_value == "":
                fraction = 1.0
            else:
                try:
                    value = _to_float(raw_value)
                except (TypeError, ValueError):
                    # No numérico: validation_error → 422.
                    return HTMLResponse(status_code=422)
                if value < 0:
                    return HTMLResponse(status_code=422)
                if ingested_unit == "%":
                    fraction = value / 100.0
                else:
                    if total_amount <= 0:
                        # No hay nada que consumir: gramos > 0 no es interpretable.
                        return HTMLResponse(status_code=422)
                    fraction = value / total_amount
            if not (0.0 <= fraction <= 1.0):
                return HTMLResponse(status_code=422)

            # amount_confidence/quality_confidence/*_uncertainty son proporciones:
            # una escala uniforme de todas las porciones no las cambia, así que se
            # calculan sobre las porciones servidas, antes de escalarlas (§6.9.1).
            update_fields = calculate_macro_summary_metrics(portions)
            update_fields["ingested_amount"] = total_amount * fraction
            update_payload = IntakeEventUpdate(**update_fields)
            try:
                with connection.transaction():
                    # 1) Ownership + idempotencia en una sola sentencia (§6.6).
                    confirm_intake_event(
                        connection, user_id=int(user_id), event_id=event_id, commit=False
                    )
                    # 2) Sobrescribe plate_amount = plate_amount * fracción para todas
                    # las porciones del evento, en una sola sentencia SQL (§6.9.1).
                    scale_event_portion_amounts(
                        connection, event_id=event_id, fraction=fraction, commit=False
                    )
                    # 3) Resto de escrituras, ya dentro de la misma transacción.
                    update_intake_event(
                        connection, user_id=int(user_id), event_id=event_id, data=update_payload, commit=False
                    )
                    # 4) Inyección automática: devuelve id o None (evento sin insulina).
                    create_injection_for_event(
                        connection, user_id=int(user_id), intake_event_id=event_id, commit=False
                    )
            except NotFoundError:
                return HTMLResponse(status_code=404)
            except ConflictError:
                return HTMLResponse(status_code=409)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return _cart_response(connection, status=200)
