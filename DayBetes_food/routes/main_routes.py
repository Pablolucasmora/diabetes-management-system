from fasthtml.common import *
import json
from pathlib import Path
from urllib.parse import quote_plus
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.menu.main_menu import main_menu
from DayBetes_food.components.scanner.scanner_main import scanner_main
from DayBetes_food.components.modal import ModalFormError
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import get_catalog_item_by_barcode, create_insulin_injection, get_open_insulin_pen
from DayBetes_food.domain.constants import InjectionZone, parse_enum, parse_optional_id
from DayBetes_food.domain.catalog import parse_barcode
from DayBetes_food.domain.insulin import InsulinInjectionCreate, parse_insulin_units, parse_shot_local
from DayBetes_food.errors import AuthenticationError, AuthorizationError, NotFoundError, ValidationError
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
        insulin_pen_id: str = "",
        units: str = "",
        zone: str = "",
        shot_hour: str = "",
        shot_date: str = "",
    ):
        """Log an injection from the menu pop-up (frontend_conventions.md §9.9). A form
        error is 200 + message inside the pop-up (code §9.5); on success an empty body
        and `injectionLogged`, which closes it, gives the notice and repaints the menu."""
        if request.headers.get("HX-Request") != "true":
            return app_error_response(request, AuthorizationError, "This action only works from the app.")
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        # The pen is required (measurement §8.4), the zone too in this form, and the
        # dose is optional for rapid and required for basal (§8.1).
        try:
            shot_time = local_naive_to_utc_aware(parse_shot_local(shot_hour, shot_date))
            pen_id = parse_optional_id(insulin_pen_id, "insulin_pen_id")
            if pen_id is None:
                raise ValidationError("Choose the pen.", fields={"insulin_pen_id": "required"})
            injection_zone = parse_enum(InjectionZone, zone, field="zone", normalize=str.lower)
            if injection_zone is None:
                raise ValidationError("Choose the injection zone.", fields={"zone": "required"})
            units_value = parse_insulin_units(units)
        except ValidationError as error:
            return render_fragment(ModalFormError(str(error)))

        with get_connection() as connection:
            # The type is the one of the pen's brand; the INSERT checks it is an
            # open pen of the user (measurement §8.4).
            pen = get_open_insulin_pen(connection, int(user_id), pen_id)
            if pen is None:
                return app_error_response(request, NotFoundError, "That pen is no longer in use.")
            payload = InsulinInjectionCreate(
                user_id=int(user_id),
                insulin_type=pen.insulin_type,
                shot_time=shot_time,
                timezone_at_event=APP_TIMEZONE.key,
                units=units_value,
                injection_zone=injection_zone,
                insulin_pen_id=pen_id,
            )
            try:
                create_insulin_injection(connection, payload)
            except ValidationError as error:
                return render_fragment(ModalFormError(str(error)))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That pen is no longer in use.")
        return HTMLResponse("", headers={"HX-Trigger": "injectionLogged"})

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
