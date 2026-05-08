from fasthtml.common import *
from datetime import datetime
from DayBetes_food.components.settings.settings_main import (
    settings_main,
    tags_settings_page,
    tags_settings_list,
    tag_settings_row,
    injections_settings_page,
    injections_settings_chunk,
)
from DayBetes_food.components.ui import render_page, render_fragment
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries.crud import (
    update_tag,
    get_all_tags,
    get_user_injection_logs,
    get_user_injection_log_prev_day,
    update_user_injection_log,
    delete_user_injection_log,
    get_user_injection_log_by_id,
)
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.time_utils import local_naive_to_utc


INJECTIONS_PAGE_SIZE = 15


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

    @rt("/settings/injections")
    def get(req):
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        with get_connection() as connection:
            rows = get_user_injection_logs(connection, users_id=int(user_id), limit=INJECTIONS_PAGE_SIZE, offset=0)
        first_chunk = injections_settings_chunk(
            rows=rows,
            offset=0,
            page_size=INJECTIONS_PAGE_SIZE,
            previous_day=None,
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
            rows = get_user_injection_logs(
                connection,
                users_id=int(user_id),
                limit=INJECTIONS_PAGE_SIZE,
                offset=clean_offset,
            )
            previous_shot = get_user_injection_log_prev_day(
                connection,
                users_id=int(user_id),
                offset=clean_offset,
            )
        previous_day = previous_shot.date() if previous_shot else None
        return injections_settings_chunk(
            rows=rows,
            offset=clean_offset,
            page_size=INJECTIONS_PAGE_SIZE,
            previous_day=previous_day,
        )

    @rt("/settings/injections/{injection_id}/delete")
    def post(req: Request, injection_id: int):
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        with get_connection() as connection:
            exists = get_user_injection_log_by_id(connection, users_id=int(user_id), injection_id=int(injection_id))
            if not exists:
                return HTMLResponse(status_code=404)
            ok = delete_user_injection_log(connection, users_id=int(user_id), injection_id=int(injection_id))
        return HTMLResponse(status_code=200 if ok else 400)

    @rt("/settings/injections/{injection_id}/update")
    def post(
        req: Request,
        injection_id: int,
        insulin_type: str = "",
        basal_units: str = "",
        zone: str = "",
        shot_hour: str = "",
        shot_date: str = "",
    ):
        if req.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        clean_type = (insulin_type or "").strip().lower()
        units = None
        if clean_type == "basal":
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
            exists = get_user_injection_log_by_id(connection, users_id=int(user_id), injection_id=int(injection_id))
            if not exists:
                return HTMLResponse(status_code=404)
            ok = update_user_injection_log(
                connection,
                users_id=int(user_id),
                injection_id=int(injection_id),
                insulin_type=clean_type,
                injection_zone=zone,
                shot_time=shot_time,
                basal_units=units,
            )
        return HTMLResponse(status_code=200 if ok else 400)
