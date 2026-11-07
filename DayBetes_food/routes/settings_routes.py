from fasthtml.common import *
from datetime import datetime
from DayBetes_food.components.settings.settings_main import (
    settings_main,
    tags_settings_page,
    tags_settings_list,
    tag_settings_row,
    injections_settings_page,
    injections_settings_chunk,
    meal_type_schedule_settings_page,
    meal_type_schedule_row,
)
from DayBetes_food.components.ui import render_page, render_fragment
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import (
    update_tag,
    get_all_tags,
    list_insulin_injections,
    get_injection_shot_time_at_offset,
    update_insulin_injection,
    delete_insulin_injection,
    get_insulin_injection,
    get_insulin_pen,
    list_insulin_pens_by_ids,
    list_open_insulin_pens,
    get_meal_type_schedule,
    upsert_meal_type_window,
    delete_meal_type_window,
)
from DayBetes_food.domain.constants import InsulinType, InjectionZone, MealType, parse_optional_id
from DayBetes_food.domain.insulin import InsulinInjectionUpdate, parse_insulin_units
from DayBetes_food.domain.meal_type_schedule import (
    AUTO_ASSIGNABLE_MEAL_TYPES,
    resolve_meal_type_window,
)
from DayBetes_food.errors import ValidationError, NotFoundError
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.time_utils import local_naive_to_utc_aware, APP_TIMEZONE


INJECTIONS_PAGE_SIZE = 15


def _injection_pens(connection, user_id: int, rows) -> tuple[list, dict]:
    """Open pens for the edit selectors and the pen of each row, open or closed."""
    open_pens = list_open_insulin_pens(connection, user_id)
    row_pen_ids = {row.insulin_pen_id for row in rows if row.insulin_pen_id is not None}
    pens_by_id = {pen.id: pen for pen in open_pens}
    missing = sorted(row_pen_ids - pens_by_id.keys())
    pens_by_id.update({pen.id: pen for pen in list_insulin_pens_by_ids(connection, user_id, missing)})
    return open_pens, pens_by_id


