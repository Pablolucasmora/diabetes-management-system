from fasthtml.common import *
from DayBetes_food.components.settings.settings_main import settings_main, tags_settings_page, tags_settings_list, tag_settings_row
from DayBetes_food.components.ui import render_page, render_fragment
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries.crud import update_tag, get_all_tags


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
