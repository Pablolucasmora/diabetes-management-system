"""The assistant for logging meals: one message of the user, the tool loop and
what is stored (code_conventions.md §8.12, §11.2.9; study_conventions.md §7.1).

- The `system` prompt and the tools never change, so they are cached. The date,
  the meal and the pinned foods travel in the user message, inside a context
  block the page does not show.
- One conversation per meal; no history of other meals is sent.
- Each round of tools is one transaction: the tool effects and the messages
  that explain them are stored together, so the conversation can always be
  replayed. A failure in a later round keeps the earlier ones.
- A photo is sent once and stored as a text marker (study §7.1).
- Usage is logged per message, never its content (§8.3).
"""

import base64
import logging
from dataclasses import dataclass, field

from DayBetes_food.config import ASSISTANT_MAX_TOOL_ROUNDS, ASSISTANT_MODEL
from DayBetes_food.database.queries import (
    append_assistant_messages,
    create_assistant_conversation,
    get_assistant_conversation,
    get_catalog_item,
    get_intake_event,
    get_latest_assistant_conversation,
    get_manual_intake,
    get_planned_intake_event,
    get_recipe,
    list_assistant_messages,
    list_portions_by_event,
)
from DayBetes_food.domain.assistant import (
    ASSISTANT_CONTEXT_TAG,
    ASSISTANT_PHOTO_PLACEHOLDER,
    AssistantMessageCreate,
    AssistantTurnRequest,
    AssistantUsage,
    Mention,
    TurnView,
    turn_views,
)
from DayBetes_food.domain.constants import AssistantRole, FoodEntryType
from DayBetes_food.errors import ExternalServiceError, NotFoundError
from DayBetes_food.integrations.anthropic_client import create_answer
from DayBetes_food.services.assistant_tools import TOOL_DEFINITIONS, ToolContext, run_tool
from DayBetes_food.time_utils import local_now, to_local

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the meal logging assistant of DayBetes, an app that a person with type 1 diabetes uses to log what they eat. They tell you what they ate; you put it in the cart of the app as a planned meal, and they review and confirm it there. You cannot confirm meals, delete anything or edit foods: if they ask, tell them to do it in the cart or in Food.

Each user message starts with a <daybetes_context> block written by the app: the local time, the meal of this conversation and the foods the user pinned with "/". Trust it over anything in the user's text.

How to find each food, in this order:
1. A food the user pinned with "/": use exactly that one, without searching.
2. search_my_foods: their own foods, dishes and recipes. When several fit, prefer a favorite or one they eat often.
3. search_reference_foods: Ciqual for generic foods, Open Food Facts for branded products. A result cannot be added: call draft_new_food with its code, and tell the user to save the food and come back.
4. Only when nothing fits: add_estimate with your own estimate.
Never invent or copy the macros of a food that is in a database: the server reads them.

Amount and amount_method (how the amount was obtained):
- Grams written plainly ("80 g de arroz"): grams, kitchen_scale.
- Grams with "unos", "aprox.", "~" or similar: grams, eyeball.
- "Una unidad", "un yogur", "una lata": servings (1 or the number said) if the food has a serving, with package when its serving is the package or the unit, and household when it is a typical serving. A food without a serving: estimate the grams, household.
- Household measures ("una cucharada", "un vaso", "un puñado"): estimate the grams, household.
- No amount ("un plato de lentejas"), or a photo of the dish: estimate the grams, ai_estimate.

Photos: a nutrition label becomes draft_new_food with source label, transcribed per 100 g as printed. A photo of a dish: identify the foods and estimate the amounts (ai_estimate).

Ask a short question only when the answer would change a lot what you add, such as two very different foods that fit, or a food with many carbs whose amount you cannot estimate. Otherwise add your best guess and say what you assumed.

