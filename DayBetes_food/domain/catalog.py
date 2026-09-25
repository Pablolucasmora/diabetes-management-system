"""Dataclasses and pure rules for `catalog` (conventions §3.1, §3.6, §7.11).

This module imports no psycopg, routes or components. The SQL-row-to-dataclass
conversion lives in DayBetes_food/database/mappers.py, not here. Numeric limits
of nutrients and the smart-macros parser live in domain/nutrition.py because
`catalog` and `manual_intake` share them.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import FoodCategory, FoodPhysicalState, Nutriscore
from DayBetes_food.domain.nutrition import NutrientValues, NumericRange, parse_number
from DayBetes_food.errors import ValidationError

CATALOG_NAME_MAX_LENGTH = 255  # = VARCHAR(255)
CATALOG_SUBTYPE_MAX_LENGTH = 100  # = VARCHAR(100)
CATALOG_BARCODE_MIN_LENGTH = 8
CATALOG_BARCODE_MAX_LENGTH = 48  # = VARCHAR(48)

CATALOG_DEFAULT_PORTION_RANGE = NumericRange(0, 3000, minimum_exclusive=True)
CATALOG_COOKING_FACTOR_RANGE = NumericRange(0, 10, minimum_exclusive=True)

# Decision 2026-09-25 (R3): initial amount of a one-click add when the food has
# no serving. It is NOT a serving nor a §4.3 equivalence.
INITIAL_AMOUNT_WITHOUT_SERVING_G = 100.0

_BARCODE_RE = re.compile(rf"[0-9]{{{CATALOG_BARCODE_MIN_LENGTH},{CATALOG_BARCODE_MAX_LENGTH}}}")


def normalize_catalog_name(raw) -> str:
    """The single name normalization (H2): strip + collapse any whitespace run
    (newlines and tabs included) into one space. Case is kept; the unique
    indexes and the copy-name query compare lower(name) in SQL."""
    return " ".join(str(raw or "").split())


def parse_catalog_name(raw) -> str:
    """Required name, <= CATALOG_NAME_MAX_LENGTH after normalizing."""
    name = normalize_catalog_name(raw)
    if not name:
        raise ValidationError("Name is required.", fields={"name": "required"})
    if len(name) > CATALOG_NAME_MAX_LENGTH:
        raise ValidationError(
            f"Name must be {CATALOG_NAME_MAX_LENGTH} characters or fewer.",
            fields={"name": "too_long"},
        )
    return name


def parse_catalog_subtype(raw) -> str:
    """Required subtype, <= CATALOG_SUBTYPE_MAX_LENGTH."""
    subtype = str(raw or "").strip()
    if not subtype:
        raise ValidationError("Subtype is required.", fields={"subtype": "required"})
    if len(subtype) > CATALOG_SUBTYPE_MAX_LENGTH:
        raise ValidationError(
            f"Subtype must be {CATALOG_SUBTYPE_MAX_LENGTH} characters or fewer.",
            fields={"subtype": "too_long"},
        )
    return subtype


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


def parse_default_portion(raw) -> float | None:
    return parse_number(raw, "default_portion", CATALOG_DEFAULT_PORTION_RANGE)


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
    favorite: bool | None
    tags: list[str] | None
