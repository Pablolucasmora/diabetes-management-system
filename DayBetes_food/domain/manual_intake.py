"""Dataclasses and pure rules for `manual_intake` (code_conventions.md §3.1,
§3.6, §7.11, §11.2.3).

This module imports no psycopg, routes or components. The SQL-row-to-dataclass
conversion lives in DayBetes_food/database/mappers.py. Nutrient limits live in
domain/nutrition.py and the rules shared with `catalog` (name/origin
normalization, subtype limit, default serving) in domain/food.py.
"""

from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import GlycemicIndex
from DayBetes_food.domain.food import FOOD_DEFAULT_PORTION_RANGE, normalize_food_text
from DayBetes_food.domain.nutrition import NutrientValues, parse_number
from DayBetes_food.errors import ValidationError

MANUAL_INTAKE_NAME_MAX_LENGTH = 255  # = VARCHAR(255)
MANUAL_INTAKE_ORIGIN_MAX_LENGTH = 255  # = VARCHAR(255) (decision 2026-10-09)
# TEXT column: the limit is a domain rule (§7.3, decision 2026-10-09). It also
# covers the quick-add notes, stored in the same column.
MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH = 500
# Declared confidence, ordinal 0-2 (measurement §6.10). Shared by
# macros_confidence and ig_confidence. Moves to domain/food.py the day catalog
# gets macros_confidence.
MANUAL_INTAKE_CONFIDENCE_MIN = 0
MANUAL_INTAKE_CONFIDENCE_MAX = 2

_CONFIDENCE_LABELS = {"ig_confidence": "IG confidence", "macros_confidence": "macros confidence"}


def _too_long(label: str, field: str, maximum: int) -> ValidationError:
    return ValidationError(
        f"{label} must be {maximum} characters or fewer.", fields={field: "too_long"}
    )


def parse_manual_intake_name(raw) -> str:
    """Required name, normalized (normalize_food_text), <= 255 characters."""
    name = normalize_food_text(raw)
    if not name:
        raise ValidationError("Name is required.", fields={"name": "required"})
    if len(name) > MANUAL_INTAKE_NAME_MAX_LENGTH:
        raise _too_long("Name", "name", MANUAL_INTAKE_NAME_MAX_LENGTH)
    return name


def parse_manual_intake_origin(raw) -> str | None:
    """Optional free-text origin (decision 2026-10-09): normalized with the same
    function as the name; '' -> None; <= 255 characters."""
    origin = normalize_food_text(raw)
    if not origin:
        return None
    if len(origin) > MANUAL_INTAKE_ORIGIN_MAX_LENGTH:
        raise _too_long("Origin", "origin", MANUAL_INTAKE_ORIGIN_MAX_LENGTH)
    return origin


def parse_manual_intake_description(raw) -> str | None:
    """Optional free text: strip only (line breaks are kept); '' -> None;
    <= 500 characters, never truncated."""
    description = str(raw or "").strip()
    if not description:
        return None
    if len(description) > MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH:
        raise _too_long("Description", "description", MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH)
    return description


def parse_declared_confidence(raw, *, field: str) -> int | None:
    """'' -> None; exactly '0', '1' or '2' -> int; anything else ->
    ValidationError (measurement §6.10)."""
    text = str(raw or "").strip()
    if not text:
        return None
    allowed = {
        str(value): value
        for value in range(MANUAL_INTAKE_CONFIDENCE_MIN, MANUAL_INTAKE_CONFIDENCE_MAX + 1)
    }
    if text not in allowed:
        raise ValidationError(
            f"Invalid {_CONFIDENCE_LABELS.get(field, field.replace('_', ' '))}.",
            fields={field: "invalid"},
        )
    return allowed[text]


def parse_quick_add_weight(raw) -> float:
    """Required estimated weight of a quick add (§11.2.3), in
    FOOD_DEFAULT_PORTION_RANGE because it becomes its default_portion."""
    if not str(raw or "").strip():
        raise ValidationError(
            "Estimated weight is required.", fields={"default_portion": "required"}
        )
    try:
        weight = parse_number(raw, "default_portion", FOOD_DEFAULT_PORTION_RANGE)
    except ValidationError as error:
        if error.fields.get("default_portion") == "out_of_range":
            raise ValidationError(
                "Estimated weight must be greater than 0 and at most "
                f"{FOOD_DEFAULT_PORTION_RANGE.maximum:g} g.",
                fields={"default_portion": "out_of_range"},
            ) from error
        raise ValidationError(
            "Estimated weight must be a number.", fields={"default_portion": "invalid"}
        ) from error
    return weight


