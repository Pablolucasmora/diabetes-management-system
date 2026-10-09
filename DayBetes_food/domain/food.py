"""Rules shared by `catalog` and `manual_intake` that are not nutrient limits.

This module imports no psycopg, routes or components (code_conventions.md
§3.6). Nutrient limits and the smart-macros parser live in domain/nutrition.py;
the rules here are the name/origin normalization, the subtype limit, the
default serving and the declared-confidence scale, which both entities share.
An entity never imports rules from another entity's module.
"""

from DayBetes_food.domain.nutrition import NumericRange, parse_number
from DayBetes_food.errors import ValidationError

FOOD_SUBTYPE_MAX_LENGTH = 100  # = VARCHAR(100) in catalog and manual_intake

# Default serving (measurement_conventions.md §5.3, decisions 2026-09-25 and
# 2026-10-09): one constant for both tables. It is a serving, not a physical
# limit.
FOOD_DEFAULT_PORTION_RANGE = NumericRange(0, 3000, minimum_exclusive=True)

# Decision 2026-09-25 (R3): initial amount of a one-click add when the food has
# no serving. It is NOT a serving nor a §4.3 equivalence.
INITIAL_AMOUNT_WITHOUT_SERVING_G = 100.0

# Declared confidence, ordinal 0-2 (measurement_conventions.md §6.10). Shared
# by catalog.macros_confidence, manual_intake.macros_confidence and
# manual_intake.ig_confidence.
FOOD_CONFIDENCE_MIN = 0
FOOD_CONFIDENCE_MAX = 2

_CONFIDENCE_LABELS = {"ig_confidence": "IG confidence", "macros_confidence": "macros confidence"}


def normalize_food_text(raw) -> str:
    """The single normalization of food names and manual_intake origins (§7.3,
    §11.5): strip + collapse any whitespace run (newlines and tabs included)
    into one space. Case is kept; the unique indexes and the copy-name queries
    compare lower(...) in SQL."""
    return " ".join(str(raw or "").split())


def parse_food_subtype(raw, *, required: bool) -> str | None:
    """Strip; '' -> None, or ValidationError when `required`; longer than
    FOOD_SUBTYPE_MAX_LENGTH -> ValidationError (never truncated, §7.3)."""
    subtype = str(raw or "").strip()
    if not subtype:
        if required:
            raise ValidationError("Subtype is required.", fields={"subtype": "required"})
        return None
    if len(subtype) > FOOD_SUBTYPE_MAX_LENGTH:
        raise ValidationError(
            f"Subtype must be {FOOD_SUBTYPE_MAX_LENGTH} characters or fewer.",
            fields={"subtype": "too_long"},
        )
    return subtype


def parse_default_portion(raw) -> float | None:
    return parse_number(raw, "default_portion", FOOD_DEFAULT_PORTION_RANGE)


def parse_declared_confidence(raw, *, field: str) -> int | None:
    """'' -> None; exactly '0', '1' or '2' -> int; anything else ->
    ValidationError (measurement §6.10)."""
    text = str(raw or "").strip()
    if not text:
        return None
    allowed = {str(value): value for value in range(FOOD_CONFIDENCE_MIN, FOOD_CONFIDENCE_MAX + 1)}
    if text not in allowed:
        raise ValidationError(
            f"Invalid {_CONFIDENCE_LABELS.get(field, field.replace('_', ' '))}.",
            fields={field: "invalid"},
        )
    return allowed[text]