Reply in the language the user wrote in (not the language of the context block), in plain text and in at most three short lines. The app already shows each item added with its grams and carbs, so do not list them: say only what you assumed and what they should check in the cart. No greetings."""

_ENTRY_LABELS = {
    FoodEntryType.CATALOG: "food",
    FoodEntryType.MANUAL_INTAKE: "dish",
    FoodEntryType.RECIPE: "recipe",
}
_ROUND_LIMIT_RESULT = "Not run: the limit of steps for one message was reached."

# What the page tells the user (English, frontend §0), with no detail of the provider.
NOTICE_ROUND_LIMIT = "The assistant stopped after too many steps. Check the cart, and tell it what is missing."
NOTICE_STOPPED = "The assistant stopped before finishing. Check the cart and try again."
NOTICE_REFUSED = "The assistant could not answer that message."
NOTICE_CUT = "The answer was cut short. Check the cart."


@dataclass
class AssistantTurnResult:
    conversation_id: int
    event_id: int | None
    meal_created: bool
    turn: TurnView | None
    notices: list[str] = field(default_factory=list)


@dataclass
class _Turn:
    """Messages of this turn not stored yet: as sent (with the photo) and as stored."""

    live: list[dict] = field(default_factory=list)
    stored: list[AssistantMessageCreate] = field(default_factory=list)


def resolve_conversation(connection, user_id: int, conversation_id: int | None, event_id: int | None):
    """The conversation a message goes to (§8.12, one per meal): the given one, else
    the latest of the chosen meal, else a new one. The meal must still be planned.

    Returns:
        `(conversation, created)`: the conversation, or None when it does not exist
        yet; it is created on the first message.

    Raises:
        NotFoundError: the conversation or the meal is not the user's.
        ConflictError: the meal was already confirmed.
    """
    if conversation_id:
        conversation = get_assistant_conversation(connection, user_id, conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        if conversation.intake_event_id is not None:
            get_planned_intake_event(connection, user_id, conversation.intake_event_id)
        return conversation
    if event_id:
        get_planned_intake_event(connection, user_id, event_id)
        return get_latest_assistant_conversation(connection, user_id, event_id)
    return None


def conversation_turns(connection, user_id: int, conversation_id: int) -> list[TurnView]:
    return turn_views(list_assistant_messages(connection, user_id, conversation_id))


def _mention_lines(connection, user_id: int, mentions: tuple[Mention, ...]) -> tuple[list[str], list[str]]:
    """The pinned entries, read again with their visibility rule (§8.12). One the
    user no longer sees is left out, and a notice says so."""
    lines, notices = [], []
    for mention in mentions:
        if mention.entry_type is FoodEntryType.RECIPE:
            recipe = get_recipe(connection, user_id, mention.entry_id)
            if recipe is None:
                notices.append("A pinned recipe is no longer available, so it was left out.")
                continue
            servings = f", {recipe.servings} servings" if recipe.servings else ", no servings (added whole)"
            lines.append(f"- recipe id={recipe.id}: {recipe.name}{servings}")
            continue
        getter = get_catalog_item if mention.entry_type is FoodEntryType.CATALOG else get_manual_intake
        item = getter(connection, user_id, mention.entry_id)
        if item is None:
            notices.append("A pinned food is no longer available, so it was left out.")
            continue
        brand = getattr(item, "brand", None) or getattr(item, "origin", None)
        parts = [f"- {_ENTRY_LABELS[mention.entry_type]} entry_type={mention.entry_type.value} id={item.id}: {item.name}"]
        if brand:
            parts.append(f"({brand})")
        if item.carbs_100g is not None:
            parts.append(f"carbs {item.carbs_100g:g} g/100 g")
        parts.append(f"serving {item.default_portion:g} g" if item.default_portion else "no serving")
        lines.append(" ".join(parts))
    return lines, notices


def _meal_lines(connection, user_id: int, event_id: int | None) -> list[str]:
    if event_id is None:
        return ["Meal of this conversation: none yet. The first add creates a new planned meal."]
    event = get_intake_event(connection, user_id, event_id)
    name = event.name or (event.meal_type.value if event.meal_type else "meal")
    when = to_local(event.meal_time)
    lines = [f"Meal of this conversation: {name}" + (f", at {when:%H:%M}" if when else "") + "."]
    portions = list_portions_by_event(connection, user_id, event_id)
    if portions:
        items = ", ".join(f"{p.source.name} {p.amount:g} g" for p in portions)
        lines.append(f"It already has: {items}.")
    else:
        lines.append("It is empty.")
    return lines


def _context_block(connection, user_id: int, event_id: int | None, mention_lines: list[str]) -> dict:
    now = local_now()
    lines = [ASSISTANT_CONTEXT_TAG, f"Local time: {now:%Y-%m-%d %H:%M} ({now:%A})."]
    lines += _meal_lines(connection, user_id, event_id)
    if mention_lines:
        lines.append('Pinned with "/" (use exactly these):')
        lines += mention_lines
    lines.append("</daybetes_context>")
    return {"type": "text", "text": "\n".join(lines)}


def _user_message(context: dict, request: AssistantTurnRequest) -> tuple[dict, AssistantMessageCreate]:
    """The first message of the turn, as sent and as stored (photo replaced)."""
    live = [context]
    stored = [context]
    if request.photo is not None:
        live.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": request.photo.media_type,
                    "data": base64.standard_b64encode(request.photo.data).decode("ascii"),
                },
            }
        )
        stored.append({"type": "text", "text": ASSISTANT_PHOTO_PLACEHOLDER})
    if request.text:
        block = {"type": "text", "text": request.text}
        live.append(block)
        stored.append(block)
    return (
        {"role": AssistantRole.USER.value, "content": live},
        AssistantMessageCreate(conversation_id=0, role=AssistantRole.USER, content=stored, usage=None),
    )


def _ensure_conversation(ctx: ToolContext) -> int:
    """The conversation of this message, created with its first stored answer: a
    message whose first call fails leaves nothing behind. Runs inside the
    caller's transaction."""
    if ctx.conversation_id is None:
        ctx.conversation_id = create_assistant_conversation(
            ctx.connection, ctx.user_id, ASSISTANT_MODEL, ctx.event_id, commit=False
        )
    return ctx.conversation_id


