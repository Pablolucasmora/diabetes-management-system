from fasthtml.common import *
import json
from urllib.parse import quote_plus
from DayBetes_food.components.menu.main_menu import main_menu
from DayBetes_food.components.scanner.scanner_main import scanner_main
from DayBetes_food.components.ui import render_page
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries.crud import get_catalog_item_by_barcode, get_default_user_id


def setup_main_routes(rt):
    @rt("/")
    def get():
        return RedirectResponse(url="/menu")

    @rt("/menu")
    def get(req):
        return render_page(req, main_menu)

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
            user_id = get_default_user_id(connection)
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
