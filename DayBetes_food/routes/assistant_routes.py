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

from DayBetes_food.routes.navigation import hx_location
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.assistant.assistant_page import (
    AssistantPage,
    AssistantThread,
    ChatsModal,
    ConversationIdInput,
    FailedTurnBlock,
    MealBar,
    MentionOptions,
    PastChatPage,
    PastChatsPage,
    PendingTurnBlock,
    PlusRow,
    RemovalRow,
    RepeatSavedCard,
    TurnBlock,
    assistant_turn_dom_id,
)
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import (
    get_assistant_conversation,
    get_assistant_turn,
    get_latest_unseen_assistant_turn,
    get_pending_assistant_turn,
    list_intake_plates,
    get_intake_event,
    get_mention_suggestions,
    list_meal_free_conversations,
    list_needs_review,
    list_past_conversations,
    hide_assistant_conversation,
    list_planned_intake_events,
    list_portions_by_event,
    list_portions_by_events,
    mark_assistant_turn_seen,
)
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
from DayBetes_food.domain.constants import AssistantTurnStatus, IntakeEventState, PathId, parse_optional_id
from DayBetes_food.domain.portion_detail import portion_carbs
from DayBetes_food.domain.search_text import normalize_search_text
from DayBetes_food.time_utils import to_local
from DayBetes_food.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.domain.assistant import RemovalCard, parse_plus_step
from DayBetes_food.services.assistant import (
    apply_preparation,
    apply_plus,
    meal_preparation_choices,
    usual_foods,
    conversation_plus_buttons,
    conversation_turns,
    plus_buttons,
    remove_proposed_food,
    resolve_conversation,
)
from DayBetes_food.services.assistant_turns import TURN_MEAL_GONE, submit_assistant_turn
from DayBetes_food.services.intake_event import repeat_meal, save_quick_add_as_dish

logger = logging.getLogger(__name__)

_MEAL_GONE = TURN_MEAL_GONE
_FOOD_GONE = "That food is no longer in this meal."
_STILL_ANSWERING = "The assistant is still answering your last message. Wait for it, then send this one."


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


# The `No meal` chats read for the list of chats, and the past chats shown (§9.11).
_MEAL_FREE_CHATS_READ = 5
_PAST_CHATS_SHOWN = 60


_PAST_CHATS_QUERY_MAX = 80


def _past_chat_text(chat, event, portions: list) -> str:
    """What the search of the past chats looks in (§9.11): the meal's name, the
    first line of the chat and the names of its foods, without accents or case."""
    parts = [chat.preview, event.name if event is not None and event.name else ""]
    parts += [portion.source.name or "" for portion in portions]
    return normalize_search_text(" ".join(parts))


def _meal_and_foods(connection, user_id: int, event_id: int | None) -> tuple:
    """The meal of the chat and its foods, for the bar (§9.11)."""
    if event_id is None:
        return None, []
    event = get_intake_event(connection, user_id, event_id)
    if event is None:
        return None, []
    return event, list_portions_by_event(connection, user_id, event_id)


def _meal_bar(
    connection,
    user_id: int,
    event_id: int | None,
    without_meal: bool,
    pending: frozenset,
    conversation=None,
    *,
    oob: bool = True,
):
    """The bar of the chat (§9.11), with the preparation values offered in `conversation`."""
    event, portions = _meal_and_foods(connection, user_id, event_id)
    preparation = meal_preparation_choices(connection, user_id, conversation)
    plates = list_intake_plates(connection, user_id, event.id) if event is not None else []
    return MealBar(
        event, portions, without_meal=without_meal, pending=pending, preparation=preparation, plates=plates, oob=oob
    )


def _chats(connection, user_id: int, current_event_id, current_conversation_id, *, oob: bool = False):
    """The list of chats (§9.11), with the carbs of each planned meal."""
    events = list_planned_intake_events(connection, user_id)
    carbs: dict[int, float] = {}
    for portion in list_portions_by_events(connection, user_id, [event.id for event in events]):
        carbs[portion.destination_id] = carbs.get(portion.destination_id, 0.0) + portion_carbs(portion)
    return ChatsModal(
        events,
        carbs,
        list_meal_free_conversations(connection, user_id, _MEAL_FREE_CHATS_READ),
        current_event_id=current_event_id,
        current_conversation_id=current_conversation_id,
        oob=oob,
    )


