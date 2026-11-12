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

from DayBetes_food.domain.catalog import CATALOG_NAME_MAX_LENGTH, parse_barcode, parse_cooking_factor
from DayBetes_food.domain.constants import (
    AssistantDraftSource,
    AssistantRole,
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodEntryType,
    FoodPhysicalState,
    MacrosSource,
    MealType,
)
from DayBetes_food.domain.food import (
    FOOD_DEFAULT_PORTION_RANGE,
    FOOD_SUBTYPE_MAX_LENGTH,
    FoodPrefill,
    normalize_food_text,
)
from DayBetes_food.domain.manual_intake import parse_manual_intake_name, require_carbs
from DayBetes_food.domain.nutrition import (
    NUTRIENT_LIMITS,
    NutrientValues,
    check_number,
    nutrients_from_totals,
    validate_nutrient_relations,
)
from DayBetes_food.domain.portion_detail import parse_amount_grams
from DayBetes_food.domain.recipe import (
    parse_recipe_extra_meal_types,
    parse_recipe_meal_type,
    parse_recipe_name,
    parse_recipe_notes,
    parse_recipe_servings,
)
from DayBetes_food.domain.recipe_plate import parse_recipe_plate_name
from DayBetes_food.errors import ValidationError

# What one message of the user can carry (frontend_conventions.md §9.11).
ASSISTANT_TEXT_MAX_LENGTH = 8000  # room for a pasted recipe (§8.12, "Recetas")
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
# Lines of what a tool changed in the meal (§8.12, "Edición de la comida").
TOOL_RESULT_CHANGED = "changed"

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


def tool_int(value, field: str, *, required: bool = False) -> int | None:
    """A whole number of a tool input, not a boolean. None passes unless required."""
    if value is None:
        if required:
            raise ValidationError(f"{field} is required.")
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be a whole number.")
    return value


def tool_id(value, field: str) -> int:
    """A required id of a tool input: a positive whole number."""
    number = tool_int(value, field, required=True)
    if number <= 0:
        raise ValidationError(f"{field} must be a positive whole number.")
    return number


def tool_bool(value, field: str) -> bool | None:
    """A true/false of a tool input. None passes."""
    if value is None or isinstance(value, bool):
        return value
    raise ValidationError(f"{field} must be true or false.")


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
# Other nutrients of a draft: tool input name -> NutrientValues field.
_DRAFT_OTHER_NUTRIENTS = {"caffeine_mg_100g": "caffeine", "alcohol_g_100g": "alcohol"}

# The drafts whose values the model writes itself (§8.12, "Alimentos nuevos"):
# their U1 comes from the source; Ciqual and OFF take PREFILL_MACROS_SOURCE.
DRAFT_MACROS_SOURCE = {
    AssistantDraftSource.LABEL: MacrosSource.LABEL,
    AssistantDraftSource.ESTIMATE: MacrosSource.AI_ESTIMATE,
}


@dataclass(frozen=True)
class FoodDraftExtras:
    """What the model adds to any food draft, also on top of a Ciqual or OFF
    prefill, which only takes the ones its source does not bring (§8.12)."""

    category: FoodCategory | None
    subtype: str | None
    initial_state: FoodPhysicalState | None
    cooking_factor: float | None
    barcode: str | None


def _tool_enum(enum_cls, value, field: str):
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError as error:
        raise ValidationError(f"{field} must be one of: {', '.join(m.value for m in enum_cls)}.") from error


def food_draft_extras(tool_input: dict) -> FoodDraftExtras:
    """The extra fields of a food draft, checked like the create form's (§7.13).

    Raises:
        ValidationError: a value out of the limits of the form, with its message.
    """
    cooking_factor = tool_number(tool_input.get("cooking_factor"), "cooking_factor")
    barcode = tool_input.get("barcode")
    if barcode is not None and not isinstance(barcode, str):
        raise ValidationError("barcode must be text.")
    return FoodDraftExtras(
        category=_tool_enum(FoodCategory, tool_input.get("category"), "category"),
        subtype=tool_text(tool_input.get("subtype"), "subtype", max_length=FOOD_SUBTYPE_MAX_LENGTH),
        initial_state=_tool_enum(FoodPhysicalState, tool_input.get("initial_state"), "initial_state"),
        cooking_factor=parse_cooking_factor(cooking_factor) if cooking_factor is not None else None,
        barcode=parse_barcode(barcode) if barcode and barcode.strip() else None,
    )


