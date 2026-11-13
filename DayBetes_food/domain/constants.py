"""Domain enums (conventions/code_conventions.md §3.6 and §4.1).

This module imports no psycopg, routes or components. Each concept has a
single enum here; no parallel lists of the same concept are created in
routes/, components/, crud.py or schema.py.
"""

import re
from enum import Enum, unique

from DayBetes_food.errors import MalformedRequestError, ValidationError


@unique
class InsulinType(str, Enum):
    RAPID = "rapid"
    BASAL = "basal"


@unique
class InjectionZone(str, Enum):
    RIGHT_ARM = "right_arm"
    LEFT_ARM = "left_arm"
    RIGHT_THIGH = "right_thigh"
    LEFT_THIGH = "left_thigh"
    ABDOMEN = "abdomen"
    RIGHT_GLUTEUS = "right_gluteus"
    LEFT_GLUTEUS = "left_gluteus"


@unique
class MealType(str, Enum):
    BREAKFAST = "breakfast"
    BRUNCH = "brunch"
    LUNCH = "lunch"
    AFTERNOON_SNACK = "afternoon_snack"
    DINNER = "dinner"
    SNACK = "snack"
    RESCUE = "rescue"
    # Fuel taken for exercise, whatever the glucose (study_conventions.md §N).
    # Always chosen by hand, like snack and rescue: never by the schedule.
    EXERCISE = "exercise"


@unique
class IntakeEventState(str, Enum):
    PLANNED = "planned"
    CONSUMED = "consumed"


@unique
class AmountInputUnit(str, Enum):
    """Amount input units the interface can emit.

    It is the central units enum required by measurement_conventions.md §11:
    the internal code of a closed unit lives here and is not written as free
    text in routes or components. The values are the stable codes of §4.2 of
    that same document.

    `lb` and `oz` carry their exact factor to grams in the enum itself and are
    the only source of that number (decision 2026-09-22). `portion` has no
    constant factor: its factor is the food's `unit_g` and is resolved at run
    time. `percent` is not a mass: it is interpreted against the total and is
    not accepted on the amount route.

    None of these units is persisted: they decide how the received amount is
    interpreted before converting it to the canonical unit (grams).
    """

    def __new__(cls, code, grams_factor=None):
        obj = str.__new__(cls, code)
        obj._value_ = code
        obj.grams_factor = grams_factor
        return obj

    GRAMS = ("g", 1.0)
    PERCENT = ("%", None)
    PORTION = ("portion", None)
    LB = ("lb", 453.59237)
    OZ = ("oz", 28.349523125)


@unique
class FoodEntryType(str, Enum):
    """Kind of entry of the Food list, as it travels in the URL of the Food
    routes: a food, a dish or a recipe. Only the first two can be the origin
    of a portion (PortionOrigin)."""
    CATALOG = "catalog"
    MANUAL_INTAKE = "manual_intake"
    RECIPE = "recipe"


@unique
class CreationResult(str, Enum):
    """Outcome of an insert that can find an equivalent row (§6.2)."""
    CREATED = "created"
    ALREADY_EXISTED = "already_existed"


@unique
class PortionOrigin(str, Enum):
    """Where the food of a portion comes from (`portion_detail` origin arc)."""
    CATALOG = "catalog"
    MANUAL_INTAKE = "manual_intake"


@unique
class PortionDestination(str, Enum):
    """Where a portion is assigned (`portion_detail` destination arc).

    FRIDGE has no writer yet: the enum describes the model, not the interface
    (decision 2026-09-22).
    """
    INTAKE_EVENT = "intake_event"
    RECIPE = "recipe"
    FRIDGE = "fridge"


# Sanity ceiling for every mass in grams shared by more than one table
# (measurement_conventions.md 6.9.2): 100000 g = 100 kg. It is not a clinical
# limit, only a ceiling so a corrupt or manipulated value is not stored as if
# it were plausible. Declared once (4.7) and reused by `intake_event` and
# `portion_detail`.
MASS_SANITY_MAX_G = 100000


@unique
class SystemTag(str, Enum):
    """Tags every user has, identified by `tags.system_key` and never renamed
    or deleted (code_conventions.md §11.2.8). Each one has a tab of the quick
    log pop-up and the meal type of the same name (frontend_conventions.md §9.6)."""
    RESCUE = "rescue"
    EXERCISE = "exercise"


