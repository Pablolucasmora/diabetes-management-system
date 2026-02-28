from fasthtml.common import *
from DayBetes_food.components.cart.cart_main import cart_main
from DayBetes_food.components.ui import render_page
from datetime import datetime
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries.crud import (
    change_event_status,
    delete_portion_detail,
    get_intake_event,
    get_portion_detail_by_event,
    update_intake_event,
    update_portion_detail,
)


def _refresh_response(status: int = 200):
    return HTMLResponse("", status_code=status, headers={"HX-Refresh": "true"})


def _get_group_rows(connection, event_id: int, origin: str, origin_id: int):
    if origin not in ("catalog", "manual_intake"):
        return []
    portions = get_portion_detail_by_event(connection, event_id)
    rows = []
    for row in portions:
        if origin == "catalog" and row.get("catalog_id") == origin_id:
            rows.append(row)
        if origin == "manual_intake" and row.get("manual_intake_id") == origin_id:
            rows.append(row)
    return rows


def _consolidate_group_amount(connection, event_id: int, origin: str, origin_id: int, total_amount: float):
    rows = _get_group_rows(connection, event_id, origin, origin_id)
    if not rows:
        return False
    keep_id = rows[0]["id"]
    ok = update_portion_detail(connection, keep_id, {"amount_g": total_amount})
    if not ok:
        return False
    for row in rows[1:]:
        deleted = delete_portion_detail(connection, row["id"])
        if not deleted:
            return False
    return True