def food_draft_prefill(tool_input: dict) -> FoodPrefill:
    """The create-form prefill of a food the model wrote itself (§8.12): read from a
    nutrition label (`label`) or estimated (`estimate`).

    The user reviews it before saving, and its U1 comes from DRAFT_MACROS_SOURCE
    (study §6.3). Name and carbs per 100 g are required; a nutrient the label does
    not show or the model cannot estimate stays empty, never 0 (§8.9).

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
    for input_name, field in _DRAFT_OTHER_NUTRIENTS.items():
        values[field] = check_number(tool_number(tool_input.get(input_name), input_name), field, NUTRIENT_LIMITS[field])
    nutrients = NutrientValues(**values)
    validate_nutrient_relations(nutrients)
    extras = food_draft_extras(tool_input)
    return FoodPrefill(
        barcode=extras.barcode,
        name=name,
        brand=brand,
        category=extras.category,
        subtype=extras.subtype,
        initial_state=extras.initial_state,
        default_portion_g=serving,
        nutriscore=None,
        nova=None,
        nutrients=nutrients,
        alcohol_source_note=None,
    )


# A recipe draft (§8.12, "Recetas"): what the model proposes and the recipe
# create form shows and saves. Its ingredients are the user's foods and dishes,
# by id, or new dishes estimated by the model.
RECIPE_DRAFT_PLATES_MAX = 10
RECIPE_DRAFT_INGREDIENTS_MAX = 40
# A new dish's macros: the model gives the totals of the amount, like a quick add.
_NEW_DISH_TOTALS = {
    "calories_100g": "calories_kcal",
    "carbs_100g": "carbs_g",
    "sugars_100g": "sugars_g",
    "fats_100g": "fats_g",
    "saturated_100g": "saturated_g",
    "proteins_100g": "proteins_g",
    "fiber_100g": "fiber_g",
}
NEW_DISH_MACROS_SOURCES = (MacrosSource.AI_ESTIMATE, MacrosSource.OWN_ESTIMATE)


@dataclass(frozen=True)
class NewDishDraft:
    """A dish the user does not have, created when the recipe is saved: a reusable
    `manual_intake`, never a quick add (§11.2.3)."""

    name: str
    nutrients: NutrientValues  # per 100 g, converted from the totals (measurement §5.4)
    macros_source: MacrosSource


@dataclass(frozen=True)
class RecipeIngredientDraft:
    entry_type: FoodEntryType | None  # catalog or manual_intake; None for a new dish
    entry_id: int | None
    new_dish: NewDishDraft | None
    grams: float
    cooking: CookingMethod | None
    final_state: FoodPhysicalState | None
    conservation: ConservationMethod | None
    is_cooked_weight: bool


@dataclass(frozen=True)
class RecipePlateDraft:
    name: str | None
    ingredients: tuple[RecipeIngredientDraft, ...]


@dataclass(frozen=True)
class RecipeDraft:
    name: str
    meal_type: MealType | None
    extra_meal_types: tuple[MealType, ...]
    servings: int | None
    notes: str | None
    plates: tuple[RecipePlateDraft, ...]

    @property
    def ingredient_count(self) -> int:
        return sum(len(plate.ingredients) for plate in self.plates)


def _new_dish_draft(raw, grams: float) -> NewDishDraft:
    if not isinstance(raw, dict):
        raise ValidationError("new_dish must be an object.")
    totals = {}
    for field, input_name in _NEW_DISH_TOTALS.items():
        value = tool_number(raw.get(input_name), input_name, required=(input_name == "carbs_g"))
        if value is not None and value < 0:
            raise ValidationError(f"{input_name} cannot be negative.")
        totals[field] = value
    nutrients = nutrients_from_totals(totals, grams)
    require_carbs(nutrients)
    macros_source = _tool_enum(MacrosSource, raw.get("macros_source"), "macros_source") or MacrosSource.AI_ESTIMATE
    if macros_source not in NEW_DISH_MACROS_SOURCES:
        raise ValidationError("macros_source of a new dish must be ai_estimate or own_estimate.")
    return NewDishDraft(parse_manual_intake_name(raw.get("name")), nutrients, macros_source)


def _ingredient_draft(raw) -> RecipeIngredientDraft:
    if not isinstance(raw, dict):
        raise ValidationError("Each ingredient must be an object.")
    grams = parse_amount_grams(tool_number(raw.get("grams"), "grams", required=True))
    has_entry = raw.get("entry_id") is not None
    has_new = raw.get("new_dish") is not None
    if has_entry == has_new:
        raise ValidationError("Give each ingredient either entry_type and entry_id, or new_dish.")
    entry_type = entry_id = new_dish = None
    if has_entry:
        entry_type = _tool_enum(FoodEntryType, raw.get("entry_type"), "entry_type")
        if entry_type not in (FoodEntryType.CATALOG, FoodEntryType.MANUAL_INTAKE):
            raise ValidationError("entry_type must be catalog or manual_intake.")
        entry_id = tool_id(raw.get("entry_id"), "entry_id")
    else:
        new_dish = _new_dish_draft(raw["new_dish"], grams)
    is_cooked_weight = bool(tool_bool(raw.get("is_cooked_weight"), "is_cooked_weight"))
    if is_cooked_weight and entry_type is not FoodEntryType.CATALOG:
        raise ValidationError("Cooked weight only applies to catalog foods.")
    return RecipeIngredientDraft(
        entry_type=entry_type,
        entry_id=entry_id,
        new_dish=new_dish,
        grams=grams,
        cooking=_tool_enum(CookingMethod, raw.get("cooking"), "cooking"),
        final_state=_tool_enum(FoodPhysicalState, raw.get("final_state"), "final_state"),
        conservation=_tool_enum(ConservationMethod, raw.get("conservation"), "conservation"),
        is_cooked_weight=is_cooked_weight,
    )


def recipe_draft(tool_input: dict) -> RecipeDraft:
    """A recipe draft written by the model, checked like the recipe form (§7.13).
    It is read again from the stored tool call when the form opens and when it is
    saved, never from the browser.

    Raises:
        ValidationError: a value out of the limits of the form, with its message.
    """
    raw_plates = tool_input.get("plates")
    if not isinstance(raw_plates, list) or not raw_plates:
        raise ValidationError("plates must be a list with at least one plate.")
    if len(raw_plates) > RECIPE_DRAFT_PLATES_MAX:
        raise ValidationError(f"A recipe draft can have at most {RECIPE_DRAFT_PLATES_MAX} plates.")
    plates = []
    for raw_plate in raw_plates:
        if not isinstance(raw_plate, dict) or not isinstance(raw_plate.get("ingredients"), list):
            raise ValidationError("Each plate needs a list of ingredients.")
        if not raw_plate["ingredients"]:
            raise ValidationError("A plate cannot be empty.")
        plates.append(
            RecipePlateDraft(
                name=parse_recipe_plate_name(raw_plate.get("name")),
                ingredients=tuple(_ingredient_draft(raw) for raw in raw_plate["ingredients"]),
            )
        )
    if sum(len(plate.ingredients) for plate in plates) > RECIPE_DRAFT_INGREDIENTS_MAX:
        raise ValidationError(f"A recipe draft can have at most {RECIPE_DRAFT_INGREDIENTS_MAX} ingredients.")
    meal_type = parse_recipe_meal_type(tool_input.get("meal_type") or "")
    extra = tool_input.get("extra_meal_types") or []
    if not isinstance(extra, list):
        raise ValidationError("extra_meal_types must be a list.")
    servings = tool_int(tool_input.get("servings"), "servings")
    return RecipeDraft(
        name=parse_recipe_name(tool_input.get("name")),
        meal_type=meal_type,
        extra_meal_types=parse_recipe_extra_meal_types(extra, meal_type),
        servings=parse_recipe_servings(servings if servings is not None else ""),
        notes=parse_recipe_notes(tool_input.get("notes") if isinstance(tool_input.get("notes"), str) else None),
        plates=tuple(plates),
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
    preparation: str | None = None  # what the user said of how it was prepared


@dataclass(frozen=True)
class DraftCard:
    """A new food or recipe prepared for the user to review: opens its create form."""

    source: str  # AssistantDraftSource of a food; "recipe" for a recipe
    name: str
    code: str | None
    message_id: int  # the assistant message whose tool call holds the draft
    tool_use_id: str
    ingredients: int | None = None  # of a recipe draft


@dataclass(frozen=True)
class TurnView:
    """One message of the user and everything the assistant did for it."""

    user_text: str
    had_photo: bool
    replies: list[str]
    added: list[AddedCard]
    drafts: list[DraftCard]
    changed: list[str]


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
            turns.append(TurnView("\n".join(texts).strip(), had_photo, [], [], [], []))
            continue
        if not turns:
            continue
        turn = turns[-1]
        # Only the final answer is shown: text written next to a tool call is the
        # model thinking aloud ("Need to search foods first"), not a reply (§9.11).
        calls_tools = any(block.get("type") == "tool_use" for block in message.content)
        for block in message.content:
            kind = block.get("type")
            if kind == "text" and message.role is AssistantRole.ASSISTANT and not calls_tools:
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
                preparation=str(added["preparation"]) if added.get("preparation") else None,
            )
        )
    changed = result.get(TOOL_RESULT_CHANGED)
    if isinstance(changed, list):
        turn.changed.extend(str(line) for line in changed if isinstance(line, str) and line)
    draft = result.get(TOOL_RESULT_DRAFT)
    tool_use_id = str(block.get("tool_use_id", ""))
    if isinstance(draft, dict) and draft.get("name") and tool_use_id in tool_message:
        ingredients = draft.get("ingredients")
        turn.drafts.append(
            DraftCard(
                source=str(draft.get("source")),
                name=str(draft["name"]),
                code=draft.get("code"),
                message_id=tool_message[tool_use_id],
                tool_use_id=tool_use_id,
                ingredients=ingredients if isinstance(ingredients, int) and not isinstance(ingredients, bool) else None,
            )
        )


def draft_tool_input(message: AssistantMessageRead, tool_use_id: str, tool_name: str) -> dict | None:
    """The input of the call `tool_use_id` of `tool_name` in an assistant message, or None.
    A draft is read from here, never from the browser (§7.13)."""
    if message.role is not AssistantRole.ASSISTANT:
        return None
    for block in message.content:
        if (
            block.get("type") == "tool_use"
            and block.get("id") == tool_use_id
            and block.get("name") == tool_name
            and isinstance(block.get("input"), dict)
        ):
            return block["input"]
    return None
