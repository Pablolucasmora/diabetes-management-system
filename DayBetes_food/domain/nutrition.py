"""Shared nutrition rules for `catalog` and `manual_intake`.

This module imports no psycopg, routes or components. It holds the numeric
limits of every nutrient, the strict numeric parser and the smart-macros
parser, declared once and shared by both entities (conventions
code_conventions.md §3.6, decision 2026-09-25). An entity never imports rules
from another entity's module.
"""

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Mapping

from DayBetes_food.errors import ValidationError

# Physical sanity ceilings, not clinical limits (measurement_conventions.md
# §5.3, decision 2026-09-25). Every field admits NULL.
NUTRIENT_FIELDS = (
    "calories_100g",
    "carbs_100g",
    "sugars_100g",
    "fats_100g",
    "saturated_100g",
    "proteins_100g",
    "fiber_100g",
    "caffeine",
    "alcohol",
)
SMART_MACRO_FIELDS = NUTRIENT_FIELDS[:7]

# Density of ethanol (measurement_conventions.md §5.1, decision 2026-09-25):
# OFF declares alcohol in % vol; converting to g/100 g multiplies by this.
ETHANOL_DENSITY_G_PER_ML = 0.789


@dataclass(frozen=True)
class NumericRange:
    minimum: float
    maximum: float
    minimum_exclusive: bool = False


NUTRIENT_LIMITS = {
    "calories_100g": NumericRange(0, 900),
    "carbs_100g": NumericRange(0, 100),
    "sugars_100g": NumericRange(0, 100),
    "fats_100g": NumericRange(0, 100),
    "saturated_100g": NumericRange(0, 100),
    "proteins_100g": NumericRange(0, 100),
    "fiber_100g": NumericRange(0, 100),
    "caffeine": NumericRange(0, 100000),  # mg/100 g
    "alcohol": NumericRange(0, 100),  # g/100 g
}

# Human labels for validation messages (English, latin-1, error §7.1).
_FIELD_LABELS = {
    "calories_100g": "Calories per 100 g",
    "carbs_100g": "Carbs per 100 g",
    "sugars_100g": "Sugars per 100 g",
    "fats_100g": "Fats per 100 g",
    "saturated_100g": "Saturated fat per 100 g",
    "proteins_100g": "Proteins per 100 g",
    "fiber_100g": "Fiber per 100 g",
    "caffeine": "Caffeine",
    "alcohol": "Alcohol",
    "default_portion": "Default serving size",
    "cooking_factor": "Cooking factor",
}


def _label(field: str) -> str:
    return _FIELD_LABELS.get(field, field.replace("_", " "))


def _range_message(field: str, limits: NumericRange) -> str:
    minimum = _format_number(limits.minimum)
    maximum = _format_number(limits.maximum)
    if limits.minimum_exclusive:
        return f"{_label(field)} must be greater than {minimum} and at most {maximum}."
    return f"{_label(field)} must be between {minimum} and {maximum}."


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(float(value))


@dataclass(frozen=True)
class NutrientValues:
    calories_100g: float | None = None
    carbs_100g: float | None = None
    sugars_100g: float | None = None
    fats_100g: float | None = None
    saturated_100g: float | None = None
    proteins_100g: float | None = None
    fiber_100g: float | None = None
    caffeine: float | None = None
    alcohol: float | None = None


def check_number(value, field: str, limits: NumericRange) -> float | None:
    """Finite + range check of an already-parsed value (smart macros, OFF).

    `None` passes. A non-finite value or one outside `limits` raises
    `ValidationError`; it is never silently converted to `None`.
    """
    if value is None:
        return None
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"{_label(field)} must be a number.", fields={field: "invalid"})
    if (
        value < limits.minimum
        or (limits.minimum_exclusive and value == limits.minimum)
        or value > limits.maximum
    ):
        raise ValidationError(_range_message(field, limits), fields={field: "out_of_range"})
    return float(value)


_DECIMAL_TEXT = re.compile(r"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")