def _pending_since(pending, conversation_id: int | None):
    """When the message still being answered in `conversation_id` was sent, or None.
    Its rounds are stored as they end, but its pending block draws it until the
    answer: the thread leaves them out, so it does not show twice (§8.12)."""
    if pending is None or conversation_id is None or pending.conversation_id != conversation_id:
        return None
    return pending.created_at


def _turn_tail(
    connection, user_id: int, conversation_id: int | None, unseen, deferred_seen: list[int] | None = None
) -> list:
    """What the thread of `conversation_id` draws after its turns (§8.12): a message
    of this conversation still being answered, or a failed one the page never
    showed. A new chat has no conversation until its answer: its pending message
    belongs to the thread without one. With `deferred_seen` (a preload), the
    failed turn shown is listed there instead of marked seen now."""
    tail = []
    if unseen is not None and unseen.status is AssistantTurnStatus.FAILED and unseen.conversation_id == conversation_id:
        tail.append(FailedTurnBlock(unseen))
        if deferred_seen is not None:
            deferred_seen.append(unseen.id)
        else:
            mark_assistant_turn_seen(connection, user_id, unseen.id)
    pending = get_pending_assistant_turn(connection, user_id)
    if pending is not None and pending.conversation_id == conversation_id:
        tail.append(PendingTurnBlock(pending))
    return tail