def setup_settings_routes(rt):
    @rt("/settings")
    def get(req):
        return render_page(
            req,
            lambda connection: settings_main(connection, current_user=req.state.user),
            show_cart=True,
        )

    @rt("/settings/tags")
    def get(req):
        return render_page(req, lambda connection: tags_settings_page(connection), show_cart=False)

    @rt("/settings/tags/list")
    def get(req, q: str = ""):
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            tags = get_all_tags(connection, search=(q or "").strip(), limit=1000)
        return tags_settings_list(tags)

    @rt("/settings/tags/update")
    def post(req: Request, tag_id: str = "", name: str = "", color: str = ""):
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if not (tag_id or "").isdigit():
            return HTMLResponse("Invalid tag id.", status_code=400)
        clean_name = " ".join((name or "").strip().split())
        clean_color = " ".join((color or "").strip().split())
        if not clean_name or not clean_color:
            return HTMLResponse("Name and color are required.", status_code=400)
        with get_connection() as connection:
            ok = update_tag(connection, int(tag_id), clean_name, clean_color)
        if not ok:
            return HTMLResponse("Could not update tag.", status_code=400)
        with get_connection() as connection:
            tags = get_all_tags(connection, search=clean_name, limit=1)
        if not tags:
            return HTMLResponse("")
        return render_fragment(tag_settings_row(tags[0]))

    @rt("/settings/meal_type_schedule")
    def get(req):
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        return render_page(
            req,
            lambda connection: meal_type_schedule_settings_page(connection, int(user_id)),
            show_cart=False,
        )

    @rt("/settings/meal_type_schedule/update")
    def post(req: Request, meal_type: str = "", start_time: str = "", end_time: str = ""):
        """
        Autosave of a time slot (start_time and end_time always together, see
        the meal_type_schedule_row docstring). meal_type is restricted to
        AUTO_ASSIGNABLE_MEAL_TYPES: snack/rescue never have a slot here
        (decision 2026-09-11).
        """
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        try:
            parsed_meal_type = MealType(meal_type)
        except ValueError:
            return HTMLResponse(status_code=422)
        if parsed_meal_type not in AUTO_ASSIGNABLE_MEAL_TYPES:
            return HTMLResponse(status_code=422)
        try:
            parsed_start = datetime.strptime((start_time or "").strip(), "%H:%M").time()
            parsed_end = datetime.strptime((end_time or "").strip(), "%H:%M").time()
        except ValueError:
            return HTMLResponse(status_code=422)
        with get_connection() as connection:
            try:
                upsert_meal_type_window(
                    connection,
                    user_id=int(user_id),
                    meal_type=parsed_meal_type,
                    start_time=parsed_start,
                    end_time=parsed_end,
                )
            except ValidationError:
                return HTMLResponse(status_code=422)
            overrides = get_meal_type_schedule(connection, int(user_id))
        return render_fragment(
            meal_type_schedule_row(
                parsed_meal_type,
                *resolve_meal_type_window(parsed_meal_type, overrides),
                is_default=parsed_meal_type not in overrides,
            )
        )

    @rt("/settings/meal_type_schedule/reset")
    def post(req: Request, meal_type: str = ""):
        """Delete the customized slot: the row goes back to showing (and using) the code default."""
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        try:
            parsed_meal_type = MealType(meal_type)
        except ValueError:
            return HTMLResponse(status_code=422)
        if parsed_meal_type not in AUTO_ASSIGNABLE_MEAL_TYPES:
            return HTMLResponse(status_code=422)
        with get_connection() as connection:
            delete_meal_type_window(connection, user_id=int(user_id), meal_type=parsed_meal_type)
            overrides = get_meal_type_schedule(connection, int(user_id))
        return render_fragment(
            meal_type_schedule_row(
                parsed_meal_type,
                *resolve_meal_type_window(parsed_meal_type, overrides),
                is_default=True,
            )
        )

    @rt("/settings/injections")
    def get(req):
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        with get_connection() as connection:
            rows = list_insulin_injections(
                connection,
                user_id=int(user_id),
                limit=INJECTIONS_PAGE_SIZE,
                offset=0,
            )
            open_pens, pens_by_id = _injection_pens(connection, int(user_id), rows)
        first_chunk = injections_settings_chunk(
            rows=rows,
            offset=0,
            page_size=INJECTIONS_PAGE_SIZE,
            previous_day=None,
            open_pens=open_pens,
            pens_by_id=pens_by_id,
        )
        return render_page(req, lambda _: injections_settings_page(first_chunk), show_cart=False)

    @rt("/settings/injections/list")
    def get(req, offset: int = 0):
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        clean_offset = max(0, int(offset or 0))
        with get_connection() as connection:
            rows = list_insulin_injections(
                connection,
                user_id=int(user_id),
                limit=INJECTIONS_PAGE_SIZE,
                offset=clean_offset,
            )
            previous_shot = get_injection_shot_time_at_offset(
                connection,
                user_id=int(user_id),
                offset=clean_offset,
            )
            open_pens, pens_by_id = _injection_pens(connection, int(user_id), rows)
        previous_day = previous_shot.date() if previous_shot else None
        return injections_settings_chunk(
            rows=rows,
            offset=clean_offset,
            page_size=INJECTIONS_PAGE_SIZE,
            previous_day=previous_day,
            open_pens=open_pens,
            pens_by_id=pens_by_id,
        )

    @rt("/settings/injections/{injection_id}/delete")
    def post(req: Request, injection_id: int):
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        with get_connection() as connection:
            try:
                delete_insulin_injection(connection, user_id=int(user_id), injection_id=int(injection_id))
            except NotFoundError:
                return HTMLResponse(status_code=404)
            return HTMLResponse(status_code=200)

    @rt("/settings/injections/{injection_id}/update")
    def post(
        req: Request,
        injection_id: int,
        insulin_pen_id: str = "",
        units: str = "",
        zone: str = "",
        shot_hour: str = "",
        shot_date: str = "",
    ):
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)

        # Parse date and time
        try:
            parsed_time = datetime.strptime((shot_hour or "").strip(), "%H:%M").time()
            parsed_date = datetime.strptime((shot_date or "").strip(), "%Y-%m-%d").date()
            shot_time_local = datetime.combine(parsed_date, parsed_time)
            shot_time = local_naive_to_utc_aware(shot_time_local)
        except ValueError:
            return HTMLResponse(status_code=422)

        # Parse the pen ('' = keep an old injection without one) and the dose
        # (optional for rapid, required for basal: validate_insulin_dose, §8.1).
        try:
            pen_id = parse_optional_id(insulin_pen_id, "insulin_pen_id")
            units_value = parse_insulin_units(units)
        except ValidationError:
            return HTMLResponse(status_code=422)

        # Parse zone (optional)
        injection_zone = None
        if zone and zone.strip():
            try:
                injection_zone = InjectionZone(zone.strip().lower())
            except ValueError:
                return HTMLResponse(status_code=422)

        with get_connection() as connection:
            # The type is the one of the pen's brand (measurement §8.4); without a
            # pen, the injection keeps its own. The UPDATE checks the pen fits.
            if pen_id is None:
                current = get_insulin_injection(connection, int(user_id), int(injection_id))
                if current is None:
                    return HTMLResponse(status_code=404)
                parsed_insulin_type = current.insulin_type
            else:
                pen = get_insulin_pen(connection, int(user_id), pen_id)
                if pen is None:
                    return HTMLResponse(status_code=404)
                parsed_insulin_type = pen.insulin_type
            payload = InsulinInjectionUpdate(
                insulin_type=parsed_insulin_type,
                shot_time=shot_time,
                injection_zone=injection_zone,
                units=units_value,
                insulin_pen_id=pen_id,
            )
            try:
                update_insulin_injection(
                    connection,
                    user_id=int(user_id),
                    injection_id=int(injection_id),
                    payload=payload,
                )
            except ValidationError:
                return HTMLResponse(status_code=422)
            except NotFoundError:
                return HTMLResponse(status_code=404)
            return HTMLResponse(status_code=200)