def parse_number(raw, field: str, limits: NumericRange, *, integer: bool = False) -> float | None:
    """'' -> None; '12,5' -> 12.5; 'abc'/NaN/Infinity/out of range -> ValidationError.

    Text is never converted to `None` (decision 2026-09-25). With `integer=True`
    a decimal value is rejected, never rounded ('2.5' -> ValidationError)."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", ".")
    if not text:
        return None
    # Only plain decimals: float() would also take "1_0", "1e3" or "inf".
    if not _DECIMAL_TEXT.fullmatch(text):
        raise ValidationError(f"{_label(field)} must be a number.", fields={field: "invalid"})
    parsed = float(text)
    if integer and not float(parsed).is_integer():
        raise ValidationError(f"{_label(field)} must be a whole number.", fields={field: "invalid"})
    return check_number(parsed, field, limits)


def validate_nutrient_relations(values: NutrientValues) -> None:
    """sugars <= carbs and saturated <= fats when both are present (§7.9)."""
    if values.sugars_100g is not None and values.carbs_100g is not None:
        if values.sugars_100g > values.carbs_100g:
            raise ValidationError(
                "Sugars cannot be greater than carbs.", fields={"sugars_100g": "relation"}
            )
    if values.saturated_100g is not None and values.fats_100g is not None:
        if values.saturated_100g > values.fats_100g:
            raise ValidationError(
                "Saturated fat cannot be greater than fats.", fields={"saturated_100g": "relation"}
            )


def parse_nutrients(raw: Mapping[str, str | None]) -> NutrientValues:
    """Parse the nine fields from visible form inputs + relations."""
    values = {}
    for field in NUTRIENT_FIELDS:
        values[field] = parse_number(raw.get(field), field, NUTRIENT_LIMITS[field])
    result = NutrientValues(**values)
    validate_nutrient_relations(result)
    return result


# ============================================
# SMART MACROS (same grammar as static/js/smart_macros.js)
# ============================================

# Grammar: a sequence of "<number> [unit] <macro name>" pairs, e.g.
# "120kcal 30 hc 12,5 g azucar 20 proteinas". The number always goes first.
# Pairs are separated by spaces, ",", ";" or "+". Any other text (a name
# before its number, an unknown name, a repeated macro, a number without a
# name) is rejected, never guessed (§7.2). Names are matched exactly after
# normalize_smart_token, so a partial word is never read as another macro.
_MACRO_FAMILIES = (
    ("calories_100g", ("kcal", "kcals", "kca", "caloria", "calorias", "calorie", "calories", "cal", "cals", "energia", "ener", "ene")),
    ("carbs_100g", ("hc", "ch", "hidrato", "hidratos", "hidrato de carbono", "hidratos de carbono", "carbo", "carbos", "carbohidrato", "carbohidratos", "carbohydrate", "carbohydrates", "carb", "carbs")),
    ("sugars_100g", ("az", "azu", "azuc", "azuca", "azucar", "azucare", "azucares", "sugar", "sugars")),
    ("proteins_100g", ("pr", "pro", "prot", "prote", "protein", "protei", "proteina", "proteinas", "proteins")),
    ("fats_100g", ("gr", "gra", "gras", "grasa", "grasas", "fat", "fats", "lipido", "lipidos", "lipid", "lipids")),
    ("saturated_100g", ("sat", "satu", "satur", "satura", "saturada", "saturadas", "grasa saturada", "grasas saturadas", "saturated", "saturated fat", "saturated fats", "st", "gs")),
    ("fiber_100g", ("fb", "fib", "fibr", "fibra", "fibras", "fiber", "fibers", "fibre", "fibres")),
)
_MACRO_ALIASES = {alias: field for field, aliases in _MACRO_FAMILIES for alias in aliases}
# A unit between the number and the name is optional and carries no meaning
# (values are per 100 g). It is only dropped when a name follows it, so
# "30gr" alone keeps its fats reading.
_SMART_UNITS = ("g", "gr", "gramos", "ml")

# [0-9] and explicit whitespace, not \d/\s: they differ between Python and
# JavaScript. The text is normalized first, so names are plain [a-z].
_SMART_SEPARATORS = re.compile(r"[ \t\r\n,;+]*")
_SMART_NUMBER = re.compile(r"[0-9]+(?:[.,][0-9]+)?")
_SMART_NAME = re.compile(r"[ \t\r\n]*([a-z]+(?:[ \t\r\n]+[a-z]+)*)")


def normalize_smart_token(token) -> str:
    """Lower case, NFD, drop combining marks (same as normalizeText in the JS)."""
    text = str(token or "").lower()
    text = unicodedata.normalize("NFD", text)
    return re.sub(r"[\u0300-\u036f]", "", text)


def _smart_error(message: str, code: str) -> ValidationError:
    return ValidationError(message, fields={"smart_macros": code})


def parse_smart_macros(text: str) -> dict[str, float | None]:
    """Parse the smart-macros text; the JS runs the same steps and messages.

    Empty text -> every field None. Text outside the grammar -> ValidationError
    with `fields={"smart_macros": code}`.
    """
    result: dict[str, float | None] = {field: None for field in SMART_MACRO_FIELDS}
    raw = normalize_smart_token(text)
    position = 0
    while True:
        position = _SMART_SEPARATORS.match(raw, position).end()
        if position >= len(raw):
            return result
        number = _SMART_NUMBER.match(raw, position)
        if number is None:
            raise _smart_error(
                "Write each value as a number followed by its macro, e.g. '30 carbs 20 proteins'.",
                "number_first",
            )
        name = _SMART_NAME.match(raw, number.end())
        if name is None:
            raise _smart_error(f"Add the macro name after {number.group(0)}.", "missing_macro")
        words = name.group(1).split()
        if len(words) > 1 and words[0] in _SMART_UNITS:
            words = words[1:]
        label = " ".join(words)
        field = _MACRO_ALIASES.get(label)
        if field is None:
            raise _smart_error(f"Unknown macro '{label}'.", "unknown_macro")
        if result[field] is not None:
            raise _smart_error(f"Macro '{label}' is written more than once.", "duplicate_macro")
        result[field] = float(number.group(0).replace(",", "."))
        position = name.end()


def nutrients_from_smart_text(text: str, caffeine_raw, alcohol_raw) -> NutrientValues:
    """Server-side smart macros (decision 2026-09-25): hidden fields are ignored.

    Text outside the grammar -> ValidationError (parse_smart_macros). Every
    value goes through check_number + validate_nutrient_relations.
    """
    parsed = parse_smart_macros(text)
    values: dict[str, float | None] = {}
    for field in SMART_MACRO_FIELDS:
        values[field] = check_number(parsed.get(field), field, NUTRIENT_LIMITS[field])
    values["caffeine"] = parse_number(caffeine_raw, "caffeine", NUTRIENT_LIMITS["caffeine"])
    values["alcohol"] = parse_number(alcohol_raw, "alcohol", NUTRIENT_LIMITS["alcohol"])
    result = NutrientValues(**values)
    validate_nutrient_relations(result)
    return result
