from fasthtml.common import *
import json
from datetime import datetime
from urllib.parse import quote_plus
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.menu.main_menu import main_menu
from DayBetes_food.components.scanner.scanner_main import scanner_main
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries.crud import add_manual_injection_log, get_catalog_item_by_barcode
from DayBetes_food.time_utils import local_naive_to_utc


def setup_main_routes(rt):
    @rt("/")
    def get():
        return RedirectResponse(url="/menu")

    @rt("/menu")
    def get(req):
        return render_page(req, main_menu)

    @rt("/menu/injection_log")
    def post(
        request: Request,
        insulin_type: str = "",
        basal_units: str = "",
        zone: str = "",
        shot_hour: str = "",
        shot_date: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)

        units = None
        if (insulin_type or "").strip().lower() == "basal":
            try:
                units = float((basal_units or "").strip().replace(",", "."))
            except (TypeError, ValueError):
                return HTMLResponse(status_code=400)
        try:
            parsed_time = datetime.strptime((shot_hour or "").strip(), "%H:%M").time()
            parsed_date = datetime.strptime((shot_date or "").strip(), "%Y-%m-%d").date()
            shot_time_local = datetime.combine(parsed_date, parsed_time)
            shot_time = local_naive_to_utc(shot_time_local)
        except ValueError:
            return HTMLResponse(status_code=400)

        with get_connection() as connection:
            ok = add_manual_injection_log(
                connection,
                users_id=int(user_id),
                insulin_type=insulin_type,
                injection_zone=zone,
                basal_units=units,
                shot_time=shot_time,
            )
            if not ok:
                return HTMLResponse(status_code=400)
            return render_fragment(main_menu(connection))

    @rt("/scanner")
    def get(req):
        return render_page(req, lambda _: scanner_main())

    @rt("/scanner/resolve")
    def post(request: Request, barcode: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean = (barcode or "").strip()
        if not clean:
            return HTMLResponse("", status_code=400)
        existing_id = None
        with get_connection() as connection:
            user_id = get_current_user_id()
            viewer_id = user_id if user_id else -1
            existing = get_catalog_item_by_barcode(connection, clean, viewer_user_id=viewer_id)
            if existing:
                existing_id = int(existing["id"])
        encoded = quote_plus(clean)
        existing_suffix = f"&existing_id={existing_id}" if existing_id else ""
        location = {
            "path": f"/food/create/catalog/form?barcode={encoded}{existing_suffix}",
            "target": "#main_content",
            "swap": "innerHTML",
            "push": True,
        }
        return HTMLResponse("", headers={"HX-Location": json.dumps(location)})