@unique
class FoodCategory(str, Enum):
    MEAT = "meat"
    FISH = "fish"
    DAIRY = "dairy"
    EGGS = "eggs"
    PROCESSED_MEAT = "processed_meat"
    LEGUMES = "legumes"
    TUBERS = "tubers"
    NUTS = "nuts"
    VEGETABLES = "vegetables"
    FRUITS = "fruits"
    CEREALS = "cereals"
    OILS_AND_FATS = "oils_and_fats"
    SWEETS = "sweets"
    BEVERAGES = "beverages"
    SAUCES = "sauces"
    CONDIMENTS = "condiments"
    SUPPLEMENTS = "supplements"


@unique
class Nutriscore(str, Enum):
    # Stored codes are upper-case (4.2: keep existing codes).
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


@unique
class PrefillSource(str, Enum):
    # Where the create form of a catalog food got its first values (§12.1).
    OPEN_FOOD_FACTS = "off"
    CIQUAL = "ciqual"


@unique
class AssistantRole(str, Enum):
    """Author of a stored message of the assistant (code_conventions.md §11.2.9):
    the same two roles as the Claude API. A `user` row is what the user sent
    or the results of the tools; an `assistant` row is one answer of the model."""
    USER = "user"
    ASSISTANT = "assistant"


@unique
class AssistantDraftSource(str, Enum):
    """Where the assistant takes a new food from: it never creates it, it opens
    the create form prefilled (code_conventions.md §8.12, "Alimentos nuevos")."""
    CIQUAL = "ciqual"
    OPEN_FOOD_FACTS = "open_food_facts"
    LABEL = "label"
    ESTIMATE = "estimate"  # the assistant's estimate, when the user asks for it


@unique
class FoodPhysicalState(str, Enum):
    # catalog.initial_state AND portion_detail.final_state.
    SOLID = "solid"
    MASHED_CREAMY = "mashed/creamy"
    LIQUID = "liquid"
    GEL = "gel"


@unique
class CookingMethod(str, Enum):
    STEAM = "steam"
    BOILED_AL_DENTE = "boiled-al-dente"
    BOILED_SOFT = "boiled-soft"
    FRIED = "fried"
    RAW = "raw"
    OVEN = "oven"
    AIRFRYER = "airfryer"
    TOASTER = "toaster"
    GRIDDLE = "griddle"


@unique
class ConservationMethod(str, Enum):
    FRESHLY_MADE = "freshly-made"
    FRIDGE = "fridge"
    FREEZER = "freezer"
    PRE_COOKED = "pre-cooked"


@unique
class Ripeness(str, Enum):
    """Ripeness of a fruit seen by eye when eating it (study_conventions.md §6.3).
    Only on meal portions of a `fruits` food; NULL is "not given", never `ripe`."""

    UNRIPE = "unripe"
    RIPE = "ripe"
    OVERRIPE = "overripe"


@unique
class MacrosSource(str, Enum):
    """U1: where the macros of a food come from (study_conventions.md §6.3).
    A fact of the food (`catalog`, `manual_intake`); NULL is "not given",
    never "estimated"."""

    LABEL = "label"
    OFFICIAL = "official"
    OPEN_FOOD_FACTS = "open_food_facts"
    REFERENCE_DB = "reference_db"
    INGREDIENTS = "ingredients"
    AI_ESTIMATE = "ai_estimate"
    OWN_ESTIMATE = "own_estimate"


# U1 prefilled by the source of the create form (study §6.3): the user reviews it.
PREFILL_MACROS_SOURCE = {
    PrefillSource.OPEN_FOOD_FACTS: MacrosSource.OPEN_FOOD_FACTS,
    PrefillSource.CIQUAL: MacrosSource.REFERENCE_DB,
}


# Published by whoever makes or sells the food: the macros that
# quality_confidence counts (measurement_conventions.md §6.5).
PUBLISHED_MACROS_SOURCES = frozenset(
    {MacrosSource.LABEL, MacrosSource.OFFICIAL, MacrosSource.OPEN_FOOD_FACTS}
)


@unique
class AmountMethod(str, Enum):
    """U2: how the amount of a portion was obtained (study_conventions.md §6.3).
    On each portion, with a default on the food; NULL is "not given"."""

    KITCHEN_SCALE = "kitchen_scale"
    POCKET_SCALE = "pocket_scale"
    PACKAGE = "package"
    HOUSEHOLD = "household"
    EYEBALL = "eyeball"
    AI_ESTIMATE = "ai_estimate"


# Measured amounts: the ones amount_confidence counts (measurement_conventions.md §6.4).
WEIGHED_AMOUNT_METHODS = frozenset(
    {AmountMethod.KITCHEN_SCALE, AmountMethod.POCKET_SCALE, AmountMethod.PACKAGE}
)


