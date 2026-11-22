"""Dataclasses and pure rules of the assistant for logging meals
(code_conventions.md §8.12, §11.2.9; frontend_conventions.md §9.11).

The assistant proposes and the user confirms: what it writes are planned
portions, and a new food is only a draft that opens the create form. This
module holds what the request carries (text, mentions, photo), the stored
conversation and the validation of the drafts the model writes. It imports no
psycopg, routes or components; the SQL-row-to-dataclass conversion lives in
DayBetes_food/database/mappers.py.
"""

import io
import json
import math
import re
from enum import Enum, unique
from dataclasses import dataclass, field, replace
from datetime import datetime

from PIL import Image, ImageOps, UnidentifiedImageError

from DayBetes_food.domain.catalog import CATALOG_NAME_MAX_LENGTH, parse_barcode, parse_cooking_factor
from DayBetes_food.domain.constants import (
    ASSISTANT_TURN_PENDING,
    AssistantDraftSource,
    AssistantRole,
    AssistantTurnStatus,
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodEntryType,
    NOVA_MAX,
    NOVA_MIN,
    YUKA_MAX,
    YUKA_MIN,
    AmountMethod,
    FoodPhysicalState,
    GlycemicIndex,
    MacrosSource,
    MealType,
    Nutriscore,
)
from DayBetes_food.domain.food import (
    FOOD_DEFAULT_PORTION_RANGE,
    FOOD_SUBTYPE_MAX_LENGTH,
    FoodPrefill,
    normalize_food_text,
    parse_declared_confidence,
)
from DayBetes_food.domain.manual_intake import (
    MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH,
    MANUAL_INTAKE_NAME_MAX_LENGTH,
    MANUAL_INTAKE_ORIGIN_MAX_LENGTH,
    parse_manual_intake_name,
    require_carbs,
    validate_ig_confidence,
)
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
# Up to four photos per message (decision of 2026-11-15), each already reduced in
# the browser (§8.12, cost). The API takes up to 5 MB per image in base64, which
# is about 3.75 MB of bytes.
ASSISTANT_PHOTOS_MAX = 4
ASSISTANT_PHOTO_MAX_BYTES = 3_750_000
ASSISTANT_PHOTO_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp")
# What the server sends and stores (§8.12, cost; §11.2.10): the same reduction
# as the browser, done again so a photo the browser could not reduce gets it
# too, and so no metadata (GPS position included) survives.
ASSISTANT_PHOTO_MAX_SIDE_PX = 1568
ASSISTANT_PHOTO_JPEG_QUALITY = 85
ASSISTANT_PHOTO_STORED_TYPE = "image/jpeg"
# A larger image is refused before it is decoded: a small file can declare
# huge dimensions (decompression bomb). A 48 MP phone photo fits.
ASSISTANT_PHOTO_MAX_PIXELS = 60_000_000

# Rows a search tool returns to the model (§8.12, cost): compact and few.
ASSISTANT_SEARCH_RESULTS_MAX = 5

# Marks the block of a user row that the server writes (date, meal, mentions):
# the page shows the user's own text only.
ASSISTANT_CONTEXT_TAG = "<daybetes_context>"
# What each photo becomes in its stored message (§11.2.9): the model never
# gets it again. The image itself is kept in assistant_photo (§11.2.10).
ASSISTANT_PHOTO_PLACEHOLDER = "[The user attached a photo here. It is sent only once.]"
# The marker of the rows stored before 2026-11-18, when photos were not kept.
_LEGACY_PHOTO_PLACEHOLDER = "[The user attached a photo here. Photos are not kept.]"
_PHOTO_PLACEHOLDERS = (ASSISTANT_PHOTO_PLACEHOLDER, _LEGACY_PHOTO_PLACEHOLDER)

# Keys of a tool result that the page shows as a card (frontend §9.11): what
# went into the cart and the draft of a new food. The page reads them back from
# the stored results, so a reopened conversation shows the same cards.
TOOL_RESULT_ADDED = "added"
TOOL_RESULT_DRAFT = "draft"
# A provisional food or dish created and added (§8.12, "Alimentos provisionales").
TOOL_RESULT_PROVISIONAL = "provisional"
# A quick add eaten often enough to offer saving it (§8.12, "Repeticiones").
TOOL_RESULT_REPEAT = "repeat"
REPEAT_WINDOW_DAYS = 90
REPEAT_MIN_COUNT = 3  # this one included: the third time in the window


class RepeatSaveAs(str, Enum):
    """What a repeated quick add is offered to become (§8.12)."""

    DISH = "dish"  # prepared by someone else
    RECIPE = "recipe"  # homemade
# `source` of the draft cards that are not a catalog food (frontend §9.11).
RECIPE_DRAFT_SOURCE = "recipe"
MANUAL_INTAKE_DRAFT_SOURCE = "manual_intake"
# Lines of what a tool changed in the meal (§8.12, "Edición de la comida").
TOOL_RESULT_CHANGED = "changed"
# A topic of the guide the assistant read to answer a question about it (§8.12,
# "Dudas sobre la guía"): the page folds that turn and the model never sees it again.
TOOL_RESULT_GUIDE = "guide"
# The answer buttons the assistant offers under its question (§8.12, "Respuestas rápidas").
TOOL_RESULT_REPLIES = "replies"
QUICK_REPLIES_MIN = 2
QUICK_REPLIES_MAX = 4
QUICK_REPLY_MAX_LENGTH = 40
# The preparation values offered as buttons under a food, per field (§8.12,
# "Preparación con un toque"): the likeliest first, at most this many.
PREPARATION_OPTIONS_MAX = 3
PREPARATION_OPTION_FIELDS = {
    "cooking": CookingMethod,
    "final_state": FoodPhysicalState,
    "conservation": ConservationMethod,
}

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
    photos: tuple[AssistantPhoto, ...] = ()


