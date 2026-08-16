from fasthtml.common import *
from DayBetes_food.components.cart.cart_main import cart_main
from DayBetes_food.components.cart.cart_components import MacrosSummary
from DayBetes_food.components.cart.cart_shared import calculate_macro_summary_metrics
from DayBetes_food.components.ui import render_fragment, render_page
from datetime import datetime
from DayBetes_food.database.connection import get_connection
from DayBetes_food.time_utils import local_naive_to_utc, utc_naive_to_local
from DayBetes_food.database.queries.crud import (
    change_event_status,
    consolidate_event_portion_group_amount,
    delete_event_portion_group,
    delete_intake_event,
    get_intake_event,
    finalize_injection_zone_for_event,
    get_portion_detail_by_event,
    set_injection_zone,
    update_event_portion_group_field,
    update_intake_event_name,
    update_intake_event,
)
from DayBetes_food.components.food.foods import MEAL_TYPES


def _cart_response(connection, status: int = 200):
    """
    Helper function to generate a consistent response for cart updates.
    """
    if status >= 400:
        return HTMLResponse("", status_code=status)
    return render_fragment(cart_main(connection))


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
        return render_page(req, cart_main, show_cart=False)

    @rt("/cart/event/{event_id}/meal_hour")
    def post(request: Request, event_id: int, meal_hour: str = "", meal_date: str = ""):
        """
        Update meal_hour from a specific event, returning the response to the request
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            parsed_time = datetime.strptime(meal_hour, "%H:%M").time()
        except ValueError:
            return HTMLResponse(status_code=400)

        with get_connection() as connection:
            event = get_intake_event(connection, event_id)
            if not event or not event.get("meal_time"):
                return HTMLResponse(status_code=404)
            current_local = utc_naive_to_local(event["meal_time"])
            if meal_date:
                try:
                    chosen_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
                except ValueError:
                    return HTMLResponse(status_code=400)
            else:
                chosen_date = current_local.date() if current_local else datetime.utcnow().date()
            updated = local_naive_to_utc(datetime.combine(chosen_date, parsed_time))
            ok = update_intake_event(connection, event_id, {"meal_time": updated})
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/meal_type")
    def post(request: Request, event_id: int, meal_type: str = ""):
        """
        Update meal_type from a specific event, returning the response to the request
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_meal_type = (meal_type or "").strip()
        if not clean_meal_type:
            return HTMLResponse(status_code=400)
        if clean_meal_type not in MEAL_TYPES:
            return HTMLResponse(status_code=400)
        with get_connection() as connection:
            ok = update_intake_event(connection, event_id, {"meal_type": clean_meal_type})
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/name")
    def post(request: Request, event_id: int, event_name: str = ""):
        """
        Update event meal name, returning the response to the request
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (event_name or "").strip()
        if len(clean_name) > 255:
            clean_name = clean_name[:255]
        with get_connection() as connection:
            ok = update_intake_event_name(connection, event_id, clean_name or None)
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/macros_summary")
    def get(request: Request, event_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            event = get_intake_event(connection, event_id)
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
        with get_connection() as connection:
            ok = delete_intake_event(connection, event_id)
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/eating_out")
    def post(request: Request, event_id: int, eating_out: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        value = (eating_out or "").strip().lower() == "true"
        with get_connection() as connection:
            ok = update_intake_event(connection, event_id, {"eating_out": value})
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/insulin_dose")
    def post(request: Request, event_id: int, insulin_dose: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        value = (insulin_dose or "").strip().lower() == "true"
        with get_connection() as connection:
            ok = update_intake_event(connection, event_id, {"insulin_dose": value})
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/injection_zone")
    def post(request: Request, event_id: int, zone: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            event = get_intake_event(connection, event_id)
            if not event:
                return HTMLResponse(status_code=404)
            if not event.get("insulin_dose"):
                return HTMLResponse(status_code=400)
            ok = set_injection_zone(connection, event_id, zone)
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/amount")
    def post(request: Request, event_id: int, origin: str, origin_id: int, amount_g: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            amount = _to_float(amount_g)
        except (TypeError, ValueError):
            return HTMLResponse(status_code=400)

        with get_connection() as connection:
            if amount <= 0:
                ok = delete_event_portion_group(connection, event_id, origin, origin_id)
            else:
                ok = consolidate_event_portion_group_amount(connection, event_id, origin, origin_id, amount)
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/offset")
    def post(request: Request, event_id: int, origin: str, origin_id: int, offset_minutes: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            value = int(offset_minutes)
        except (TypeError, ValueError):
            return HTMLResponse(status_code=400)
        with get_connection() as connection:
            ok = update_event_portion_group_field(connection, event_id, origin, origin_id, "offset_minutes", value)
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/strictly_weighed")
    def post(request: Request, event_id: int, origin: str, origin_id: int, strictly_weighed: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        value = (strictly_weighed or "").strip().lower() == "true"
        with get_connection() as connection:
            ok = update_event_portion_group_field(connection, event_id, origin, origin_id, "strictly_weighed", value)
            if not ok:
                return HTMLResponse("", status_code=400)
            event = get_intake_event(connection, event_id)
            if not event:
                return HTMLResponse("", status_code=404)
            portions = get_portion_detail_by_event(connection, event_id)
            return render_fragment(Div(MacrosSummary(event, portions), id=f"macros_summary_event_{event_id}"))

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/macros_quality")
    def post(request: Request, event_id: int, origin: str, origin_id: int, macros_quality: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        value = (macros_quality or "").strip().lower() == "true"
        with get_connection() as connection:
            ok = update_event_portion_group_field(connection, event_id, origin, origin_id, "macros_quality", value)
            if not ok:
                return HTMLResponse("", status_code=400)
            event = get_intake_event(connection, event_id)
            if not event:
                return HTMLResponse("", status_code=404)
            portions = get_portion_detail_by_event(connection, event_id)
            return render_fragment(Div(MacrosSummary(event, portions), id=f"macros_summary_event_{event_id}"))

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/is_cooked_weight")
    def post(request: Request, event_id: int, origin: str, origin_id: int, is_cooked_weight: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        value = (is_cooked_weight or "").strip().lower() == "true"
        with get_connection() as connection:
            ok = update_event_portion_group_field(connection, event_id, origin, origin_id, "is_cooked_weight", value)
            if not ok:
                return HTMLResponse("", status_code=400)
            event = get_intake_event(connection, event_id)
            if not event:
                return HTMLResponse("", status_code=404)
            portions = get_portion_detail_by_event(connection, event_id)
            return render_fragment(Div(MacrosSummary(event, portions), id=f"macros_summary_event_{event_id}"))

    @rt("/cart/event/{event_id}/confirm")
    def post(
        request: Request,
        event_id: int,
        ingested_value: str = "",
        ingested_unit: str = "g",
        total_amount: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        ingested_amount = None
        if (ingested_value or "").strip() != "":
            try:
                value = float(ingested_value)
            except (TypeError, ValueError):
                return HTMLResponse(status_code=400)
            if value < 0:
                return HTMLResponse(status_code=400)

            try:
                total = float(total_amount)
            except (TypeError, ValueError):
                total = None

            if ingested_unit == "%":
                if total is None:
                    return HTMLResponse(status_code=400)
                ingested_amount = (total * value) / 100.0
            else:
                ingested_amount = value

        with get_connection() as connection:
            portions = get_portion_detail_by_event(connection, event_id)
            update_payload = {}
            if ingested_amount is not None:
                update_payload["ingested_amount"] = ingested_amount
            if (total_amount or "").strip() != "":
                try:
                    update_payload["total_amount"] = float(total_amount)
                except (TypeError, ValueError):
                    pass
            update_payload.update(calculate_macro_summary_metrics(portions))
            try:
                with connection.transaction():
                    updated = (
                        update_intake_event(connection, event_id, update_payload, commit=False)
                        if update_payload
                        else True
                    )
                    if not updated:
                        raise ValueError("Could not update intake event")
                    finalized_zone = finalize_injection_zone_for_event(connection, event_id, commit=False)
                    if not finalized_zone:
                        raise ValueError("Could not finalize injection zone")
                    changed = change_event_status(connection, event_id, "consumed", commit=False)
                    if not changed:
                        raise ValueError("Could not change intake event status")
            except Exception:
                return _cart_response(connection, status=400)

            return _cart_response(connection, status=200 if (updated and finalized_zone and changed) else 400)
