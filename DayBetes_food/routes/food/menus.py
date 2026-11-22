"""The saved restaurant menus, `Menus` (frontend_conventions.md §9.13;
code_conventions.md §11.2.10): read and delete, never edited by hand."""

import json

from fasthtml.common import *

from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.food.menus import MENUS_PATH, MenuPlacePage, MenusPage
from DayBetes_food.components.ui import render_page
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import delete_menu_item, delete_menu_place, list_menu_items, list_menu_places
from DayBetes_food.errors import AuthenticationError, NotFoundError
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.domain.constants import PathId

_MENU_NOT_FOUND = "Menu not found."


def _back_to_menus() -> dict:
    location = {"path": MENUS_PATH, "target": "#main_content", "swap": "innerHTML", "push": True}
    return {"HX-Location": json.dumps(location)}


def _user_id() -> int:
    user_id = get_current_user_id()
    if not user_id:
        raise AuthenticationError("Your session has expired.")
    return int(user_id)


def setup_menus_routes(rt):
    @rt(MENUS_PATH)
    def get(request: Request):
        user_id = _user_id()
        with get_connection() as connection:
            places = list_menu_places(connection, user_id)
        return render_page(request, MenusPage(places))

    @rt(f"{MENUS_PATH}/place")
    def get(request: Request, place: str = ""):
        user_id = _user_id()
        with get_connection() as connection:
            items = list_menu_items(connection, user_id, place.strip())
        if not items:
            raise NotFoundError(_MENU_NOT_FOUND)
        return render_page(request, MenuPlacePage(items[0].place, items))

    @rt(f"{MENUS_PATH}/items/{{item_id}}/delete")
    def post(request: Request, item_id: PathId):
        """One dish: the row goes; after the last one of its place, back to the list."""
        user_id = _user_id()
        with get_connection() as connection:
            with connection.transaction():
                place = delete_menu_item(connection, user_id, item_id)
                remaining = list_menu_items(connection, user_id, place) if place else []
        if place is None:
            return app_error_response(request, NotFoundError, "Dish not found.")
        return HTMLResponse("", headers={} if remaining else _back_to_menus())

    @rt(f"{MENUS_PATH}/delete")
    def post(request: Request, place: str = ""):
        user_id = _user_id()
        with get_connection() as connection:
            with connection.transaction():
                deleted = delete_menu_place(connection, user_id, place.strip())
        if not deleted:
            return app_error_response(request, NotFoundError, _MENU_NOT_FOUND)
        return HTMLResponse("", headers=_back_to_menus())
