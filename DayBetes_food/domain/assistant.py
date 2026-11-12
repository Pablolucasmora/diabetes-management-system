"""Dataclasses and pure rules of the assistant for logging meals
(code_conventions.md §8.12, §11.2.9; frontend_conventions.md §9.11).

The assistant proposes and the user confirms: what it writes are planned
portions, and a new food is only a draft that opens the create form. This
module holds what the request carries (text, mentions, photo), the stored
conversation and the validation of the drafts the model writes. It imports no
psycopg, routes or components; the SQL-row-to-dataclass conversion lives in
DayBetes_food/database/mappers.py.
"""

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import AssistantRole, FoodEntryType
from DayBetes_food.domain.food import FOOD_DEFAULT_PORTION_RANGE, FoodPrefill, normalize_food_text
from DayBetes_food.domain.catalog import CATALOG_NAME_MAX_LENGTH
from DayBetes_food.domain.nutrition import NUTRIENT_LIMITS, NutrientValues, check_number, validate_nutrient_relations
from DayBetes_food.errors import ValidationError

# What one message of the user can carry (frontend_conventions.md §9.11).
ASSISTANT_TEXT_MAX_LENGTH = 2000
ASSISTANT_MENTIONS_MAX = 10
# One photo per message, already reduced in the browser (§8.12, cost). The API
# takes up to 5 MB per image in base64, which is about 3.75 MB of bytes.
ASSISTANT_PHOTO_MAX_BYTES = 3_750_000
ASSISTANT_PHOTO_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp")

# Rows a search tool returns to the model (§8.12, cost): compact and few.
ASSISTANT_SEARCH_RESULTS_MAX = 5

# Marks the block of a user row that the server writes (date, meal, mentions):
# the page shows the user's own text only.
ASSISTANT_CONTEXT_TAG = "<daybetes_context>"
# What a stored photo becomes: photos are never kept (§11.2.9, study §7.1).
ASSISTANT_PHOTO_PLACEHOLDER = "[The user attached a photo here. Photos are not kept.]"

# Keys of a tool result that the page shows as a card (frontend §9.11): what
# went into the cart and the draft of a new food. The page reads them back from
# the stored results, so a reopened conversation shows the same cards.
TOOL_RESULT_ADDED = "added"
TOOL_RESULT_DRAFT = "draft"

# A tool_use id as the API writes it (`toolu_...`); it travels in the URL of a
# draft (frontend §9.11), so it is checked before reaching the SQL.
_TOOL_USE_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")

# Magic numbers of the accepted photo formats: the declared content type is not proof.
_PHOTO_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


@dataclass(frozen=True)
class Mention:
    """An entry pinned with `/`: travels as type + id, never as a name, and the
    server reads it again with its visibility rule (§8.12)."""

    entry_type: FoodEntryType
    entry_id: int


@dataclass(frozen=True)
class AssistantPhoto:
    media_type: str
    data: bytes


@dataclass(frozen=True)
class AssistantTurnRequest:
    """One message of the user, already parsed (§7.1)."""

    text: str
    mentions: tuple[Mention, ...]
    photo: AssistantPhoto | None


@dataclass(frozen=True)
class AssistantConversationRead:
    id: int
    user_id: int
    intake_event_id: int | None  # None: no meal yet, or its meal was deleted
    model: str
    created_at: datetime


@dataclass(frozen=True)
class AssistantUsage:
    """Usage of one answer of the model (§8.12): stored on the `assistant` row
    and logged, never with its content (§8.3)."""

    input_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    output_tokens: int
    duration_ms: int
    stop_reason: str | None


@dataclass(frozen=True)
class AssistantMessageCreate:
    conversation_id: int
    role: AssistantRole
    content: list[dict]  # content blocks of the Claude API, photos replaced
    usage: AssistantUsage | None  # only on `assistant` rows


@dataclass(frozen=True)
class AssistantMessageRead:
    id: int
    conversation_id: int
    position: int
    role: AssistantRole
    content: list[dict]
    created_at: datetime


def parse_assistant_text(raw) -> str:
    """The text of a message: trimmed, at most ASSISTANT_TEXT_MAX_LENGTH
    characters. It may be empty when the message carries a photo or a mention."""
    text = str(raw or "").replace("\r\n", "\n").strip()
    if len(text) > ASSISTANT_TEXT_MAX_LENGTH:
        raise ValidationError(
            f"The message can have at most {ASSISTANT_TEXT_MAX_LENGTH} characters.",
            fields={"message": "too_long"},
        )
    return text