@dataclass(frozen=True)
class AssistantConversationRead:
    id: int
    user_id: int
    intake_event_id: int | None  # None: no meal yet, or its meal was deleted
    model: str
    created_at: datetime
    without_meal: bool = False  # `No meal`: only drafts, never a meal (§8.12)


@dataclass(frozen=True)
class AssistantTurnRead:
    """One message answered in the background (code_conventions.md §8.12, §11.2.11).
    It holds what the page needs while it waits and after: the text and photo
    count the user sent, and where the answer ended up."""

    id: int
    user_id: int
    status: AssistantTurnStatus
    conversation_id: int | None  # None until the answer creates the conversation
    intake_event_id: int | None  # the meal it wrote to, for `Add to`
    meal_created: bool  # its first add created that meal
    user_text: str
    photo_count: int
    notices: tuple[str, ...]  # shown under the answer (§9.11)
    error_message: str | None  # the user-facing reason of a failed turn
    created_at: datetime
    finished_at: datetime | None
    seen_at: datetime | None  # when the page showed its outcome

    @property
    def pending(self) -> bool:
        return self.status in ASSISTANT_TURN_PENDING


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


def check_photo_count(count: int) -> None:
    """Checked before the files are read."""
    if count > ASSISTANT_PHOTOS_MAX:
        raise ValidationError(
            f"Attach at most {ASSISTANT_PHOTOS_MAX} photos in one message.", fields={"photo": "too_many"}
        )


def parse_assistant_photos(uploads: list[tuple[str, bytes]]) -> tuple[AssistantPhoto, ...]:
    """The attached photos, in order. Each format is checked on the bytes, not
    only on the declared type, and each size against ASSISTANT_PHOTO_MAX_BYTES."""
    check_photo_count(len(uploads))
    photos = []
    for position, (content_type, data) in enumerate(uploads, start=1):
        if not data:
            continue
        # "Photo 2 ..." when there are several, so the user knows which one to change.
        which = f"Photo {position}" if len(uploads) > 1 else "The photo"
        media_type = str(content_type or "").split(";")[0].strip().lower()
        if media_type not in ASSISTANT_PHOTO_MEDIA_TYPES:
            raise ValidationError(f"{which} must be JPEG, PNG or WebP.", fields={"photo": "invalid"})
        if len(data) > ASSISTANT_PHOTO_MAX_BYTES:
            raise ValidationError(f"{which} is too large.", fields={"photo": "too_large"})
        if media_type == "image/webp":
            valid = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        else:
            valid = data.startswith(_PHOTO_SIGNATURES[media_type])
        if not valid:
            raise ValidationError(f"{which} could not be read.", fields={"photo": "invalid"})
        photos.append(AssistantPhoto(ASSISTANT_PHOTO_STORED_TYPE, reencode_assistant_photo(data, which)))
    return tuple(photos)


