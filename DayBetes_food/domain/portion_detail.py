"""Dataclasses and pure rules for `portion_detail` (conventions §3.1, §3.6).

This module imports no psycopg, routes or components. The SQL-row-to-dataclass
conversion lives in DayBetes_food/database/mappers.py, not here.

A row of `portion_detail` is one amount of a food assigned to a destination.
It has two exclusive arcs, both reinforced with `num_nonnulls(...) = 1`:
origin (`catalog` | `manual_intake`) and destination (`intake_event` |
`recipe` | `fridge`).
"""

import math
from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import (
    AmountInputUnit,
    ConservationMethod,
    CookingMethod,
    FoodPhysicalState,
    MASS_SANITY_MAX_G,
    Clear,
    PortionDestination,
    PortionOrigin,
)
from DayBetes_food.errors import ValidationError

# Upper sanity bound of a portion amount, shared with intake_event
# (measurement_conventions.md 4.4 / 6.9.2). Same value as the CHECK
# ck_portion_detail_amount_range in database/schema.py.
PORTION_DETAIL_AMOUNT_MAX_G = MASS_SANITY_MAX_G

# Range of offset_minutes (measurement_conventions.md 4.5). Same values as
# intake_plate.offset_minutes: the template cannot accept a range the row
# would reject (4.6.2).
PORTION_DETAIL_OFFSET_MIN_MINUTES = -300
PORTION_DETAIL_OFFSET_MAX_MINUTES = 300

# Closed set per preparation field (decision 2026-09-25, §4.1). The text-to-enum
# conversion already happened at the boundary with parse_enum.
_PREPARATION_ENUMS = {
    "cooking": CookingMethod,
    "conservation": ConservationMethod,
    "final_state": FoodPhysicalState,
}


def parse_amount_grams(value) -> float:
    """Validate a mass in grams before it reaches the database (7.5).

    Rejects NaN/Infinity, non-positive values and anything above the sanity
    ceiling. The CHECK in the database is the last barrier, not the first: a
    constraint violation would surface as a 500 instead of a 422.
    """
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError("amount_not_finite")
    if value <= 0:
        raise ValidationError("amount_not_positive")
    if value > PORTION_DETAIL_AMOUNT_MAX_G:
        raise ValidationError("amount_above_max")
    return float(value)


def amount_to_grams(value: float, unit: AmountInputUnit, serving_grams: float | None) -> float:
    """Convert an amount typed in `unit` to grams (measurement_conventions.md 4.2, 11).

    The single server-side conversion of every amount boundary (decision
    2026-09-22): `lb`/`oz` use the exact factor of the central enum, `portion`
    uses `serving_grams` —the food's serving, which the caller resolves from
    the database, never from a hidden form field (code_conventions.md 7.13)—
    and `g` is identity. `%` is not a mass and is rejected here: it is always
    relative to a total the caller owns. A `portion` unit with no serving
    (`serving_grams is None`) is rejected (H15, decision 2026-09-25). The
    result is not validated; the caller applies `parse_amount_grams` to it.
    """
    unit = AmountInputUnit(unit)
    if unit is AmountInputUnit.PORTION:
        if serving_grams is None:
            raise ValidationError("amount_unit_not_admitted")
        return value * float(serving_grams)
    if unit.grams_factor is None:
        raise ValidationError("amount_unit_not_admitted")
    return value * unit.grams_factor


def validate_preparation_choice(field: str, value):
    """Validate `cooking`/`conservation`/`final_state` against its enum (T2.2).

    Defence in depth (7.10): persistence cannot accept any string just because
    the live list is used in presentation. `None` is "no value" and passes;
    the `CLEAR` sentinel is an order to empty and is checked before calling.
    """
    if value is None:
        return None
    enum_cls = _PREPARATION_ENUMS[field]
    if not isinstance(value, enum_cls):
        raise ValidationError(f"invalid_{field}")
    return value


@dataclass(frozen=True)
class PortionSourceRead:
    """The food a portion points to, read through the JOIN of its origin arc.

    Lives here, and not inside PortionDetailRead as loose keys, because these
    columns belong to catalog/manual_intake: the portion row does not store a
    single nutritional value (finding 1, still open).
    """
    name: str | None
    unit_g: float | None           # catalog.default_portion | manual_intake.default_portion; None = no serving
    category: str | None
    subtype: str | None
    cooking_factor: float | None  # catalog only; None for manual_intake
    # The food's, read live (measurement §6.11, decision 2026-10-09): the
    # portion does not store a copy. None = no data.
    macros_quality: bool | None
    calories_100g: float | None
    carbs_100g: float | None
    sugars_100g: float | None
    fats_100g: float | None
    saturated_100g: float | None
    proteins_100g: float | None
    fiber_100g: float | None


