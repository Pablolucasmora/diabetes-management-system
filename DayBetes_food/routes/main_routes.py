from fasthtml.common import *
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.menu.main_menu import main_menu
from DayBetes_food.components.scanner.scanner_main import scanner_main
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import get_catalog_item_by_barcode, create_insulin_injection
from DayBetes_food.domain.constants import InsulinType, InjectionZone
from DayBetes_food.domain.catalog import parse_barcode
from DayBetes_food.domain.insulin import InsulinInjectionCreate
from DayBetes_food.errors import AuthenticationError, ValidationError
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.time_utils import local_naive_to_utc_aware, APP_TIMEZONE


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
        units: str = "",
        zone: str = "",
        shot_hour: str = "",
        shot_date: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)

        # Parsear fecha y hora
        try:
            parsed_time = datetime.strptime((shot_hour or "").strip(), "%H:%M").time()
            parsed_date = datetime.strptime((shot_date or "").strip(), "%Y-%m-%d").date()
            shot_time_local = datetime.combine(parsed_date, parsed_time)
            shot_time = local_naive_to_utc_aware(shot_time_local)
        except ValueError:
            return HTMLResponse(status_code=422)

        # Parsear tipo de insulina
        try:
            parsed_insulin_type = InsulinType(insulin_type.strip().lower())
        except ValueError:
            return HTMLResponse(status_code=422)

        # Parsear dosis (si aplica)
        units_value = None
        if parsed_insulin_type is InsulinType.BASAL:
            try:
                units_value = float((units or "").strip().replace(",", "."))
            except (TypeError, ValueError):
                return HTMLResponse(status_code=422)

        # Parsear zona (opcional)
        injection_zone = None
        if zone and zone.strip():
            try:
                injection_zone = InjectionZone(zone.strip().lower())
            except ValueError:
                return HTMLResponse(status_code=422)

        # Crear payload y registrar
        payload = InsulinInjectionCreate(
            user_id=int(user_id),
            insulin_type=parsed_insulin_type,
            shot_time=shot_time,
            timezone_at_event=APP_TIMEZONE.key,
            units=units_value,
            injection_zone=injection_zone,
        )
        with get_connection() as connection:
            try:
                create_insulin_injection(connection, payload)
            except ValidationError:
                return HTMLResponse(status_code=422)
            return render_fragment(main_menu(connection))

    @rt("/scanner")
    def get(req):
        return render_page(req, lambda _: scanner_main())

    @rt("/data/smart_macros_cases.json")
    def get():
        # Read-only route: the static handler does not serve this .json, and
        # dbSmartMacrosSelfCheck() needs it (plan F5.3). It is only the shared
        # parse cases, no user data.
        path = Path(__file__).resolve().parent.parent / "static" / "data" / "smart_macros_cases.json"
        if not path.is_file():
            return HTMLResponse(status_code=404)
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    @rt("/scanner/resolve")
    def post(request: Request, barcode: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            clean = parse_barcode(barcode)
        except ValidationError:
            return app_error_response(
                request, ValidationError, "Invalid barcode: it must contain only digits (8 to 48)."
            )
        if not clean:
            return app_error_response(
                request, ValidationError, "Invalid barcode: it must contain only digits (8 to 48)."
            )
        existing_id = None
        with get_connection() as connection:
            existing = get_catalog_item_by_barcode(connection, int(user_id), clean)
            if existing:
                existing_id = existing.id
        encoded = quote_plus(clean)
        existing_suffix = f"&existing_id={existing_id}" if existing_id else ""
        location = {
            "path": f"/food/create/catalog/form?barcode={encoded}{existing_suffix}",
            "target": "#main_content",
            "swap": "innerHTML",
            "push": True,
        }
        return HTMLResponse("", headers={"HX-Location": json.dumps(location)})