def reencode_assistant_photo(data: bytes, which: str = "The photo") -> bytes:
    """The photo as the model gets it and as it is stored (§8.12, §11.2.10): a
    JPEG of at most ASSISTANT_PHOTO_MAX_SIDE_PX on its longer side, upright and
    without metadata. Writing a new JPEG from the pixels drops EXIF, and with
    it any GPS position; the orientation it held is applied first.

    Raises:
        ValidationError: the bytes are not an image Pillow can read, or the
            image declares more than ASSISTANT_PHOTO_MAX_PIXELS.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width * height > ASSISTANT_PHOTO_MAX_PIXELS:
                raise ValidationError(f"{which} is too large.", fields={"photo": "too_large"})
            # A JPEG can be decoded at a fraction of its size: far less memory
            # for a full-size phone photo. No-op for other formats.
            image.draft("RGB", (ASSISTANT_PHOTO_MAX_SIDE_PX, ASSISTANT_PHOTO_MAX_SIDE_PX))
            upright = ImageOps.exif_transpose(image)
            if upright.mode in ("RGBA", "LA", "P"):
                # Transparent parts of a screenshot become white, not black.
                upright = upright.convert("RGBA")
                background = Image.new("RGB", upright.size, (255, 255, 255))
                background.paste(upright, mask=upright.getchannel("A"))
                upright = background
            elif upright.mode != "RGB":
                upright = upright.convert("RGB")
            upright.thumbnail((ASSISTANT_PHOTO_MAX_SIDE_PX, ASSISTANT_PHOTO_MAX_SIDE_PX), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            # No exif, icc_profile or comment argument: nothing but the pixels is written.
            upright.save(output, format="JPEG", quality=ASSISTANT_PHOTO_JPEG_QUALITY, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError(f"{which} could not be read.", fields={"photo": "invalid"}) from None


def require_turn_content(request: AssistantTurnRequest) -> None:
    """A message needs something to read: text, a mention or a photo."""
    if not request.text and not request.mentions and not request.photos:
        raise ValidationError("Write what you ate.", fields={"message": "required"})


# `Add to` (frontend §9.11): a meal id, "" for `New meal` (its first add creates
# it) or this value for `No meal` (a chat for new foods and recipes only).
NO_MEAL_CHOICE = "none"


def parse_meal_choice(raw) -> tuple[int | None, bool]:
    """`Add to` as `(event_id, without_meal)`.

    Raises:
        ValidationError: neither a meal id, nor empty, nor `none`.
    """
    text = str(raw or "").strip()
    if text == NO_MEAL_CHOICE:
        return None, True
    if not text:
        return None, False
    if not text.isdigit() or int(text) <= 0:
        raise ValidationError("Invalid meal.", fields={"meal": "invalid"})
    return int(text), False


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


def _draft_nutrients(tool_input: dict) -> NutrientValues:
    """The nutrients per 100 g of a food or dish draft, checked like the create
    forms' (§7.13): carbs required, an unknown one empty, never 0 (§8.9).

    Raises:
        ValidationError: a value out of its limits or inconsistent with the rest.
    """
    values = {}
    for field in _LABEL_NUTRIENTS:
        number = tool_number(tool_input.get(field), field, required=(field == "carbs_100g"))
        values[field] = check_number(number, field, NUTRIENT_LIMITS[field])
    for input_name, field in _DRAFT_OTHER_NUTRIENTS.items():
        values[field] = check_number(tool_number(tool_input.get(input_name), input_name), field, NUTRIENT_LIMITS[field])
    nutrients = NutrientValues(**values)
    validate_nutrient_relations(nutrients)
    return nutrients


@dataclass(frozen=True)
class FoodDraftExtras:
    """What the model adds to any food draft, also on top of a Ciqual or OFF
    prefill, which only takes the ones its source does not bring (§8.12)."""

    category: FoodCategory | None
    subtype: str | None
    initial_state: FoodPhysicalState | None
    cooking_factor: float | None
    barcode: str | None
    # The rest of the create form (ampliación del 2026-11-15, §8.12): only what
    # the label prints or the user says.
    nutriscore: Nutriscore | None = None
    nova: int | None = None
    yuka: int | None = None
    macros_confidence: int | None = None
    default_amount_method: AmountMethod | None = None
    favorite: bool | None = None


def tool_confidence(value, field: str) -> int | None:
    """A declared confidence 0-2 of a tool input (measurement §6.10)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be 0, 1 or 2.")
    return parse_declared_confidence(str(value), field=field)