@dataclass(frozen=True)
class PortionDetailRead:
    id: int
    origin: PortionOrigin
    origin_id: int
    destination: PortionDestination
    destination_id: int
    plate_id: int | None
    amount: float
    cooking: CookingMethod | None
    conservation: ConservationMethod | None
    final_state: FoodPhysicalState | None
    strictly_weighed: bool | None   # None = no data (decision 2026-09-18)
    is_cooked_weight: bool
    offset_minutes: int | None
    created_at: datetime
    updated_at: datetime
    source: PortionSourceRead


@dataclass(frozen=True)
class PortionDetailCreate:
    origin: PortionOrigin
    origin_id: int
    destination: PortionDestination
    destination_id: int
    amount: float
    plate_id: int | None = None
    cooking: CookingMethod | None = None
    conservation: ConservationMethod | None = None
    final_state: FoodPhysicalState | None = None
    strictly_weighed: bool | None = None
    is_cooked_weight: bool = False
    offset_minutes: int | None = None


@dataclass(frozen=True)
class PortionDetailUpdate:
    """Partial update. None = leave as is; CLEAR = write NULL (7.4)."""
    cooking: CookingMethod | None | Clear = None
    conservation: ConservationMethod | None | Clear = None
    final_state: FoodPhysicalState | None | Clear = None


# ============================================
# Amounts and event metrics over portions
# ============================================

# Macro of the food and the event uncertainty column it feeds (measurement_conventions.md §6.6).
MACRO_UNCERTAINTY_KEYS = (
    ("carbs", "carbs_uncertainty"),
    ("sugars", "sugars_uncertainty"),
    ("fats", "fats_uncertainty"),
    ("saturated", "saturated_uncertainty"),
    ("proteins", "proteins_uncertainty"),
    ("fiber", "fiber_uncertainty"),
)


def parse_source_macro(portion, macro_key: str):
    return getattr(portion.source, f"{macro_key}_100g")


def portion_intake_amount(portion) -> float:
    """Amount of a portion in grams (measurement_conventions.md 4.4).

    `portion_detail` has a single amount column since decision 2026-09-18.
    """
    return float(portion.amount)


def portion_macro_amount(portion) -> float:
    """Amount used to compute macros (measurement_conventions.md 5.2).

    catalog macros are expressed per 100 g of RAW food, so a weight taken
    already cooked is converted back with cooking_factor = cooked/raw. The
    conversion is never persisted: `amount` keeps what the user weighed
    (decision 2026-09-18). Only catalog origins; manual_intake has no factor.
    """
    amount = float(portion.amount)
    if not portion.is_cooked_weight or portion.origin is not PortionOrigin.CATALOG:
        return amount
    factor = portion.source.cooking_factor
    if factor is None:
        # Defence of the calculation for inherited portions (decisions
        # 2026-09-24 / 2026-09-25), not a default value.
        return amount
    return amount / factor if factor > 0 else amount


def calculate_macro_summary_metrics(portions) -> dict:
    total_amount = sum(portion_intake_amount(p) for p in portions)
    amount_confidence_num = 0.0
    quality_confidence_num = 0.0
    for portion in portions:
        amount = portion_intake_amount(portion)
        # NULL means "no data" (decision 2026-09-18): it does not add to the
        # numerator, same as False, but said explicitly instead of `bool()`
        # (code_conventions.md 3.2: decide whether NULL is zero or absence).
        amount_confidence_num += amount * (1.0 if portion.strictly_weighed is True else 0.0)
        # The food's quality, read live (measurement §6.5, §6.11).
        quality_confidence_num += amount * (1.0 if portion.source.macros_quality is True else 0.0)

    metrics = {
        "amount_confidence": (amount_confidence_num / total_amount) if total_amount > 0 else 0.0,
        "quality_confidence": (quality_confidence_num / total_amount) if total_amount > 0 else 0.0,
    }

    for macro_key, uncertainty_key in MACRO_UNCERTAINTY_KEYS:
        unknown_amount = 0.0
        for portion in portions:
            amount = portion_intake_amount(portion)
            if parse_source_macro(portion, macro_key) is None:
                unknown_amount += amount
        metrics[uncertainty_key] = (unknown_amount / total_amount) if total_amount > 0 else 0.0

    return metrics
