from fasthtml.common import *
from DayBetes_food.components.cart.cart_main import cart_main
from DayBetes_food.components.cart.cart_components import MacrosSummary
from DayBetes_food.components.ui import render_fragment, render_page
from datetime import datetime
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries.crud import (
    change_event_status,
    delete_intake_event,
    get_intake_event,
    get_portion_detail_by_event,
    update_intake_event,
)


def _cart_response(connection, status: int = 200):
    if status >= 400:
        return HTMLResponse("", status_code=status)
    return render_fragment(cart_main(connection))


def _to_float(value: str):
    normalized = (value or "").strip().replace(",", ".")
    return float(normalized)


def _group_column(origin: str):
    if origin == "catalog":
        return "catalog_id"
    if origin == "manual_intake":
        return "manual_intake_id"
    return None


def _get_group_rows(connection, event_id: int, origin: str, origin_id: int):
    group_col = _group_column(origin)
    if not group_col:
        return []
    query = f"""
        SELECT
            pd.id,
            pd.amount_g,
            c.default_portion AS catalog_default_portion,
            im.amount_g AS manual_amount_g
        FROM portion_detail pd
        LEFT JOIN catalog c ON pd.catalog_id = c.id
        LEFT JOIN manual_intake im ON pd.manual_intake_id = im.id
        WHERE pd.intake_event_id = %(event_id)s
          AND pd.{group_col} = %(origin_id)s
        ORDER BY pd.id;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"event_id": event_id, "origin_id": origin_id})
        return cursor.fetchall()


def _delete_group(connection, rows):
    if not rows:
        return False
    ids = [int(row["id"]) for row in rows]
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM portion_detail WHERE id = ANY(%(ids)s);",
                {"ids": ids},
            )
            deleted = cursor.rowcount
        connection.commit()
        return deleted == len(ids)
    except Exception:
        connection.rollback()
        return False


def _consolidate_group_amount(connection, event_id: int, origin: str, origin_id: int, total_amount: float):
    rows = _get_group_rows(connection, event_id, origin, origin_id)
    if not rows:
        return False

    keep_id = int(rows[0]["id"])
    delete_ids = [int(row["id"]) for row in rows[1:]]
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE portion_detail SET amount_g = %(amount)s WHERE id = %(id)s;",
                {"amount": total_amount, "id": keep_id},
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False

            if delete_ids:
                cursor.execute(
                    "DELETE FROM portion_detail WHERE id = ANY(%(ids)s);",
                    {"ids": delete_ids},
                )
                if cursor.rowcount != len(delete_ids):
                    connection.rollback()
                    return False
        connection.commit()
        return True
    except Exception:
        connection.rollback()
        return False


def _update_group_field(connection, event_id: int, origin: str, origin_id: int, field_name: str, field_value):
    group_col = _group_column(origin)
    if not group_col:
        return False
    allowed_fields = {"offset_minutes", "strictly_weighed", "macros_quality", "is_cooked_weight"}
    if field_name not in allowed_fields:
        return False

    query = f"""
        UPDATE portion_detail pd
        SET {field_name} = %(value)s
        WHERE pd.intake_event_id = %(event_id)s
          AND pd.{group_col} = %(origin_id)s;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"value": field_value, "event_id": event_id, "origin_id": origin_id},
            )
            updated = cursor.rowcount
        connection.commit()
        return updated > 0
    except Exception:
        connection.rollback()
        return False


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
            return HTMLResponse(status_code=400)

        with get_connection() as connection:
            event = get_intake_event(connection, event_id)
            if not event or not event.get("meal_time"):
                return HTMLResponse(status_code=404)
            current = event["meal_time"]
            if meal_date:
                try:
                    chosen_date = datetime.strptime(meal_date, "%Y-%m-%d").date()
                except ValueError:
                    return HTMLResponse(status_code=400)
            else:
                chosen_date = current.date()
            updated = datetime.combine(chosen_date, parsed_time)
            ok = update_intake_event(connection, event_id, {"meal_time": updated})
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/meal_type")
    def post(request: Request, event_id: int, meal_type: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if not meal_type:
            return HTMLResponse(status_code=400)
        with get_connection() as connection:
            ok = update_intake_event(connection, event_id, {"meal_type": meal_type})
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
                rows = _get_group_rows(connection, event_id, origin, origin_id)
                ok = _delete_group(connection, rows)
            else:
                ok = _consolidate_group_amount(connection, event_id, origin, origin_id, amount)
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
            ok = _update_group_field(connection, event_id, origin, origin_id, "offset_minutes", value)
            return _cart_response(connection, status=200 if ok else 400)

    @rt("/cart/event/{event_id}/ingredient/{origin}/{origin_id}/strictly_weighed")
    def post(request: Request, event_id: int, origin: str, origin_id: int, strictly_weighed: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        value = (strictly_weighed or "").strip().lower() == "true"
        with get_connection() as connection:
            ok = _update_group_field(connection, event_id, origin, origin_id, "strictly_weighed", value)
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
            ok = _update_group_field(connection, event_id, origin, origin_id, "macros_quality", value)
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
            ok = _update_group_field(connection, event_id, origin, origin_id, "is_cooked_weight", value)
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

            return _cart_response(connection, status=200 if (updated and changed) else 400)