def setup_cart_routes(rt):
    @rt("/cart")
    def get(req):
        return render_page(req, cart_main, show_cart=False)

    @rt("/cart/event/{event_id}/meal_hour")
    def post(request: Request, event_id: int, meal_hour: str = "", meal_date: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            parsed_time = datetime.strptime(meal_hour, "%H:%M").time()
        except ValueError:
            return _refresh_response(status=400)

        with get_connection() as connection:
            event = get_intake_event(connection, event_id)
            if not event or not event.get("meal_time"):
                return _refresh_response(status=404)
            current = event["meal_time"]
            if meal_date:
                try:
                    chosen_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
                except ValueError:
                    return _refresh_response(status=400)
            else:
                chosen_date = current.date()
            updated = datetime.combine(chosen_date, parsed_time)
            ok = update_intake_event(connection, event_id, {"meal_time": updated})
            return _refresh_response(status=200 if ok else 400)

    @rt("/cart/event/{event_id}/meal_type")
    def post(request: Request, event_id: int, meal_type: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if not meal_type:
            return _refresh_response(status=400)
        with get_connection() as connection:
            ok = update_intake_event(connection, event_id, {"meal_type": meal_type})
        return _refresh_response(status=200 if ok else 400)

    @rt("/cart/event/{event_id}/eating_out")
    def post(request: Request, event_id: int, eating_out: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        value = (eating_out or "").strip().lower() == "true"
        with get_connection() as connection:
            ok = update_intake_event(connection, event_id, {"eating_out": value})
        return _refresh_response(status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/amount")
    def post(request: Request, event_id: int, origin: str, origin_id: int, amount_g: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            amount = float(amount_g)
        except (TypeError, ValueError):
            return _refresh_response(status=400)

        with get_connection() as connection:
            if amount <= 0:
                rows = _get_group_rows(connection, event_id, origin, origin_id)
                ok = bool(rows)
                for row in rows:
                    ok = ok and delete_portion_detail(connection, row["id"])
            else:
                ok = _consolidate_group_amount(connection, event_id, origin, origin_id, amount)
        return _refresh_response(status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/increment")
    def post(request: Request, event_id: int, origin: str, origin_id: int, amount_g: str = "", unit_g: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            rows = _get_group_rows(connection, event_id, origin, origin_id)
            if not rows:
                return _refresh_response(status=404)
            sample = rows[0]
            current_amount = sum(float(r.get("amount_g") or 0.0) for r in rows)

            try:
                unit = float(amount_g)
            except (TypeError, ValueError):
                try:
                    unit = float(unit_g)
                except (TypeError, ValueError):
                    if origin == "catalog":
                        unit = float(sample.get("catalog_default_portion") or 100.0)
                    else:
                        unit = float(sample.get("manual_amount_g") or sample.get("amount_g") or 100.0)
            if unit <= 0:
                unit = 1.0

            ok = _consolidate_group_amount(connection, event_id, origin, origin_id, current_amount + unit)
            return _refresh_response(status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/decrement")
    def post(request: Request, event_id: int, origin: str, origin_id: int, amount_g: str = "", unit_g: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            rows = _get_group_rows(connection, event_id, origin, origin_id)
            if not rows:
                return _refresh_response(status=404)
            sample = rows[0]
            current_amount = sum(float(r.get("amount_g") or 0.0) for r in rows)

            try:
                unit = float(amount_g)
            except (TypeError, ValueError):
                try:
                    unit = float(unit_g)
                except (TypeError, ValueError):
                    if origin == "catalog":
                        unit = float(sample.get("catalog_default_portion") or 100.0)
                    else:
                        unit = float(sample.get("manual_amount_g") or sample.get("amount_g") or 100.0)
            if unit <= 0:
                unit = 1.0

            if current_amount <= unit + 1e-6:
                ok = True
                for row in rows:
                    ok = ok and delete_portion_detail(connection, row["id"])
            else:
                ok = _consolidate_group_amount(connection, event_id, origin, origin_id, current_amount - unit)
            return _refresh_response(status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/offset")
    def post(request: Request, event_id: int, origin: str, origin_id: int, offset_minutes: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            value = int(offset_minutes)
        except (TypeError, ValueError):
            return _refresh_response(status=400)
        with get_connection() as connection:
            rows = _get_group_rows(connection, event_id, origin, origin_id)
            ok = bool(rows)
            for row in rows:
                ok = ok and update_portion_detail(connection, row["id"], {"offset_minutes": value})
        return _refresh_response(status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/strictly_weighed")
    def post(request: Request, event_id: int, origin: str, origin_id: int, strictly_weighed: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        value = (strictly_weighed or "").strip().lower() == "true"
        with get_connection() as connection:
            rows = _get_group_rows(connection, event_id, origin, origin_id)
            ok = bool(rows)
            for row in rows:
                ok = ok and update_portion_detail(connection, row["id"], {"strictly_weighed": value})
        return _refresh_response(status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/macros_quality")
    def post(request: Request, event_id: int, origin: str, origin_id: int, macros_quality: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        value = (macros_quality or "").strip().lower() == "true"
        with get_connection() as connection:
            rows = _get_group_rows(connection, event_id, origin, origin_id)
            ok = bool(rows)
            for row in rows:
                ok = ok and update_portion_detail(connection, row["id"], {"macros_quality": value})
        return _refresh_response(status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/is_cooked_weight")
    def post(request: Request, event_id: int, origin: str, origin_id: int, is_cooked_weight: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        value = (is_cooked_weight or "").strip().lower() == "true"
        with get_connection() as connection:
            rows = _get_group_rows(connection, event_id, origin, origin_id)
            ok = bool(rows)
            for row in rows:
                ok = ok and update_portion_detail(connection, row["id"], {"is_cooked_weight": value})
        return _refresh_response(status=200 if ok else 400)

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
                return _refresh_response(status=400)
            if value < 0:
                return _refresh_response(status=400)

            try:
                total = float(total_amount)
            except (TypeError, ValueError):
                total = None

            if ingested_unit == "%":
                if total is None:
                    return _refresh_response(status=400)
                ingested_amount = (total * value) / 100.0
            else:
                ingested_amount = value

        with get_connection() as connection:
            update_payload = {}
            if ingested_amount is not None:
                update_payload["ingested_amount"] = ingested_amount
            if (total_amount or "").strip() != "":
                try:
                    update_payload["total_amount"] = float(total_amount)
                except (TypeError, ValueError):
                    pass
            updated = update_intake_event(connection, event_id, update_payload) if update_payload else True
            changed = change_event_status(connection, event_id, "consumed")

        return _refresh_response(status=200 if (updated and changed) else 400)