def parse_mentions(raw) -> tuple[Mention, ...]:
    """The hidden `mentions` field: a JSON list of `{entry_type, entry_id}`.
    Empty is no mentions; a repeated entry counts once; anything malformed is a
    422, never "no mentions" (§7.2)."""
    text = str(raw or "").strip()
    if not text:
        return ()
    invalid = ValidationError("The pinned foods could not be read.", fields={"mentions": "invalid"})
    try:
        items = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise invalid from exc
    if not isinstance(items, list):
        raise invalid
    mentions: list[Mention] = []
    for item in items:
        if not isinstance(item, dict):
            raise invalid
        entry_id = item.get("entry_id")
        if not isinstance(entry_id, int) or isinstance(entry_id, bool) or entry_id <= 0:
            raise invalid
        try:
            entry_type = FoodEntryType(item.get("entry_type"))
        except ValueError as exc:
            raise invalid from exc
        mention = Mention(entry_type, entry_id)
        if mention not in mentions:
            mentions.append(mention)
    if len(mentions) > ASSISTANT_MENTIONS_MAX:
        raise ValidationError(
            f"Pin at most {ASSISTANT_MENTIONS_MAX} foods in one message.", fields={"mentions": "too_many"}
        )
    return tuple(mentions)


def parse_assistant_photo(content_type, data: bytes | None) -> AssistantPhoto | None:
    """The attached photo, or None. The format is checked on the bytes, not only
    on the declared type, and the size against ASSISTANT_PHOTO_MAX_BYTES."""
    if not data:
        return None
    media_type = str(content_type or "").split(";")[0].strip().lower()
    if media_type not in ASSISTANT_PHOTO_MEDIA_TYPES:
        raise ValidationError("Attach a JPEG, PNG or WebP photo.", fields={"photo": "invalid"})
    if len(data) > ASSISTANT_PHOTO_MAX_BYTES:
        raise ValidationError("The photo is too large.", fields={"photo": "too_large"})
    if media_type == "image/webp":
        valid = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    else:
        valid = data.startswith(_PHOTO_SIGNATURES[media_type])
    if not valid:
        raise ValidationError("The photo could not be read.", fields={"photo": "invalid"})
    return AssistantPhoto(media_type, data)


def require_turn_content(request: AssistantTurnRequest) -> None:
    """A message needs something to read: text, a mention or a photo."""
    if not request.text and not request.mentions and request.photo is None:
        raise ValidationError("Write what you ate.", fields={"message": "required"})


def parse_tool_use_id(raw) -> str:
    text = str(raw or "").strip()
    if not _TOOL_USE_ID.fullmatch(text):
        raise ValidationError("Invalid draft.", fields={"draft": "invalid"})
    return text


# The model writes the drafts and the estimates: its numbers are checked like
# a form's (§7), and a wrong one goes back to it as a tool error (§8.12).


def tool_number(value, field: str, *, required: bool = False) -> float | None:
    """A number of a tool input: finite, not a boolean. None passes unless required."""
    if value is None:
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"{field} must be a number.")
    return float(value)


def tool_text(value, field: str, *, max_length: int, required: bool = False) -> str | None:
    """A text of a tool input, normalized like a food name (§7.3)."""
    if value is None:
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text.")
    text = normalize_food_text(value)
    if not text:
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    if len(text) > max_length:
        raise ValidationError(f"{field} can have at most {max_length} characters.")
    return text


_LABEL_NUTRIENTS = (
    "calories_100g",
    "carbs_100g",
    "sugars_100g",
    "fats_100g",
    "saturated_100g",
    "proteins_100g",
    "fiber_100g",
)


def label_draft_prefill(tool_input: dict) -> FoodPrefill:
    """The create-form prefill of a food read from a nutrition label (§8.12).

    The model transcribes; the user reviews before saving, so the origin of the
    macros stays `label` (study §6.3). Name and carbs per 100 g are required; a
    nutrient the label does not show stays empty, never 0 (§8.9).

    Raises:
        ValidationError: a value out of the limits of the form, with its message.
    """
    name = tool_text(tool_input.get("name"), "name", max_length=CATALOG_NAME_MAX_LENGTH, required=True)
    brand = tool_text(tool_input.get("brand"), "brand", max_length=CATALOG_NAME_MAX_LENGTH)
    serving = tool_number(tool_input.get("serving_g"), "serving_g")
    if serving is not None:
        serving = check_number(serving, "default_portion", FOOD_DEFAULT_PORTION_RANGE)
    values = {}
    for field in _LABEL_NUTRIENTS:
        number = tool_number(tool_input.get(field), field, required=(field == "carbs_100g"))
        values[field] = check_number(number, field, NUTRIENT_LIMITS[field])
    nutrients = NutrientValues(**values)
    validate_nutrient_relations(nutrients)
    return FoodPrefill(
        barcode=None,
        name=name,
        brand=brand,
        category=None,
        subtype=None,
        initial_state=None,
        default_portion_g=serving,
        nutriscore=None,
        nova=None,
        nutrients=nutrients,
        alcohol_source_note=None,
    )


