"""Dataclasses and pure rules for `catalog` (conventions §3.1, §3.6, §7.11).

This module imports no psycopg, routes or components. The SQL-row-to-dataclass
conversion lives in DayBetes_food/database/mappers.py, not here. Numeric limits
of nutrients and the smart-macros parser live in domain/nutrition.py, and the
name normalization, subtype limit and default serving in domain/food.py,
because `catalog` and `manual_intake` share them.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import FoodCategory, FoodPhysicalState, Nutriscore, PrefillSource
from DayBetes_food.domain.food import normalize_food_text
from DayBetes_food.domain.nutrition import NutrientValues, NumericRange, parse_number
from DayBetes_food.errors import ValidationError

CATALOG_NAME_MAX_LENGTH = 255  # = VARCHAR(255)
CATALOG_BARCODE_MIN_LENGTH = 8
CATALOG_BARCODE_MAX_LENGTH = 48  # = VARCHAR(48)
CATALOG_PREFILL_SOURCE_ID_MAX_LENGTH = 64  # = VARCHAR(64)

CATALOG_COOKING_FACTOR_RANGE = NumericRange(0, 10, minimum_exclusive=True)

_BARCODE_RE = re.compile(rf"[0-9]{{{CATALOG_BARCODE_MIN_LENGTH},{CATALOG_BARCODE_MAX_LENGTH}}}")


def parse_catalog_name(raw) -> str:
    """Required name, <= CATALOG_NAME_MAX_LENGTH after normalizing."""
    name = normalize_food_text(raw)
    if not name:
        raise ValidationError("Name is required.", fields={"name": "required"})
    if len(name) > CATALOG_NAME_MAX_LENGTH:
        raise ValidationError(
            f"Name must be {CATALOG_NAME_MAX_LENGTH} characters or fewer.",
            fields={"name": "too_long"},
        )
    return name


def parse_barcode(raw) -> str | None:
    """Strip; '' -> None; otherwise only digits, 8 to 48, else ValidationError."""
    barcode = str(raw or "").strip()
    if not barcode:
        return None
    if not _BARCODE_RE.fullmatch(barcode):
        raise ValidationError(
            f"Barcode must contain only digits ({CATALOG_BARCODE_MIN_LENGTH} to {CATALOG_BARCODE_MAX_LENGTH}).",
            fields={"barcode": "format"},
        )
    return barcode


def barcode_search_codes(raw) -> list[str]:
    """The codes a search term may refer to; [] if it is not a barcode.

    A UPC-A scans as 12 digits and Open Food Facts stores it as 13, with a
    leading zero, so each form also looks for the other one.
    """
    term = str(raw or "").strip()
    if not _BARCODE_RE.fullmatch(term):
        return []
    if len(term) == 12:
        return [term, f"0{term}"]
    if len(term) == 13 and term.startswith("0"):
        return [term, term[1:]]
    return [term]


def parse_prefill_reference(raw_source, raw_source_id) -> tuple[PrefillSource | None, str | None]:
    """Both or neither (ck_catalog_prefill_reference). They arrive as hidden
    fields, so they are validated like any other input."""
    source = str(raw_source or "").strip()
    source_id = str(raw_source_id or "").strip()
    if not source and not source_id:
        return None, None
    try:
        parsed_source = PrefillSource(source)
    except ValueError as exc:
        raise ValidationError("Invalid prefill source.", fields={"prefill_source": "invalid"}) from exc
    if not source_id or len(source_id) > CATALOG_PREFILL_SOURCE_ID_MAX_LENGTH:
        raise ValidationError("Invalid prefill reference.", fields={"prefill_source_id": "invalid"})
    return parsed_source, source_id


def parse_cooking_factor(raw) -> float | None:
    return parse_number(raw, "cooking_factor", CATALOG_COOKING_FACTOR_RANGE)


@dataclass(frozen=True)
class CatalogItemRead:
    id: int
    created_by: int | None
    origin_root_id: int | None
    name: str
    brand_id: int | None
    brand: str | None
    category: FoodCategory
    subtype: str
    initial_state: FoodPhysicalState | None
    nutriscore: Nutriscore | None
    nova: int | None
    yuka: int | None
    default_portion: float | None
    calories_100g: float | None
    carbs_100g: float | None
    sugars_100g: float | None
    fats_100g: float | None
    saturated_100g: float | None
    proteins_100g: float | None
    fiber_100g: float | None
    caffeine: float | None
    alcohol: float | None
    barcode: str | None
    cooking_factor: float | None
    # Decision 2026-10-09 (measurement §6.10, §6.11). None = no data.
    macros_quality: bool | None  # the food's data, read live by portions
    default_strictly_weighed: bool | None  # copied to each new portion
    macros_confidence: int | None  # declared, ordinal 0-2
    is_published: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    is_favorite: bool
    can_edit: bool
    is_listable: bool

    @property
    def is_archived(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_library(self) -> bool:
        return self.created_by is None


@dataclass(frozen=True)
class CatalogItemCreate:
    """No is_published: the DB default FALSE makes it personal (§11.4.1, R5)."""

    created_by: int
    origin_root_id: int | None
    name: str
    brand_id: int | None
    category: FoodCategory
    subtype: str
    initial_state: FoodPhysicalState | None
    nutriscore: Nutriscore | None
    nova: int | None
    yuka: int | None
    default_portion: float | None
    nutrients: NutrientValues
    barcode: str | None
    cooking_factor: float | None
    # Decision 2026-10-09 (measurement §6.10, §6.11). None = no data.
    macros_quality: bool | None  # the food's data, read live by portions
    default_strictly_weighed: bool | None  # copied to each new portion
    macros_confidence: int | None  # declared, ordinal 0-2
    # Where the form's first values came from (measurement §12.1). None = typed.
    prefill_source: PrefillSource | None = None
    prefill_source_id: str | None = None


@dataclass(frozen=True)
class CatalogItemUpdate:
    """FULL replacement of the editable fields (the edit form sends all of them):
    None means NULL for nullable fields (§3.4, §7.4 declared contract). It does
    not contain created_by, origin_root_id, is_published or deleted_at: those
    change only through their own operations. Its field list IS the update
    whitelist (§4.6, §7.11)."""

    name: str
    brand_id: int | None
    category: FoodCategory
    subtype: str
    initial_state: FoodPhysicalState | None
    nutriscore: Nutriscore | None
    nova: int | None
    yuka: int | None
    default_portion: float | None
    nutrients: NutrientValues
    barcode: str | None
    cooking_factor: float | None
    # Decision 2026-10-09 (measurement §6.10, §6.11). None = no data.
    macros_quality: bool | None  # the food's data, read live by portions
    default_strictly_weighed: bool | None  # copied to each new portion
    macros_confidence: int | None  # declared, ordinal 0-2


@dataclass(frozen=True)
class CatalogItemRequest:
    """HTTP form already parsed and validated (§3.1, §7.11); never reaches
    persistence."""

    name: str
    brand_label: str | None
    brand_is_new: bool
    category: FoodCategory
    subtype: str
    subtype_is_new: bool
    initial_state: FoodPhysicalState | None
    nutriscore: Nutriscore | None
    nova: int | None
    yuka: int | None
    default_portion: float | None
    nutrients: NutrientValues
    barcode: str | None
    cooking_factor: float | None
    # Decision 2026-10-09 (measurement §6.10, §6.11). None = no data.
    macros_quality: bool | None  # the food's data, read live by portions
    default_strictly_weighed: bool | None  # copied to each new portion
    macros_confidence: int | None  # declared, ordinal 0-2
    favorite: bool | None
    prefill_source: PrefillSource | None = None
    prefill_source_id: str | None = None
