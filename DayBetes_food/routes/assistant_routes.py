"""Routes of the assistant for logging meals (code_conventions.md §8.12,
frontend_conventions.md §9.11).

Registered only when the assistant is configured (`ASSISTANT_ENABLED`):
otherwise its URLs answer 404 like any unknown URL.
"""

from fasthtml.common import *

from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.assistant.assistant_page import AssistantPage, MentionOptions
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import get_mention_suggestions
from DayBetes_food.errors import AuthenticationError
from DayBetes_food.http_errors import app_error_response


def setup_assistant_routes(rt):
    @rt("/assistant")
    def get(request: Request):
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        return render_page(request, lambda _: AssistantPage(), show_cart=False)

    @rt("/assistant/mentions")
    def get(request: Request, q: str = ""):
        """Suggestions after `/` (§9.11): the viewer's visible foods, dishes and recipes."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        search = (q or "").strip()
        with get_connection() as connection:
            rows = get_mention_suggestions(connection, int(user_id), search)
        return render_fragment(MentionOptions(rows, searching=bool(search)))