def setup_assistant_routes(rt):
    @rt("/assistant")
    def get(
        request: Request, intake_event_id: str = "", conversation_id: str = "", new_meal: str = "", new_chat: str = ""
    ):
        """The page (§9.11): the chosen conversation, else the chosen meal's, else the
        conversation of the latest planned meal, as in Food. `new_meal` and
        `new_chat` (with `No meal`) start an empty one."""
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        chosen_conversation = parse_optional_id(conversation_id, "conversation")
        chosen_event, without_meal = parse_meal_choice(intake_event_id)
        # A preload (frontend §12, §13) may never be shown: it writes nothing,
        # and the page marks its turns seen when it is shown
        # (POST /assistant/turn/{id}/seen; code_conventions.md §9.2).
        deferred_seen = [] if request.headers.get("HX-Preloaded") == "true" else None

        with get_connection() as connection:
            events = list_planned_intake_events(connection, int(user_id))
            conversation = None
            selected = None
            # Coming back after leaving while it answered (§8.12): the outcome the
            # page never showed opens its conversation, and a new chat still
            # waiting for its first answer opens empty, with that message.
            unseen = get_latest_unseen_assistant_turn(connection, int(user_id))
            pending_turn = get_pending_assistant_turn(connection, int(user_id))
            waiting_new_chat = pending_turn is not None and pending_turn.conversation_id is None
            if not chosen_conversation and not new_meal and not new_chat:
                if unseen is not None and unseen.conversation_id is not None:
                    chosen_conversation = unseen.conversation_id
                elif pending_turn is not None and pending_turn.conversation_id is not None:
                    chosen_conversation = pending_turn.conversation_id
            if new_meal:
                without_meal = False
            elif not (without_meal and new_chat):
                selected = _selected_meal(events, chosen_event)
                if not intake_event_id and not chosen_conversation and events:
                    selected = events[0].id
                try:
                    conversation = resolve_conversation(
                        connection, int(user_id), chosen_conversation, selected, latest_without_meal=without_meal
                    )
                except (NotFoundError, ConflictError):
                    # Its meal was confirmed or deleted meanwhile: start on a new meal.
                    conversation, selected, without_meal = None, None, False
                if waiting_new_chat and not conversation_id:
                    # Its message belongs to a chat that has no conversation yet.
                    conversation, selected = None, None
                if conversation is not None:
                    selected = conversation.intake_event_id
                    without_meal = conversation.without_meal
            conversation_key = conversation.id if conversation else None
            event, portions = _meal_and_foods(connection, int(user_id), selected)
            turns = (
                conversation_turns(
                    connection, int(user_id), conversation_key, before=_pending_since(pending_turn, conversation_key)
                )
                if conversation
                else []
            )
            if (
                unseen is not None
                and unseen.status is AssistantTurnStatus.DONE
                and unseen.conversation_id == conversation_key
            ):
                # Its answer is one of the turns drawn now.
                if deferred_seen is not None:
                    deferred_seen.append(unseen.id)
                else:
                    mark_assistant_turn_seen(connection, int(user_id), unseen.id)
            tail = _turn_tail(connection, int(user_id), conversation_key, unseen, deferred_seen)
            pending = _pending_review(connection, int(user_id))
            buttons = plus_buttons(connection, int(user_id), conversation)
            chats = _chats(connection, int(user_id), selected, conversation_key)
            preparation = meal_preparation_choices(connection, int(user_id), conversation)
            usual = usual_foods(connection, int(user_id)) if not turns and not tail and not without_meal else []
            plates = list_intake_plates(connection, int(user_id), event.id) if event is not None else []
        content = AssistantPage(
            event,
            portions,
            conversation_key,
            turns,
            chats,
            without_meal=without_meal,
            pending=pending,
            plus_buttons=buttons,
            preparation=preparation,
            usual=usual,
            plates=plates,
            tail=tail,
            mark_seen=tuple(deferred_seen or ()),
        )
        return render_page(request, content, show_cart=False)

    @rt("/assistant/turn/{turn_id}/seen")
    def post(request: Request, turn_id: PathId):
        """A preloaded page of DiaBot, shown (code_conventions.md §9.2): marks the
        turn it drew seen, as showing it does without a preload. Not the user's,
        or already seen: nothing changes. Answers nothing."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            mark_assistant_turn_seen(connection, int(user_id), turn_id)
        return HTMLResponse(status_code=204)

    @rt("/assistant/history")
    def get(request: Request, q: str = ""):
        """The past chats (§9.11): confirmed meals and `No meal` chats, hidden ones too, by day."""
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        with get_connection() as connection:
            chats = list_past_conversations(connection, int(user_id), _PAST_CHATS_SHOWN)
            events = {}
            for chat in chats:
                if chat.event_id is None:
                    continue
                event = get_intake_event(connection, int(user_id), chat.event_id)
                if event is not None:
                    events[chat.event_id] = event
            portions: dict[int, list] = {}
            for portion in list_portions_by_events(connection, int(user_id), list(events)):
                portions.setdefault(portion.destination_id, []).append(portion)
        query = normalize_search_text(q)[:_PAST_CHATS_QUERY_MAX]
        days: list = []
        for chat in chats:
            event = events.get(chat.event_id) if chat.event_id is not None else None
            if chat.event_id is not None and event is None:
                continue
            if query and query not in _past_chat_text(chat, event, portions.get(chat.event_id, [])):
                continue
            when = event.meal_time if event is not None and event.meal_time else chat.updated_at
            day = to_local(when).date()
            if not days or days[-1][0] != day:
                days.append((day, []))
            days[-1][1].append((chat, event, portions.get(event.id, []) if event is not None else []))
        return render_page(request, PastChatsPage(days, q.strip()[:_PAST_CHATS_QUERY_MAX]), show_cart=False)

    @rt("/assistant/history/{conversation_id}/repeat")
    def post(request: Request, conversation_id: PathId):
        """`Repeat today` (§9.11): a new planned meal for now with what that confirmed
        meal served; opens its chat. Repeating it makes another meal (§9.6), which
        is deleted in the cart."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            conversation = get_assistant_conversation(connection, int(user_id), conversation_id)
            if conversation is None or conversation.intake_event_id is None:
                return app_error_response(request, NotFoundError, "Chat not found.")
            try:
                with connection.transaction():
                    event_id = repeat_meal(connection, int(user_id), conversation.intake_event_id)
            except NotFoundError as error:
                return app_error_response(request, NotFoundError, str(error))
        return HTMLResponse("", headers=hx_location(f"/assistant?{urlencode({'intake_event_id': event_id})}"))

    @rt("/assistant/conversations/{conversation_id}/hide")
    def post(request: Request, conversation_id: PathId):
        """Delete a chat from the list of chats (§9.11): hidden, kept for the study,
        still in the past chats. Answers nothing: the row goes. Repeating it is a
        no-op (§9.6)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                hide_assistant_conversation(connection, int(user_id), conversation_id)
            except NotFoundError as error:
                return app_error_response(request, NotFoundError, str(error))
        return HTMLResponse("")

    @rt("/assistant/history/{conversation_id}")
    def get(request: Request, conversation_id: PathId):
        """A past chat, read-only (§9.11). A conversation whose meal is still
        planned opens in the live page instead."""
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        with get_connection() as connection:
            conversation = get_assistant_conversation(connection, int(user_id), conversation_id)
            if conversation is None or conversation.intake_event_id is None:
                raise NotFoundError("Chat not found.")
            event, portions = _meal_and_foods(connection, int(user_id), conversation.intake_event_id)
            if event is None:
                raise NotFoundError("Chat not found.")
            if event.state is IntakeEventState.PLANNED:
                return Redirect(f"/assistant?{urlencode({'conversation_id': conversation.id})}")
            turns = conversation_turns(connection, int(user_id), conversation.id)
            pending = _pending_review(connection, int(user_id))
        return render_page(request, PastChatPage(event, portions, turns, pending, conversation.id), show_cart=False)

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
            conversation_key = conversation.id if conversation else None
            turns = (
                conversation_turns(
                    connection,
                    int(user_id),
                    conversation.id,
                    before=_pending_since(get_pending_assistant_turn(connection, int(user_id)), conversation_key),
                )
                if conversation
                else []
            )
            # A pending new chat belongs only to the `New chat` / `New meal` view.
            tail = (
                _turn_tail(connection, int(user_id), conversation_key, None)
                if conversation_key is not None or new_chat or not intake_event_id
                else []
            )
            pending = _pending_review(connection, int(user_id))
            buttons = plus_buttons(connection, int(user_id), conversation)
            bar_event = conversation.intake_event_id if conversation else event_id
            bar_without = conversation.without_meal if conversation else without_meal
            bar = _meal_bar(connection, int(user_id), bar_event, bar_without, pending, conversation)
            meal_rows = frozenset(portion.id for portion in _meal_and_foods(connection, int(user_id), bar_event)[1])
        response = render_fragment(
            (
                AssistantThread(
                    turns,
                    conversation_key,
                    pending,
                    new_meal=bar_event is None and not bar_without,
                    tail=tail,
                    meal_rows=meal_rows,
                ),
                PlusRow(buttons, conversation_key, oob=True),
                bar,
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
        """One message to the assistant (§8.12). It is queued and answered in the
        background; the response, at once, is the message with `Thinking`, which
        asks for its answer every 2 s (`/assistant/turn/{id}`). Leaving the page
        does not stop it. One message at a time per user: another one while it
        answers is a `409`.

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
                turn_id = submit_assistant_turn(
                    connection,
                    int(user_id),
                    conversation_id=chosen_conversation_id,
                    event_id=chosen_event_id,
                    without_meal=without_meal,
                    request=turn_request,
                )
            except ConflictError:
                return app_error_response(request, ConflictError, _STILL_ANSWERING)
            except NotFoundError:
                return app_error_response(request, NotFoundError, _MEAL_GONE)
            turn = get_assistant_turn(connection, int(user_id), turn_id)
        return render_fragment(PendingTurnBlock(turn))

    @rt("/assistant/turn/{turn_id}")
    def get(request: Request, turn_id: PathId):
        """A message answered in the background (§8.12), asked for every 2 s by its
        block: `204` while it waits (htmx swaps nothing); its answer, with the
        conversation id, the +1 row, the meal's bar and, if it created the meal,
        the list of chats out of band, when it is stored; or
        the failed block. Showing the outcome marks it seen."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            turn = get_assistant_turn(connection, int(user_id), turn_id)
            if turn is None:
                # Not the user's or gone: stop polling with an empty block.
                return HTMLResponse(f'<div id="{assistant_turn_dom_id(turn_id)}"></div>')
            if turn.pending:
                return HTMLResponse(status_code=204)
            mark_assistant_turn_seen(connection, int(user_id), turn.id)
            if turn.status is AssistantTurnStatus.FAILED:
                return render_fragment(FailedTurnBlock(turn))
            turns = conversation_turns(connection, int(user_id), turn.conversation_id) if turn.conversation_id else []
            pending = _pending_review(connection, int(user_id))
            conversation = (
                get_assistant_conversation(connection, int(user_id), turn.conversation_id)
                if turn.conversation_id
                else None
            )
            buttons = conversation_plus_buttons(connection, int(user_id), turn.conversation_id)
            # The bar carries the meal, so a meal created now is the one the next
            # message continues; the list of chats then shows it too (§9.11).
            fragments = [
                ConversationIdInput(turn.conversation_id, oob=True),
                PlusRow(buttons, turn.conversation_id, oob=True),
                _meal_bar(
                    connection,
                    int(user_id),
                    turn.intake_event_id or (conversation.intake_event_id if conversation else None),
                    bool(conversation and conversation.without_meal),
                    pending,
                    conversation,
                ),
            ]
            if turn.meal_created:
                fragments.append(
                    _chats(connection, int(user_id), turn.intake_event_id, turn.conversation_id, oob=True)
                )
            if turns:
                fragments.insert(
                    0, TurnBlock(turns[-1], turn.conversation_id, list(turn.notices), pending, latest=True)
                )
        response = render_fragment(tuple(fragments))
        response.headers["HX-Replace-Url"] = _assistant_url(turn.conversation_id, "")
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
            conversation = get_assistant_conversation(connection, int(user_id), chosen_conversation_id)
            pending = _pending_review(connection, int(user_id))
            bar = _meal_bar(
                connection,
                int(user_id),
                conversation.intake_event_id if conversation else None,
                False,
                pending,
                conversation,
            )
        # The meal's foods in the bar change with the tap too (§9.11).
        return render_fragment((PlusRow(buttons, chosen_conversation_id), bar))

    @rt("/assistant/preparation/{portion_id}")
    def post(request: Request, portion_id: PathId, field: str = "", value: str = "", conversation_id: str = ""):
        """A preparation value picked with a tap (§8.12, "Preparación con un toque"):
        one of those the assistant offered for that row and field, set without the
        model. Answers the bar. Repeating it leaves the same value (§9.6)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            chosen_conversation_id = parse_optional_id(conversation_id, "conversation")
            if chosen_conversation_id is None:
                raise ValidationError("Conversation not found.")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        with get_connection() as connection:
            try:
                with connection.transaction():
                    apply_preparation(
                        connection, int(user_id), chosen_conversation_id, portion_id, field.strip(), value.strip()
                    )
            except NotFoundError as error:
                return app_error_response(request, NotFoundError, str(error))
            except ConflictError:
                return app_error_response(request, ConflictError, _MEAL_GONE)
            except ValidationError as error:
                # A merge over the limit (measurement §4.6.4).
                return app_error_response(request, ValidationError, str(error))
            conversation = get_assistant_conversation(connection, int(user_id), chosen_conversation_id)
            bar = _meal_bar(
                connection,
                int(user_id),
                conversation.intake_event_id if conversation else None,
                False,
                _pending_review(connection, int(user_id)),
                conversation,
                oob=False,
            )
        return render_fragment(bar)

    @rt("/assistant/remove/{portion_id}")
    def post(request: Request, portion_id: PathId, conversation_id: str = ""):
        """Remove a food DiaBot proposed to remove (§8.12, "Quitar del carrito"): the
        user's tap on its card. Answers the row, marked removed, with the bar and the
        +1 row out of band. Repeating it -> 404, the food is already gone (§9.6)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            chosen_conversation_id = parse_optional_id(conversation_id, "conversation")
            if chosen_conversation_id is None:
                raise ValidationError("Conversation not found.")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        with get_connection() as connection:
            try:
                with connection.transaction():
                    name = remove_proposed_food(connection, int(user_id), chosen_conversation_id, portion_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, _FOOD_GONE)
            except ConflictError:
                return app_error_response(request, ConflictError, _MEAL_GONE)
            except ValidationError:
                # Giving it back leaves its container over the limit (measurement §4.8.6).
                return app_error_response(request, ValidationError, "That food does not fit back in its container.")
            conversation = get_assistant_conversation(connection, int(user_id), chosen_conversation_id)
            card = next(
                (
                    card
                    for turn in conversation_turns(connection, int(user_id), chosen_conversation_id)
                    for card in turn.removals
                    if card.portion_id == portion_id
                ),
                RemovalCard(portion_id, name, None),
            )
            fragments = (
                RemovalRow(card, chosen_conversation_id, removed=True),
                _meal_bar(
                    connection,
                    int(user_id),
                    conversation.intake_event_id if conversation else None,
                    False,
                    _pending_review(connection, int(user_id)),
                    conversation,
                ),
                PlusRow(conversation_plus_buttons(connection, int(user_id), chosen_conversation_id), chosen_conversation_id, oob=True),
            )
        response = render_fragment(fragments)
        response.headers["HX-Trigger"] = "dbReviewChanged"
        return response

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