@unique
class StorageLocation(str, Enum):
    """Where a container (`fridge`) is kept (measurement_conventions.md 4.8).

    Not `ConservationMethod`: that one describes a portion, this one a
    container. There is no pantry at room temperature (decision 2026-11-07).
    """
    FRIDGE = "fridge"
    FREEZER = "freezer"


@unique
class KeepPartMode(str, Enum):
    """How the part of an ingredient that stays on the plate is given, when the rest
    goes to the fridge after cooking (measurement_conventions.md §4.8.5)."""
    PERCENT = "percent"   # % of the ingredient that stays on the plate
    WEIGHED = "weighed"   # the cooked total and what was plated, both weighed


@unique
class FridgeCloseReason(str, Enum):
    """Why a container left the fridge (code_conventions.md §11.2.6). An emptied one
    reopens if what was taken from it goes back; a discarded one never does."""
    EMPTIED = "emptied"
    DISCARDED = "discarded"


@unique
class PenFormat(str, Enum):
    """How an insulin pen comes (measurement_conventions.md §8.4)."""
    PREFILLED_PEN = "prefilled_pen"
    CARTRIDGE = "cartridge"


@unique
class PenCloseReason(str, Enum):
    """Why an insulin pen stopped being used (code_conventions.md §11.2.7). It is
    worked out when the pen is closed, never asked (measurement §8.4)."""
    EMPTY = "empty"
    EXPIRED = "expired"
    DISCARDED = "discarded"


@unique
class GlycemicIndex(str, Enum):
    """Declared absorption speed of a manual dish (measurement_conventions.md
    §5.5). Not a measured GI. Existing codes kept (§4.2); `none` added."""

    NONE = "none"  # no absorption (no carbs)
    LOW = "low"  # slow
    MEDIUM = "medium"
    HIGH = "high"  # fast


@unique
class NutrientEntryMode(str, Enum):
    """How the user typed the nutrients of a manual dish (measurement §5.4).
    Transport only: never persisted."""

    PER_100G = "per_100g"
    PORTION_TOTAL = "portion_total"


NOVA_MIN, NOVA_MAX = 1, 4
YUKA_MIN, YUKA_MAX = 0, 100


def parse_enum(enum_cls, raw, *, field: str, normalize=None):
    """Boundary conversion of a closed value (4.3, 7.7). '' -> None; unknown -> ValidationError."""
    text = (raw or "").strip()
    if normalize:
        text = normalize(text)
    if not text:
        return None
    try:
        return enum_cls(text)
    except ValueError as exc:
        raise ValidationError(f"Invalid {field.replace('_', ' ')}.", fields={field: "invalid"}) from exc


_ID_TEXT = re.compile(r"[0-9]{1,10}")


def parse_optional_id(raw, label: str) -> int | None:
    """An id from a form or a query string (§7.8). Empty is None; anything malformed
    is a 422, never silently "no id". An id in the URL path is a PathId."""
    text = str(raw or "").strip()
    if not text:
        return None
    if not _ID_TEXT.fullmatch(text):
        raise ValidationError(f"Invalid {label}.", fields={label: "invalid"})
    return int(text)


class PathId(int):
    """An id in the URL path (§7.8), as the type of the route parameter
    (`entry_id: PathId`): FastHTML builds it from the path segment.

    Only ASCII digits, like parse_optional_id. With `int`, FastHTML used `int()`,
    which takes other Unicode digits (`٨`, `８`) and underscores (`1_7`), and
    answered a malformed id with a bare 404. A malformed id is a 400 through the
    global boundary (error_conventions.md §3.1); a valid one with nothing visible
    stays a 404 from the route.
    """

    def __new__(cls, raw):
        text = str(raw)
        if not _ID_TEXT.fullmatch(text):
            raise MalformedRequestError("Invalid id in the URL path.")
        return super().__new__(cls, int(text))


class Clear:
    """Sentinel for a partial update: "present but empty", write NULL (7.4).

    A field left out of the payload is `None` ("do not touch"); an explicit
    clearing is the `CLEAR` singleton. The two states cannot share a value.
    """

    def __repr__(self) -> str:
        return "CLEAR"


CLEAR = Clear()


def sql_in_list(enum_cls) -> str:
    """List of the enum's values for a CHECK: "'rapid', 'basal'".

    The values are code constants, not request data: the parametrization rule
    of code_conventions.md 11.9 refers to dynamic values. Generating it here
    guarantees that the CHECK always matches the enum (4.4).
    """
    return ", ".join(f"'{member.value}'" for member in enum_cls)
