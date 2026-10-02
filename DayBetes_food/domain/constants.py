"""Domain enums (conventions/code_conventions.md §3.6 and §4.1).

This module imports no psycopg, routes or components. Each concept has a
single enum here; no parallel lists of the same concept are created in
routes/, components/, crud.py or schema.py.
"""

from enum import Enum, unique

from DayBetes_food.errors import ValidationError


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