def tool_score(value, field: str, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValidationError(f"{field} must be a whole number from {minimum} to {maximum}.")
    return value


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
        nutriscore=_tool_enum(Nutriscore, tool_input.get("nutriscore"), "nutriscore"),
        nova=tool_score(tool_input.get("nova"), "nova", NOVA_MIN, NOVA_MAX),
        yuka=tool_score(tool_input.get("yuka"), "yuka", YUKA_MIN, YUKA_MAX),
        macros_confidence=tool_confidence(tool_input.get("macros_confidence"), "macros_confidence"),
        default_amount_method=_tool_enum(AmountMethod, tool_input.get("default_amount_method"), "default_amount_method"),
        favorite=tool_bool(tool_input.get("favorite"), "favorite"),
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
    nutrients = _draft_nutrients(tool_input)
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


# A dish draft (§8.12, "Platos manuales", ampliación del 2026-11-15): a reusable
# manual_intake the user reviews in its create form. Its macros are per 100 g,
# as the form's default mode, and its U1 is said by the model.
MANUAL_DRAFT_MACROS_SOURCES = (
    MacrosSource.AI_ESTIMATE,
    MacrosSource.OWN_ESTIMATE,
    MacrosSource.OFFICIAL,
    MacrosSource.LABEL,
)


@dataclass(frozen=True)
class ManualIntakeDraft:
    name: str
    description: str | None
    subtype: str | None
    origin: str | None
    default_portion: float | None
    nutrients: NutrientValues
    glycemic_index: GlycemicIndex | None
    ig_confidence: int | None
    macros_confidence: int | None
    macros_source: MacrosSource
    default_amount_method: AmountMethod | None
    favorite: bool | None


def manual_intake_draft(tool_input: dict) -> ManualIntakeDraft:
    """A dish draft written by the model, checked like the dish create form (§7.13).

    Name and carbs per 100 g are required; an unknown nutrient stays empty,
    never 0 (§8.9).

    Raises:
        ValidationError: a value out of the limits of the form, with its message.
    """
    name = tool_text(tool_input.get("name"), "name", max_length=MANUAL_INTAKE_NAME_MAX_LENGTH, required=True)
    parse_manual_intake_name(name)
    serving = tool_number(tool_input.get("serving_g"), "serving_g")
    if serving is not None:
        serving = check_number(serving, "default_portion", FOOD_DEFAULT_PORTION_RANGE)
    nutrients = _draft_nutrients(tool_input)
    require_carbs(nutrients)
    glycemic_index = _tool_enum(GlycemicIndex, tool_input.get("glycemic_index"), "glycemic_index")
    ig_confidence = tool_confidence(tool_input.get("ig_confidence"), "ig_confidence")
    validate_ig_confidence(glycemic_index, ig_confidence)
    macros_source = _tool_enum(MacrosSource, tool_input.get("macros_source"), "macros_source")
    if macros_source not in MANUAL_DRAFT_MACROS_SOURCES:
        raise ValidationError(
            "macros_source must be one of: " + ", ".join(m.value for m in MANUAL_DRAFT_MACROS_SOURCES) + "."
        )
    return ManualIntakeDraft(
        name=name,
        description=tool_text(
            tool_input.get("description"), "description", max_length=MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH
        ),
        subtype=tool_text(tool_input.get("subtype"), "subtype", max_length=FOOD_SUBTYPE_MAX_LENGTH),
        origin=tool_text(tool_input.get("origin"), "origin", max_length=MANUAL_INTAKE_ORIGIN_MAX_LENGTH),
        default_portion=serving,
        nutrients=nutrients,
        glycemic_index=glycemic_index,
        ig_confidence=ig_confidence,
        macros_confidence=tool_confidence(tool_input.get("macros_confidence"), "macros_confidence"),
        macros_source=macros_source,
        default_amount_method=_tool_enum(AmountMethod, tool_input.get("default_amount_method"), "default_amount_method"),
        favorite=tool_bool(tool_input.get("favorite"), "favorite"),
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
    favorite: bool | None = None  # None keeps the form's default

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
        favorite=tool_bool(tool_input.get("favorite"), "favorite"),
    )


def is_context_block(block: dict) -> bool:
    """Whether a text block of a user row is the one the server writes."""
    return block.get("type") == "text" and str(block.get("text", "")).startswith(ASSISTANT_CONTEXT_TAG)


# Length of the first line of a chat in the list of chats (frontend §9.11).
CHAT_PREVIEW_LENGTH = 60


def chat_preview(content: list | None) -> str:
    """What the user wrote first in a chat, on one line, for the list of chats
    (frontend §9.11): `Photo` when it was only photos, `Empty chat` when nothing."""
    blocks = content or []
    texts = [
        str(block.get("text", ""))
        for block in blocks
        if block.get("type") == "text" and not is_context_block(block)
        and block.get("text") not in _PHOTO_PLACEHOLDERS
    ]
    text = " ".join(" ".join(texts).split())
    if not text:
        has_photo = any(
            block.get("type") == "image" or block.get("text") in _PHOTO_PLACEHOLDERS for block in blocks
        )
        return "Photo" if has_photo else "Empty chat"
    if len(text) <= CHAT_PREVIEW_LENGTH:
        return text
    return text[: CHAT_PREVIEW_LENGTH - 1].rstrip() + "…"


# "Usual now" in an empty chat (decision of the user of 2026-11-22, frontend §9.11):
# the foods eaten most around this time of day.
USUAL_FOODS_SHOWN = 5
USUAL_FOODS_DAYS = 60
# Each past meal counts exp(-(distance to now / spread)²): 1 at this time, 0.64 an
# hour away, 0.17 two hours away (frontend §9.11, decision of the user 2026-11-22).
USUAL_FOODS_SPREAD_MINUTES = 90
USUAL_FOODS_MIN_SCORE = 0.35  # at least one meal within about 90 minutes of now


@dataclass(frozen=True)
class UsualFood:
    """A food the user eats often at this time, offered in an empty chat (§9.11)."""

    entry_type: str  # FoodEntryType value: catalog or manual_intake
    entry_id: int
    name: str
    grams: float  # the median amount eaten


# "Lo de siempre" (decision of the user of 2026-11-22, §8.12): a meal eaten at
# least this many times in this many days, around this time of day, with the
# same foods.
USUAL_MEAL_DAYS = 30
USUAL_MEAL_MIN_COUNT = 3
USUAL_MEAL_MINUTES = 120  # ±2 h of now (decision of the user 2026-11-22)
USUAL_MEALS_SHOWN = 3


@dataclass(frozen=True)
class UsualMealFood:
    entry_type: str
    entry_id: int
    name: str
    grams: float  # the median amount eaten
    cooking: str | None
    final_state: str | None
    conservation: str | None


@dataclass(frozen=True)
class UsualMeal:
    times: int
    foods: tuple[UsualMealFood, ...]


def _minutes_apart(a: int, b: int) -> int:
    distance = abs(a - b) % 1440
    return min(distance, 1440 - distance)


def usual_meals(meals: list[tuple[int, list]], now_minute: int) -> list[UsualMeal]:
    """The meals eaten again and again around this time (§8.12, "Lo de siempre").

    `meals`: (local minute of the day, its portions) of the confirmed meals of the
    window. Two meals are the same when they have the same foods, whatever the
    amounts; each food takes the median of what was eaten and its latest
    preparation. The most repeated first, at most USUAL_MEALS_SHOWN.
    """
    groups: dict[frozenset, list[list]] = {}
    for minute, portions in meals:
        if not portions or _minutes_apart(minute, now_minute) > USUAL_MEAL_MINUTES:
            continue
        key = frozenset((p.origin.value, p.origin_id) for p in portions)
        groups.setdefault(key, []).append(portions)
    found = []
    for key, occurrences in groups.items():
        if len(occurrences) < USUAL_MEAL_MIN_COUNT:
            continue
        foods = []
        for entry_type, entry_id in sorted(key):
            rows = [p for portions in occurrences for p in portions if (p.origin.value, p.origin_id) == (entry_type, entry_id)]
            amounts = sorted(p.amount for p in rows)
            middle = len(amounts) // 2
            median = amounts[middle] if len(amounts) % 2 else (amounts[middle - 1] + amounts[middle]) / 2
            latest = rows[0]
            foods.append(
                UsualMealFood(
                    entry_type,
                    entry_id,
                    latest.source.name or "",
                    round(median),
                    latest.cooking.value if latest.cooking else None,
                    latest.final_state.value if latest.final_state else None,
                    latest.conservation.value if latest.conservation else None,
                )
            )
        found.append(UsualMeal(len(occurrences), tuple(foods)))
    found.sort(key=lambda meal: -meal.times)
    return found[:USUAL_MEALS_SHOWN]


@dataclass(frozen=True)
class ChatSummary:
    """A chat without a meal in the list of chats (frontend §9.11)."""

    conversation_id: int
    updated_at: datetime
    preview: str


@dataclass(frozen=True)
class PastChat:
    """A chat in the past chats (frontend §9.11): the conversation of a confirmed
    meal, or a `No meal` chat, hidden or not."""

    conversation_id: int
    event_id: int | None  # None: a `No meal` chat
    updated_at: datetime
    preview: str
    hidden: bool


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
class ProvisionalCard:
    """A provisional food or dish the assistant created and added (§8.12)."""

    entry_type: str  # FoodEntryType value: catalog or manual_intake
    entry_id: int
    name: str
    brand_or_origin: str | None
    carbs_100g: float | None
    macros_source: str | None
    grams: float | None
    carbs_g: float | None


@dataclass(frozen=True)
class RepeatCard:
    """A quick add eaten often, offered to be saved (§8.12, "Repeticiones")."""

    quick_add_id: int
    name: str
    count: int
    save_as: str  # RepeatSaveAs value


@dataclass(frozen=True)
class AddedUnit:
    """What one add put in a row of the meal, so a +1 can repeat it (§8.12, "Botones +1")."""

    portion_id: int
    unit_g: float  # one counted piece, else one serving, else the grams of that add


@dataclass(frozen=True)
class PreparationChoice:
    """The values of one preparation field the assistant offered for a row of the
    meal, to pick with a tap (§8.12, "Preparación con un toque")."""

    portion_id: int
    field: str  # a key of PREPARATION_OPTION_FIELDS
    options: tuple[str, ...]  # values of its enum, the likeliest first


@dataclass(frozen=True)
class TurnView:
    """One message of the user and everything the assistant did for it."""

    user_text: str
    photo_count: int
    replies: list[str]
    added: list[AddedCard]
    drafts: list[DraftCard]
    changed: list[str]
    provisional: list[ProvisionalCard] = field(default_factory=list)
    repeats: list[RepeatCard] = field(default_factory=list)
    units: list[AddedUnit] = field(default_factory=list)
    quick_replies: list[str] = field(default_factory=list)
    preparation: list[PreparationChoice] = field(default_factory=list)
    guides: list[str] = field(default_factory=list)  # topics of the guide read in it

    @property
    def is_guide_question(self) -> bool:
        """Only a question about the guide: it read the guide and touched nothing (§8.12)."""
        return bool(self.guides) and not (
            self.added or self.drafts or self.changed or self.provisional or self.repeats or self.units
        )


def _added_unit(added) -> AddedUnit | None:
    """The unit of an add with its row id; None for a recipe or an old result."""
    if not isinstance(added, dict) or not _is_id(added.get("food_id")):
        return None
    grams = _number(added.get("grams"))
    if not grams or grams <= 0:
        return None
    # The pieces the user counted win over the servings: "2 croquetas" +1 is a
    # third croqueta, even if the serving is two of them (§8.12, "Botones +1").
    count = _number(added.get("pieces")) or _number(added.get("servings"))
    unit = grams / count if count and count > 0 else grams
    return AddedUnit(portion_id=added["food_id"], unit_g=unit)


def parse_preparation_options(field_name: str, raw) -> tuple[str, ...]:
    """The values of one preparation field the model offered: known ones only,
    without repeats, at most PREPARATION_OPTIONS_MAX; anything else gives none."""
    enum_cls = PREPARATION_OPTION_FIELDS.get(field_name)
    if enum_cls is None or not isinstance(raw, list):
        return ()
    known = {member.value for member in enum_cls}
    options: list[str] = []
    for value in raw:
        if isinstance(value, str) and value in known and value not in options:
            options.append(value)
    return tuple(options[:PREPARATION_OPTIONS_MAX])


def parse_quick_replies(raw) -> list[str]:
    """The answer buttons the model offered (§8.12, "Respuestas rápidas").

    Raises:
        ValidationError: not 2 to 4 non-empty texts of at most 40 characters.
    """
    if not isinstance(raw, list):
        raise ValidationError("options must be a list of texts.")
    options = [" ".join(str(value).split()) for value in raw if isinstance(value, str)]
    options = [option for option in options if option]
    if not QUICK_REPLIES_MIN <= len(options) <= QUICK_REPLIES_MAX or len(options) != len(raw):
        raise ValidationError(f"Give {QUICK_REPLIES_MIN} to {QUICK_REPLIES_MAX} non-empty options.")
    if any(len(option) > QUICK_REPLY_MAX_LENGTH for option in options):
        raise ValidationError(f"Each option at most {QUICK_REPLY_MAX_LENGTH} characters.")
    return options


def preparation_choices(turns: list["TurnView"]) -> dict[int, dict[str, tuple[str, ...]]]:
    """The latest values offered for each preparation field of each row of the
    meal (§8.12), in the order of PREPARATION_OPTION_FIELDS."""
    latest: dict[int, dict[str, tuple[str, ...]]] = {}
    for turn in turns:
        for choice in turn.preparation:
            latest.setdefault(choice.portion_id, {})[choice.field] = choice.options
    return {
        portion_id: {name: fields[name] for name in PREPARATION_OPTION_FIELDS if name in fields}
        for portion_id, fields in latest.items()
    }


# Days of confirmed meals read for the usual preparation of a food (§8.12).
USUAL_PREPARATION_DAYS = 90


def with_usual_first(options: tuple[str, ...], usual: str | None) -> tuple[str, ...]:
    """The values offered for one field with the user's usual one for that food
    first (§8.12, "Preparación con un toque"): DiaBot ranks by what the chat says,
    the history of the food decides the first place. It stays at
    PREPARATION_OPTIONS_MAX values."""
    if usual is None:
        return options
    return (usual, *(value for value in options if value != usual))[:PREPARATION_OPTIONS_MAX]


def plus_one_units(turns: list["TurnView"]) -> list[AddedUnit]:
    """The rows a +1 can repeat, the last added first, each with the unit of its
    latest add (§8.12, "Botones +1")."""
    latest: dict[int, AddedUnit] = {}
    for turn in turns:
        for unit in turn.units:
            latest.pop(unit.portion_id, None)
            latest[unit.portion_id] = unit
    return list(reversed(latest.values()))


# Steps of a +1 button and of its long-press menu, in units (frontend §9.11).
PLUS_STEPS = (1.0, 0.5, 2.0, -1.0)


def parse_plus_step(raw) -> float:
    try:
        step = float(str(raw).strip())
    except (TypeError, ValueError) as error:
        raise ValidationError("Unknown step.") from error
    if step not in PLUS_STEPS:
        raise ValidationError("Unknown step.")
    return step


def _is_id(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _number(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def starts_turn(message: AssistantMessageRead) -> bool:
    """A user row with something other than tool results is a new message of the user."""
    return message.role is AssistantRole.USER and any(block.get("type") != "tool_result" for block in message.content)


# Turns of the user sent back to the model (code_conventions.md §8.12, cost).
# Older ones are cut in steps, so the cached prefix stays the same for several
# messages in a row instead of changing with every message.
ASSISTANT_HISTORY_MAX_TURNS = 30
ASSISTANT_HISTORY_CUT_STEP = 10


def without_guide_questions(messages: list[AssistantMessageRead]) -> list[AssistantMessageRead]:
    """The stored messages without the turns that only answered a question about the
    guide (§8.12, "Dudas sobre la guía"): kept for the study and shown folded, but
    never sent back to the model, so they do not make the chat dearer."""
    starts = [i for i, message in enumerate(messages) if starts_turn(message)]
    if not starts:
        return messages
    kept = messages[: starts[0]]
    bounds = starts + [len(messages)]
    for start, end in zip(bounds, bounds[1:]):
        turn = messages[start:end]
        views = turn_views(turn)
        if views and views[0].is_guide_question:
            continue
        kept.extend(turn)
    return kept


def without_unanswered_calls(messages: list[AssistantMessageRead]) -> list[AssistantMessageRead]:
    """The stored messages without the tool calls the API would reject (§8.12,
    "Turno"): an answer whose calls are not all answered by the next row, as one
    cut by its token limit was stored before 2026-11-22, and the results of calls
    that are no longer sent. Without this, one such row breaks the chat for good."""
    kept: list[AssistantMessageRead] = []
    answered: set = set()
    for index, message in enumerate(messages):
        if message.role is AssistantRole.ASSISTANT:
            calls = {block.get("id") for block in message.content if block.get("type") == "tool_use"}
            if calls:
                following = messages[index + 1] if index + 1 < len(messages) else None
                results = (
                    {block.get("tool_use_id") for block in following.content if block.get("type") == "tool_result"}
                    if following is not None and following.role is AssistantRole.USER
                    else set()
                )
                if not calls <= results:
                    continue
                answered = calls
            else:
                answered = set()
            kept.append(message)
            continue
        if any(block.get("type") == "tool_result" for block in message.content):
            content = [
                block for block in message.content
                if block.get("type") != "tool_result" or block.get("tool_use_id") in answered
            ]
            answered = set()
            if not content:
                continue
            if len(content) != len(message.content):
                message = replace(message, content=content)
        kept.append(message)
    return kept


def history_window(messages: list[AssistantMessageRead]) -> list[AssistantMessageRead]:
    """The stored messages sent back to the model: at most the last
    ASSISTANT_HISTORY_MAX_TURNS turns of the user, cut at the start of a turn so
    that every tool call keeps its result."""
    starts = [i for i, message in enumerate(messages) if starts_turn(message)]
    excess = len(starts) - ASSISTANT_HISTORY_MAX_TURNS
    if excess <= 0:
        return messages
    step = ASSISTANT_HISTORY_CUT_STEP
    cut_turn = min(((excess + step - 1) // step) * step, len(starts) - 1)
    return messages[starts[cut_turn]:]


def turn_views(messages: list[AssistantMessageRead]) -> list[TurnView]:
    """The turns of a stored conversation, in order, as the page shows them."""
    turns: list[TurnView] = []
    tool_message: dict[str, int] = {}  # tool_use_id -> id of the assistant row that called it
    for message in messages:
        if starts_turn(message):
            texts = [
                str(block.get("text", ""))
                for block in message.content
                if block.get("type") == "text" and not is_context_block(block)
                and block.get("text") not in _PHOTO_PLACEHOLDERS
            ]
            photo_count = sum(
                block.get("type") == "image" or block.get("text") in _PHOTO_PLACEHOLDERS
                for block in message.content
            )
            turns.append(TurnView("\n".join(texts).strip(), photo_count, [], [], [], []))
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
    unit = _added_unit(added)
    if unit is not None:
        turn.units.append(unit)
        offered = added.get("preparation_options")
        if isinstance(offered, dict):
            for name in PREPARATION_OPTION_FIELDS:
                options = parse_preparation_options(name, offered.get(name))
                if options:
                    turn.preparation.append(PreparationChoice(unit.portion_id, name, options))
    guide = result.get(TOOL_RESULT_GUIDE)
    if isinstance(guide, str) and guide:
        turn.guides.append(guide)
    replies = result.get(TOOL_RESULT_REPLIES)
    if isinstance(replies, list):
        turn.quick_replies[:] = [str(reply) for reply in replies if isinstance(reply, str) and reply]
    provisional = result.get(TOOL_RESULT_PROVISIONAL)
    if isinstance(added, dict) and isinstance(provisional, dict) and _is_id(provisional.get("id")):
        # Shown on its own card, with Review, instead of in Added to the cart.
        turn.provisional.append(
            ProvisionalCard(
                entry_type=str(provisional.get("entry_type")),
                entry_id=provisional["id"],
                name=str(added.get("name") or ""),
                brand_or_origin=provisional.get("brand_or_origin"),
                carbs_100g=_number(provisional.get("carbs_100g")),
                macros_source=provisional.get("macros_source"),
                grams=_number(added.get("grams")),
                carbs_g=_number(added.get("carbs_g")),
            )
        )
        added = None
    repeat = result.get(TOOL_RESULT_REPEAT)
    if isinstance(repeat, dict) and isinstance(added, dict) and _is_id(repeat.get("quick_add_id")):
        turn.repeats.append(
            RepeatCard(
                quick_add_id=repeat["quick_add_id"],
                name=str(added.get("name") or ""),
                count=int(_number(repeat.get("count")) or 0),
                save_as=str(repeat.get("save_as")),
            )
        )
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


# ============================================
# Quick mode (§8.12, "Modo rápido")
# ============================================

QUICK_LIST_MAX_ITEMS = 12
QUICK_MODE_EFFORT = "low"
TOOL_EFFORT_MARKER = "effort"  # block type of a `system` row: our marker, not an API block

_QUICK_SPLIT = re.compile(r"\s*(?:,|;|\n|\s+y\s+|\s+and\s+)\s*", re.IGNORECASE)
_QUICK_UNIT = r"(?:(?:g|gr|grs|gramos|ml|ud|uds|unidad|unidades)\.?)"
_QUICK_NUMBER = r"\d+(?:[.,]\d+)?"
_QUICK_NAME = r"[^\d?¿!¡]*[^\W\d_][^\d?¿!¡]*"
_QUICK_ITEM = re.compile(
    rf"^(?:{_QUICK_NAME}\s+{_QUICK_NUMBER}\s*{_QUICK_UNIT}?"
    rf"|{_QUICK_NUMBER}\s*{_QUICK_UNIT}?\s+(?:de\s+)?{_QUICK_NAME})$",
    re.IGNORECASE,
)


def is_quick_list(text: str, *, has_photo: bool = False) -> bool:
    """Whether a message is only a list of foods with their amounts ("arroz 150,
    pollo 120, pan 40"): decided by its form, before calling the model. Each part
    is a short name and an amount; a time or a day ("sobre las 9") is not one."""
    if has_photo or "?" in text or "¿" in text:
        return False
    parts = [part.strip() for part in _QUICK_SPLIT.split(text.strip()) if part.strip()]
    if not 1 <= len(parts) <= QUICK_LIST_MAX_ITEMS:
        return False
    return all(_quick_item(part) for part in parts)


# A number that is a time or a day is not an amount ("sobre las 9", "ayer 14").
_QUICK_NOT_AMOUNT = re.compile(
    r"\b(?:las|la|hora|horas|ayer|hoy|mañana|anoche|at|pm|am|yesterday|today)\b", re.IGNORECASE
)
QUICK_NAME_MAX_WORDS = 4


def _quick_item(part: str) -> bool:
    if not _QUICK_ITEM.match(part) or _QUICK_NOT_AMOUNT.search(part):
        return False
    name = re.sub(rf"{_QUICK_NUMBER}\s*{_QUICK_UNIT}?|\bde\b", " ", part, flags=re.IGNORECASE)
    return len(name.split()) <= QUICK_NAME_MAX_WORDS


def effort_marker(effort: str) -> list[dict]:
    """The content of a `system` row that changes the effort from there on."""
    return [{"type": TOOL_EFFORT_MARKER, "effort": effort}]


def current_effort(messages: list[AssistantMessageRead], default: str) -> str:
    """The effort the model runs at after these messages: the last change in
    them, or the request's own."""
    for message in reversed(messages):
        if message.role is AssistantRole.SYSTEM:
            for block in message.content:
                if block.get("type") == TOOL_EFFORT_MARKER and block.get("effort"):
                    return str(block["effort"])
    return default


def api_message(role: AssistantRole, content: list[dict]) -> dict:
    """A stored row as the API takes it: a `system` row is a change of effort."""
    if role is AssistantRole.SYSTEM:
        effort = next(
            (block.get("effort") for block in content if block.get("type") == TOOL_EFFORT_MARKER), None
        )
        return {"role": "system", "content": [], "output_config": {"effort": effort}}
    return {"role": role.value, "content": content}


# ============================================
# Learning from the user's corrections (§8.12, "Aprender de las correcciones")
# ============================================

CALIBRATION_DAYS = 90
CALIBRATION_MIN_SAMPLES = 5
CALIBRATION_MIN_SHIFT = 0.10  # a median ratio within ±10 % changes nothing
CALIBRATION_RATIO_RANGE = (0.25, 4.0)  # one ratio outside it is clipped, not trusted


@unique
class CalibrationGroup(str, Enum):
    PHOTO = "photo"  # the turn had a photo; wins over the other two
    OUT = "out"  # the meal was eaten out
    HOME = "home"


_CALIBRATION_WHAT = {
    CalibrationGroup.PHOTO: "from a photo",
    CalibrationGroup.OUT: "when eating out",
    CalibrationGroup.HOME: "at home",
}


@dataclass(frozen=True)
class EstimateSample:
    """One add of DiaBot with an estimated amount, as its tool result stored it."""
    portion_id: int
    grams: float
    carbs_g: float | None
    is_quick_add: bool  # an add_estimate: its carbs are DiaBot's too
    group: CalibrationGroup


@dataclass(frozen=True)
class CalibrationPortion:
    """The row of a confirmed meal an estimate went to, as it ended."""
    portion_id: int
    served_g: float  # amount / eaten_fraction of its plate
    carbs_100g: float | None  # of a quick add, now; None for anything else


def estimate_samples(rows: list[tuple[int, list[dict], bool]]) -> list[EstimateSample]:
    """The estimated adds of some conversations. `rows` are their `user` rows in
    order, each as (conversation_id, content, eating_out): turn starts say
    whether the turn had a photo, tool results say what was added."""
    samples: list[EstimateSample] = []
    photo: dict[int, bool] = {}
    for conversation_id, content, eating_out in rows:
        if any(block.get("type") != "tool_result" for block in content):
            photo[conversation_id] = any(
                block.get("type") == "image" or block.get("text") in _PHOTO_PLACEHOLDERS for block in content
            )
            continue
        for block in content:
            if block.get("type") != "tool_result" or block.get("is_error"):
                continue
            try:
                result = json.loads(block.get("content") or "")
            except (TypeError, ValueError):
                continue
            added = result.get(TOOL_RESULT_ADDED) if isinstance(result, dict) else None
            if not isinstance(added, dict) or added.get("amount_method") != "ai_estimate":
                continue
            portion_id, grams = added.get("food_id"), added.get("grams")
            if not isinstance(portion_id, int) or not isinstance(grams, (int, float)) or grams <= 0:
                continue
            carbs = added.get("carbs_g")
            group = (
                CalibrationGroup.PHOTO
                if photo.get(conversation_id)
                else CalibrationGroup.OUT
                if eating_out
                else CalibrationGroup.HOME
            )
            samples.append(
                EstimateSample(
                    portion_id,
                    float(grams),
                    float(carbs) if isinstance(carbs, (int, float)) else None,
                    added.get("kind") == "estimate",
                    group,
                )
            )
    return samples


def _clipped(ratio: float) -> float:
    low, high = CALIBRATION_RATIO_RANGE
    return min(max(ratio, low), high)


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _shift_text(ratio: float) -> str:
    return f"{(ratio - 1) * 100:+.0f} %".replace("-", "−")


def calibration_lines(samples: list[EstimateSample], portions: dict[int, CalibrationPortion]) -> list[str]:
    """The lines of the context block that tell DiaBot how the user corrects its
    estimates: one per group with enough samples and a real shift. Several adds
    to one row count as one estimate, their grams summed."""
    grams_by_row: dict[int, tuple[float, CalibrationGroup]] = {}
    for sample in samples:
        total, group = grams_by_row.get(sample.portion_id, (0.0, sample.group))
        grams_by_row[sample.portion_id] = (total + sample.grams, group)
    amount_ratios: dict[CalibrationGroup, list[float]] = {}
    for portion_id, (grams, group) in grams_by_row.items():
        portion = portions.get(portion_id)
        if portion is not None and portion.served_g > 0:
            amount_ratios.setdefault(group, []).append(_clipped(portion.served_g / grams))
    carbs_ratios: list[float] = []
    for sample in samples:
        portion = portions.get(sample.portion_id)
        if not sample.is_quick_add or not sample.carbs_g or portion is None or portion.carbs_100g is None:
            continue
        carbs_ratios.append(_clipped((portion.carbs_100g / 100) / (sample.carbs_g / sample.grams)))

    lines = []
    for group in CalibrationGroup:
        ratios = amount_ratios.get(group, [])
        if len(ratios) < CALIBRATION_MIN_SAMPLES:
            continue
        ratio = _median(ratios)
        if abs(ratio - 1) <= CALIBRATION_MIN_SHIFT:
            continue
        lines.append(
            f"Calibration: the user corrects your estimated amounts {_CALIBRATION_WHAT[group]} to "
            f"x{ratio:.2f} (median of {len(ratios)}). Scale those estimates by it and say so in a few "
            f"words (\"{_shift_text(ratio)}, as you usually correct\")."
        )
    if len(carbs_ratios) >= CALIBRATION_MIN_SAMPLES:
        ratio = _median(carbs_ratios)
        if abs(ratio - 1) > CALIBRATION_MIN_SHIFT:
            lines.append(
                f"Calibration: the user corrects the carbs of your quick add estimates to x{ratio:.2f} "
                f"(median of {len(carbs_ratios)}). Scale them by it and say so in a few words."
            )
    return lines