def require_carbs(nutrients: NutrientValues) -> None:
    """carbs_100g is NOT NULL in manual_intake (§11.2.3): 0 is valid, unknown is not."""
    if nutrients.carbs_100g is None:
        raise ValidationError(
            "Carbs are required. Write 0 if the dish has no carbs.",
            fields={"carbs_100g": "required"},
        )


def validate_ig_confidence(glycemic_index: GlycemicIndex | None, ig_confidence: int | None) -> None:
    """ig_confidence needs a glycemic_index (measurement §6.10, §7.9). Never
    clears ig_confidence silently (§7.2)."""
    if ig_confidence is not None and glycemic_index is None:
        raise ValidationError(
            "IG confidence needs a glycemic index. Choose one or clear the confidence.",
            fields={"ig_confidence": "requires_glycemic_index"},
        )


@dataclass(frozen=True)
class ManualIntakeRead:
    id: int
    created_by: int  # owner: creator = owner, NOT NULL (§11.2.3)
    origin_root_id: int | None
    name: str
    description: str | None
    subtype: str | None
    origin: str | None
    default_portion: float | None  # None = no serving (measurement §5.3)
    calories_100g: float | None
    carbs_100g: float  # NOT NULL; 0 is a real value
    sugars_100g: float | None
    fats_100g: float | None
    saturated_100g: float | None
    proteins_100g: float | None
    fiber_100g: float | None
    caffeine: float | None
    alcohol: float | None
    glycemic_index: GlycemicIndex | None
    ig_confidence: int | None
    macros_confidence: int | None
    default_macros_quality: bool | None  # None = no data (measurement §6.11)
    default_strictly_weighed: bool | None
    is_quick_add: bool
    is_published: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    is_favorite: bool  # computed in SQL for the viewer
    can_edit: bool  # SQL: owner AND active
    is_listable: bool  # SQL: active AND (published OR own)

    @property
    def is_archived(self) -> bool:
        return self.deleted_at is not None


@dataclass(frozen=True)
class ManualIntakeCreate:
    """No is_published: the DB default FALSE makes it personal (§11.4.1)."""

    created_by: int
    origin_root_id: int | None
    name: str
    description: str | None
    subtype: str | None
    origin: str | None
    default_portion: float | None
    nutrients: NutrientValues  # carbs_100g never None (require_carbs)
    glycemic_index: GlycemicIndex | None
    ig_confidence: int | None
    macros_confidence: int | None
    default_macros_quality: bool | None
    default_strictly_weighed: bool | None
    is_quick_add: bool = False


@dataclass(frozen=True)
class ManualIntakeUpdate:
    """FULL replacement of the editable fields of a reusable dish (the edit form
    sends all of them): None means NULL for every nullable field (§3.4, §7.4).
    It does not contain created_by, origin_root_id, is_published, is_quick_add
    or deleted_at: those change only through their own operations. Its field
    list IS the update whitelist (§4.6, §7.11)."""

    name: str
    description: str | None
    subtype: str | None
    origin: str | None
    default_portion: float | None
    nutrients: NutrientValues
    glycemic_index: GlycemicIndex | None
    ig_confidence: int | None
    macros_confidence: int | None
    default_macros_quality: bool | None
    default_strictly_weighed: bool | None


@dataclass(frozen=True)
class ManualIntakeRequest:
    """Reusable-dish form already parsed and validated (§3.1, §7.11); never
    reaches persistence."""

    name: str
    description: str | None
    subtype: str | None
    subtype_is_new: bool
    origin: str | None
    default_portion: float | None
    nutrients: NutrientValues
    glycemic_index: GlycemicIndex | None
    ig_confidence: int | None
    macros_confidence: int | None
    default_macros_quality: bool | None
    default_strictly_weighed: bool | None
    favorite: bool | None  # None = field absent (edit form)
    tags: list[str] | None  # None = field absent


@dataclass(frozen=True)
class QuickAddRequest:
    """Quick-add form already parsed (§11.2.3). Meal and plate are resolved by
    the route (same as /food/log)."""

    name: str
    weight_g: float  # becomes default_portion AND the portion amount
    nutrients: NutrientValues  # already per 100 g (measurement §5.4)
    description: str | None  # the notes