def is_context_block(block: dict) -> bool:
    """Whether a text block of a user row is the one the server writes."""
    return block.get("type") == "text" and str(block.get("text", "")).startswith(ASSISTANT_CONTEXT_TAG)


@dataclass(frozen=True)
class AddedCard:
    """Something the assistant put in the cart, as its tool reported it."""

    name: str
    grams: float | None
    carbs_g: float | None
    amount_method: str | None
    servings: float | None
    kind: str | None  # None: a food or dish; "recipe" or "estimate"


@dataclass(frozen=True)
class DraftCard:
    """A new food prepared for the user to review: opens the create form."""

    source: str
    name: str
    code: str | None
    message_id: int  # the assistant message whose tool call holds a label draft
    tool_use_id: str


@dataclass(frozen=True)
class TurnView:
    """One message of the user and everything the assistant did for it."""

    user_text: str
    had_photo: bool
    replies: list[str]
    added: list[AddedCard]
    drafts: list[DraftCard]


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _starts_turn(message: AssistantMessageRead) -> bool:
    """A user row with something other than tool results is a new message of the user."""
    return message.role is AssistantRole.USER and any(block.get("type") != "tool_result" for block in message.content)


def turn_views(messages: list[AssistantMessageRead]) -> list[TurnView]:
    """The turns of a stored conversation, in order, as the page shows them."""
    turns: list[TurnView] = []
    tool_message: dict[str, int] = {}  # tool_use_id -> id of the assistant row that called it
    for message in messages:
        if _starts_turn(message):
            texts = [
                str(block.get("text", ""))
                for block in message.content
                if block.get("type") == "text" and not is_context_block(block)
                and block.get("text") != ASSISTANT_PHOTO_PLACEHOLDER
            ]
            had_photo = any(
                block.get("type") == "image" or block.get("text") == ASSISTANT_PHOTO_PLACEHOLDER
                for block in message.content
            )
            turns.append(TurnView("\n".join(texts).strip(), had_photo, [], [], []))
            continue
        if not turns:
            continue
        turn = turns[-1]
        for block in message.content:
            kind = block.get("type")
            if kind == "text" and message.role is AssistantRole.ASSISTANT:
                text = str(block.get("text", "")).strip()
                if text:
                    turn.replies.append(text)
            elif kind == "tool_use":
                tool_message[str(block.get("id"))] = message.id
            elif kind == "tool_result" and not block.get("is_error"):
                _read_tool_result(turn, block, tool_message)
    return turns


def _read_tool_result(turn: TurnView, block: dict, tool_message: dict[str, int]) -> None:
    try:
        result = json.loads(block.get("content") or "")
    except (TypeError, ValueError):
        return
    if not isinstance(result, dict):
        return
    added = result.get(TOOL_RESULT_ADDED)
    if isinstance(added, dict) and added.get("name"):
        turn.added.append(
            AddedCard(
                name=str(added["name"]),
                grams=_number(added.get("grams")),
                carbs_g=_number(added.get("carbs_g")),
                amount_method=added.get("amount_method"),
                servings=_number(added.get("servings")),
                kind=added.get("kind"),
            )
        )
    draft = result.get(TOOL_RESULT_DRAFT)
    tool_use_id = str(block.get("tool_use_id", ""))
    if isinstance(draft, dict) and draft.get("name") and tool_use_id in tool_message:
        turn.drafts.append(
            DraftCard(
                source=str(draft.get("source")),
                name=str(draft["name"]),
                code=draft.get("code"),
                message_id=tool_message[tool_use_id],
                tool_use_id=tool_use_id,
            )
        )


def label_draft_input(message: AssistantMessageRead, tool_use_id: str) -> dict | None:
    """The input of the label draft `tool_use_id` in an assistant message, or None."""
    if message.role is not AssistantRole.ASSISTANT:
        return None
    for block in message.content:
        if (
            block.get("type") == "tool_use"
            and block.get("id") == tool_use_id
            and block.get("name") == "draft_new_food"
            and isinstance(block.get("input"), dict)
            and block["input"].get("source") == "label"
        ):
            return block["input"]
    return None
