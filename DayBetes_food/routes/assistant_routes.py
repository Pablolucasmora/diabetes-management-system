"""Routes of the assistant for logging meals (code_conventions.md §8.12,
frontend_conventions.md §9.11).

Registered only when the assistant is configured (`ASSISTANT_ENABLED`):
otherwise its URLs answer 404 like any unknown URL.

Errors of the HTMX actions keep their status and empty body, with the message
in the toast (`app_error_response`, error_conventions.md §7.1): htmx swaps
nothing, so the text and the photos stay in the composer to send again.
"""

import logging
from urllib.parse import urlencode

from fasthtml.common import *
from starlette.datastructures import UploadFile

from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.assistant.assistant_page import (
    AssistantMealSelect,
    AssistantPage,
    AssistantThread,
    ConversationIdInput,
    MentionOptions,
    PlusRow,
    RepeatSavedCard,
    TurnBlock,
)
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import get_mention_suggestions, list_needs_review, list_planned_intake_events
from DayBetes_food.domain.assistant import (
    parse_meal_choice,
    ASSISTANT_PHOTO_MAX_BYTES,
    AssistantTurnRequest,
    check_photo_count,
    parse_assistant_photos,
    parse_assistant_text,
    parse_mentions,
    require_turn_content,
)
from DayBetes_food.domain.constants import PathId, parse_optional_id
from DayBetes_food.errors import (
    AuthenticationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from DayBetes_food.http_errors import app_error_response, request_id
from DayBetes_food.domain.assistant import parse_plus_step
from DayBetes_food.services.assistant import (
    apply_plus,
    conversation_plus_buttons,
    conversation_turns,
    plus_buttons,
    resolve_conversation,
    send_assistant_message,
)
from DayBetes_food.services.intake_event import save_quick_add_as_dish

logger = logging.getLogger(__name__)

_MEAL_GONE = "That meal was confirmed or deleted. Choose another meal."
_UNAVAILABLE = "The assistant is not available right now. Try again in a moment."


def _read_photos(photos) -> list[tuple[str, bytes]]:
    """The uploaded files, each read up to one byte over the limit: a larger one
    is rejected without reading it whole. Too many are rejected before reading."""
    files = [photo for photo in (photos or []) if isinstance(photo, UploadFile) and photo.filename]
    check_photo_count(len(files))
    return [(photo.content_type or "", photo.file.read(ASSISTANT_PHOTO_MAX_BYTES + 1)) for photo in files]


def _selected_meal(events: list, chosen: int | None) -> int | None:
    """The meal chosen in the selector, if it is still a planned meal of the user."""
    return chosen if chosen and any(event.id == chosen for event in events) else None


def _assistant_url(conversation_id: int | None, intake_event_id: str) -> str:
    """The URL that reopens the conversation on screen, which replaces the page's
    own so that Back comes back to it (frontend_conventions.md §5)."""
    if conversation_id is not None:
        return f"/assistant?{urlencode({'conversation_id': conversation_id})}"
    if intake_event_id:
        return f"/assistant?{urlencode({'intake_event_id': intake_event_id})}"
    return "/assistant"


def _pending_review(connection, user_id: int) -> frozenset:
    """(entry_type, id) of the provisional entries still to review: their cards show Review."""
    return frozenset((entry.entry_type.value, entry.entry_id) for entry in list_needs_review(connection, user_id))


def setup_assistant_routes(rt):
    @rt("/assistant")
    def get(request: Request, intake_event_id: str = "", conversation_id: str = ""):
        """The page (§9.11): the chosen conversation, else the chosen meal's, else the
        conversation of the latest planned meal, like `Add to` in Food."""
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        chosen_conversation = parse_optional_id(conversation_id, "conversation")

        chosen_event, without_meal = parse_meal_choice(intake_event_id)

        with get_connection() as connection:
            events = list_planned_intake_events(connection, int(user_id))
            selected = _selected_meal(events, chosen_event)
            if not intake_event_id and not chosen_conversation and events:
                selected = events[0].id
            try:
                conversation = resolve_conversation(
                    connection, int(user_id), chosen_conversation, selected, latest_without_meal=without_meal
                )
            except (NotFoundError, ConflictError):
                # Its meal was confirmed or deleted meanwhile: start on a new meal.
                conversation, selected = None, None
            if conversation is not None:
                selected = conversation.intake_event_id
                without = conversation.without_meal
            else:
                without = without_meal
            turns = conversation_turns(connection, int(user_id), conversation.id) if conversation else []
            pending = _pending_review(connection, int(user_id))
            buttons = plus_buttons(connection, int(user_id), conversation)
        content = AssistantPage(
            events,
            selected,
            conversation.id if conversation else None,
            turns,
            without_meal=without,
            pending=pending,
            plus_buttons=buttons,
        )
        return render_page(request, content, show_cart=False)

    @rt("/assistant/thread")
    def get(request: Request, intake_event_id: str = "", new_chat: str = "", conversation_id: str = ""):
        """The conversation of the meal chosen in `Add to` (§9.11): `New meal` is empty,
        and `No meal` reopens the latest one unless `New chat` asks for an empty one.
        With `conversation_id`, that conversation: the page reloads it after a failed
        send, to show what the rounds before the failure already did (§8.12)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            event_id, without_meal = parse_meal_choice(intake_event_id)
            chosen_conversation_id = parse_optional_id(conversation_id, "conversation")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        with get_connection() as connection:
            try:
                conversation = resolve_conversation(
                    connection,
                    int(user_id),
                    chosen_conversation_id,
                    event_id,
                    latest_without_meal=without_meal and not new_chat,
                )
            except (NotFoundError, ConflictError):
                return app_error_response(request, NotFoundError, _MEAL_GONE)
            turns = conversation_turns(connection, int(user_id), conversation.id) if conversation else []
            pending = _pending_review(connection, int(user_id))
            buttons = plus_buttons(connection, int(user_id), conversation)
        conversation_id_shown = conversation.id if conversation else None
        response = render_fragment(
            (
                AssistantThread(turns, conversation_id_shown, pending),
                PlusRow(buttons, conversation_id_shown, oob=True),
            )
        )
        response.headers["HX-Replace-Url"] = _assistant_url(conversation.id if conversation else None, intake_event_id)
        return response

    @rt("/assistant/message")
    def post(
        request: Request,
        message: str = "",
        mentions: str = "",
        intake_event_id: str = "",
        conversation_id: str = "",
        photo: list[UploadFile] | None = None,
    ):
        """One message to the assistant (§8.12). Answers the turn, appended to the
        thread, with the conversation id and, if its first add created the meal,
        the meal selector out of band.

        Repeating it is a new message: the assistant may add the food again, and
        the user removes the copy in the cart (§9.6).
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            turn_request = AssistantTurnRequest(
                text=parse_assistant_text(message),
                mentions=parse_mentions(mentions),
                photos=parse_assistant_photos(_read_photos(photo)),
            )
            require_turn_content(turn_request)
            chosen_event_id, without_meal = parse_meal_choice(intake_event_id)
            chosen_conversation_id = parse_optional_id(conversation_id, "conversation")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))

        with get_connection() as connection:
            try:
                result = send_assistant_message(
                    connection,
                    int(user_id),
                    conversation_id=chosen_conversation_id,
                    event_id=chosen_event_id,
                    request=turn_request,
                    without_meal=without_meal,
                )
            except (NotFoundError, ConflictError) as error:
                return app_error_response(request, type(error), _MEAL_GONE)
            except ExternalServiceError as error:
                # Logged once here, with the adapter's internal reason (§8.3, §8.6).
                logger.warning(
                    "Assistant call failed",
                    exc_info=error,
                    extra={"error_code": error.code, "reason": str(error), "request_id": request_id(request)},
                )
                return app_error_response(request, ExternalServiceError, _UNAVAILABLE)
            events = list_planned_intake_events(connection, int(user_id)) if result.meal_created else []
            pending = _pending_review(connection, int(user_id))
            buttons = conversation_plus_buttons(connection, int(user_id), result.conversation_id)

        fragments = [
            ConversationIdInput(result.conversation_id, oob=True),
            PlusRow(buttons, result.conversation_id, oob=True),
        ]
        if result.turn is not None:
            fragments.insert(0, TurnBlock(result.turn, result.conversation_id, result.notices, pending))
        if result.meal_created:
            # The new meal is chosen in `Add to`, so the next message continues it.
            fragments.append(AssistantMealSelect(events, result.event_id, oob=True))
        response = render_fragment(tuple(fragments))
        response.headers["HX-Replace-Url"] = _assistant_url(result.conversation_id, intake_event_id)
        # The bar's dot of foods to review (frontend §9.3) asks again.
        response.headers["HX-Trigger"] = "dbReviewChanged"
        return response

    @rt("/assistant/repeat/{quick_add_id}/dish")
    def post(request: Request, quick_add_id: PathId, conversation_id: str = ""):
        """Save a repeated quick add as a provisional dish (§8.12, "Repeticiones"):
        the user's tap on its card. Repeating it -> 409, the dish already exists (§9.6)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            chosen_conversation_id = parse_optional_id(conversation_id, "conversation")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        with get_connection() as connection:
            try:
                with connection.transaction():
                    dish_id, name = save_quick_add_as_dish(connection, int(user_id), quick_add_id)
            except NotFoundError as error:
                return app_error_response(request, NotFoundError, str(error))
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
        response = render_fragment(RepeatSavedCard(name, dish_id, chosen_conversation_id or 0))
        response.headers["HX-Trigger"] = "dbReviewChanged"
        return response

    @rt("/assistant/plus/{portion_id}")
    def post(request: Request, portion_id: PathId, step: str = "1", conversation_id: str = ""):
        """A +1 button (§8.12, "Botones +1"): one more unit of a row of the
        conversation's meal, without the model. Answers the row of buttons.
        Repeating it adds another unit: each tap is one more (§9.6)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            parsed_step = parse_plus_step(step)
            chosen_conversation_id = parse_optional_id(conversation_id, "conversation")
            if chosen_conversation_id is None:
                raise ValidationError("Conversation not found.")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        with get_connection() as connection:
            try:
                with connection.transaction():
                    apply_plus(connection, int(user_id), chosen_conversation_id, portion_id, parsed_step)
            except NotFoundError as error:
                return app_error_response(request, NotFoundError, str(error))
            except ConflictError:
                return app_error_response(request, ConflictError, _MEAL_GONE)
            except ValidationError as error:
                return app_error_response(request, ValidationError, str(error))
            buttons = conversation_plus_buttons(connection, int(user_id), chosen_conversation_id)
        return render_fragment(PlusRow(buttons, chosen_conversation_id))

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