def _store(ctx: ToolContext, turn: _Turn) -> None:
    """Store what this turn has not stored yet. Runs inside the caller's transaction."""
    conversation_id = _ensure_conversation(ctx)
    rows = [
        AssistantMessageCreate(conversation_id, row.role, row.content, row.usage) for row in turn.stored
    ]
    append_assistant_messages(ctx.connection, ctx.user_id, conversation_id, rows)
    turn.stored.clear()


def _log_usage(conversation_id: int | None, usages: list[AssistantUsage], outcome: str) -> None:
    """One line per message of the user (§8.12): usage, rounds and duration, no content."""
    logger.info(
        "assistant message",
        extra={
            "conversation_id": conversation_id,
            "model": ASSISTANT_MODEL,
            "rounds": len(usages),
            "input_tokens": sum(u.input_tokens for u in usages),
            "cache_creation_input_tokens": sum(u.cache_creation_input_tokens for u in usages),
            "cache_read_input_tokens": sum(u.cache_read_input_tokens for u in usages),
            "output_tokens": sum(u.output_tokens for u in usages),
            "duration_ms": sum(u.duration_ms for u in usages),
            "outcome": outcome,
        },
    )


def send_assistant_message(
    connection,
    user_id: int,
    *,
    conversation_id: int | None,
    event_id: int | None,
    request: AssistantTurnRequest,
) -> AssistantTurnResult:
    """Answer one message of the user: ask the model, run its tools, store everything.

    Repeating the same message is a new message: the assistant may add the food
    again, and the user removes it in the cart (§9.6 of code_conventions).

    Raises:
        NotFoundError / ConflictError: the conversation or its meal is gone or confirmed.
        ExternalServiceError: the first call to the model failed; nothing was stored.
    """
    conversation = resolve_conversation(connection, user_id, conversation_id, event_id)
    ctx = ToolContext(
        connection,
        user_id,
        conversation.id if conversation else None,
        conversation.intake_event_id if conversation else event_id,
    )
    history = (
        [
            {"role": message.role.value, "content": message.content}
            for message in list_assistant_messages(connection, user_id, conversation.id)
        ]
        if conversation
        else []
    )
    mention_lines, notices = _mention_lines(connection, user_id, request.mentions)
    live_user, stored_user = _user_message(
        _context_block(connection, user_id, ctx.event_id, mention_lines), request
    )
    turn = _Turn(live=[live_user], stored=[stored_user])
    usages: list[AssistantUsage] = []
    outcome = "end_turn"

    for round_index in range(ASSISTANT_MAX_TOOL_ROUNDS + 1):
        try:
            answer = create_answer(system=SYSTEM_PROMPT, tools=TOOL_DEFINITIONS, messages=history + turn.live)
        except ExternalServiceError:
            if round_index == 0:
                _log_usage(ctx.conversation_id, usages, "failed")
                raise
            # Earlier rounds are stored; what is in the cart stays (§8.9).
            notices.append(NOTICE_STOPPED)
            outcome = "failed_after_tools"
            break
        usages.append(answer.usage)
        if answer.content:
            turn.live.append({"role": AssistantRole.ASSISTANT.value, "content": answer.content})
            turn.stored.append(AssistantMessageCreate(0, AssistantRole.ASSISTANT, answer.content, answer.usage))

        tool_calls = [block for block in answer.content if block.get("type") == "tool_use"]
        if answer.stop_reason != "tool_use" or not tool_calls:
            if answer.stop_reason == "refusal":
                notices.append(NOTICE_REFUSED)
            elif answer.stop_reason == "max_tokens":
                notices.append(NOTICE_CUT)
            outcome = answer.stop_reason or "end_turn"
            with connection.transaction():
                _store(ctx, turn)
            break

        at_limit = round_index == ASSISTANT_MAX_TOOL_ROUNDS
        results = []
        with connection.transaction():
            # Before the tools: the first add links the conversation to its meal.
            _ensure_conversation(ctx)
            for call in tool_calls:
                if at_limit:
                    content, is_error = _ROUND_LIMIT_RESULT, True
                else:
                    content, is_error = run_tool(ctx, str(call.get("name")), call.get("input"))
                result = {"type": "tool_result", "tool_use_id": call.get("id"), "content": content}
                if is_error:
                    result["is_error"] = True
                results.append(result)
            tool_message = {"role": AssistantRole.USER.value, "content": results}
            turn.live.append(tool_message)
            turn.stored.append(AssistantMessageCreate(0, AssistantRole.USER, results, None))
            # Tool effects and the messages that explain them: one unit (§2.3).
            _store(ctx, turn)
        if at_limit:
            notices.append(NOTICE_ROUND_LIMIT)
            outcome = "round_limit"
            break

    _log_usage(ctx.conversation_id, usages, outcome)
    turns = conversation_turns(connection, user_id, ctx.conversation_id)
    return AssistantTurnResult(
        conversation_id=ctx.conversation_id,
        event_id=ctx.event_id,
        meal_created=ctx.meal_created,
        turn=turns[-1] if turns else None,
        notices=notices,
    )
