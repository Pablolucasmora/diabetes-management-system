"""Routes of the `Fridge` tab of Food (frontend_conventions.md §9.8).

Every route is an htmx action of the Food page: it requires `HX-Request` (403
otherwise) and a session. The HTMX contract (target, swap, fragment, events) is
in code_conventions.md §9.5. Saving a food into a new container is a route of
the food page, next to `/food/log` (routes/food_routes.py).
"""

from fasthtml.common import *

from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.food.fridge import (
    FridgeActionsMenu,
    FridgeDiscardConfirm,
    FridgeEditForm,
    FridgeListContent,
    FridgeListOob,
)
from DayBetes_food.components.modal import ModalFormError
from DayBetes_food.components.ui import render_fragment
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import update_fridge
from DayBetes_food.domain.constants import StorageLocation, parse_enum
from DayBetes_food.domain.fridge import (
    FridgeUpdate,
    expiry_from_local_date,
    parse_content_weight,
    parse_expiry_date,
    parse_fridge_name,
)
from DayBetes_food.errors import AuthenticationError, NotFoundError, ValidationError
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.services.fridge import discard_fridge, get_fridge_item, list_fridge_items, move_fridge
from DayBetes_food.time_utils import local_naive_to_utc_aware, utc_now

# Event of a change that closes the actions pop-up (code_conventions.md §9.5).
FRIDGE_CHANGED_EVENT = "fridgeChanged"
_NOT_FOUND = "That container is no longer in your fridge."
_SESSION_EXPIRED = "Your session has expired."


def _list_response(connection, user_id: int, headers: dict | None = None):
    """The whole list, for #food-list."""
    items = list_fridge_items(connection, user_id)
    response = render_fragment(FridgeListContent(items, utc_now()))
    response.headers.update(headers or {})
    return response


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def setup_fridge_routes(rt):
    def _view(request: Request, fridge_id: int, component):
        """A view of the actions pop-up of one container."""
        if not _is_htmx(request):
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _SESSION_EXPIRED)
        with get_connection() as connection:
            item = get_fridge_item(connection, int(user_id), fridge_id)
        if item is None:
            return app_error_response(request, NotFoundError, _NOT_FOUND)
        return render_fragment(component(item))

    @rt("/food/fridge/{fridge_id}/actions")
    def get(request: Request, fridge_id: int):
        return _view(request, fridge_id, FridgeActionsMenu)

    @rt("/food/fridge/{fridge_id}/actions/edit")
    def get(request: Request, fridge_id: int):
        return _view(request, fridge_id, FridgeEditForm)

    @rt("/food/fridge/{fridge_id}/actions/discard")
    def get(request: Request, fridge_id: int):
        return _view(request, fridge_id, FridgeDiscardConfirm)

    @rt("/food/fridge/{fridge_id}/location")
    def post(request: Request, fridge_id: int, location: str = ""):
        """Move a container to `location`. Repeating it is a no-op: it is already
        there (code_conventions.md §6.3). Answers with the whole list."""
        if not _is_htmx(request):
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _SESSION_EXPIRED)
        try:
            target = parse_enum(StorageLocation, location, field="location")
        except ValidationError as error:
            return app_error_response(request, error, str(error))
        if target is None:
            return app_error_response(request, ValidationError, "Choose the fridge or the freezer.")
        with get_connection() as connection:
            try:
                move_fridge(connection, int(user_id), fridge_id, target)
            except NotFoundError:
                return app_error_response(request, NotFoundError, _NOT_FOUND)
            return _list_response(connection, int(user_id))

    @rt("/food/fridge/{fridge_id}/discard")
    def post(request: Request, fridge_id: int):
        """Throw a container away (code_conventions.md §11.2.6). Repeating it is a
        404: it is no longer open. Answers with the whole list and `fridgeChanged`."""
        if not _is_htmx(request):
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _SESSION_EXPIRED)
        with get_connection() as connection:
            try:
                discard_fridge(connection, int(user_id), fridge_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, _NOT_FOUND)
            return _list_response(connection, int(user_id), {"HX-Trigger": FRIDGE_CHANGED_EVENT})

    @rt("/food/fridge/{fridge_id}/edit")
    def post(request: Request, fridge_id: int, name: str = "", expires_at: str = "", content_weight: str = ""):
        """Save name, expiry date and real weight together (full replacement, §3.4).
        A validation error is a message inside the form (200, §9.5). On success the
        message is emptied, the list is swapped out of band and `fridgeChanged`
        closes the pop-up. Repeating it leaves the same values."""
        if not _is_htmx(request):
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, _SESSION_EXPIRED)
        try:
            payload = FridgeUpdate(
                name=parse_fridge_name(name),
                expires_at=local_naive_to_utc_aware(expiry_from_local_date(parse_expiry_date(expires_at))),
                content_weight=parse_content_weight(content_weight),
            )
        except ValidationError as error:
            return render_fragment(ModalFormError(str(error)))
        with get_connection() as connection:
            try:
                update_fridge(connection, int(user_id), fridge_id, payload)
            except ValidationError as error:
                return render_fragment(ModalFormError(str(error)))
            except NotFoundError:
                return app_error_response(request, NotFoundError, _NOT_FOUND)
            items = list_fridge_items(connection, int(user_id))
        response = render_fragment(FridgeListOob(items, utc_now()))
        response.headers["HX-Trigger"] = FRIDGE_CHANGED_EVENT
        return response
