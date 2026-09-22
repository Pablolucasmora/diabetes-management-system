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
    CONSERVATION_OPTIONS,
    COOKING_OPTIONS,
    INITIAL_STATE_OPTIONS,
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

# Whitelist per preparation field (T2.2). `final_state` reuses the initial
# state options: both describe the same closed set (4.6).
_PREPARATION_OPTIONS = {
    "cooking": COOKING_OPTIONS,
    "conservation": CONSERVATION_OPTIONS,
    "final_state": INITIAL_STATE_OPTIONS,
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


def amount_to_grams(value: float, unit: AmountInputUnit, serving_grams: float) -> float:
    """Convert an amount typed in `unit` to grams (measurement_conventions.md 4.2, 11).

    The single server-side conversion of every amount boundary (decision
    2026-09-22): `lb`/`oz` use the exact factor of the central enum, `portion`
    uses `serving_grams` —the food's serving, which the caller resolves from
    the database, never from a hidden form field (code_conventions.md 7.13)—
    and `g` is identity. `%` is not a mass and is rejected here: it is always
    relative to a total the caller owns. The result is not validated; the
    caller applies `parse_amount_grams` to it.
    """
    unit = AmountInputUnit(unit)
    if unit is AmountInputUnit.PORTION:
        return value * float(serving_grams)
    if unit.grams_factor is None:
        raise ValidationError("amount_unit_not_admitted")
    return value * unit.grams_factor


def validate_preparation_choice(field: str, value):
    """Validate `cooking`/`conservation`/`final_state` against its whitelist (T2.2).

    Defence in depth (7.10): persistence cannot accept any string just because
    the live list is used in presentation. `None` is "no value" and passes;
    the `CLEAR` sentinel is an order to empty and is checked before calling.
    """
    if value is None:
        return None
    options = _PREPARATION_OPTIONS[field]
    if value not in options:
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
    unit_g: float                 # catalog.default_portion | manual_intake.amount_g
    category: str | None
    subtype: str | None
    cooking_factor: float | None  # catalog only; None for manual_intake
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
    cooking: str | None
    conservation: str | None
    final_state: str | None
    strictly_weighed: bool | None   # None = no data (decision 2026-09-18)
    macros_quality: bool | None
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
    cooking: str | None = None
    conservation: str | None = None
    final_state: str | None = None
    strictly_weighed: bool | None = None
    macros_quality: bool | None = None
    is_cooked_weight: bool = False
    offset_minutes: int | None = None


@dataclass(frozen=True)
class PortionDetailUpdate:
    """Partial update. None = leave as is; CLEAR = write NULL (7.4)."""
    cooking: str | None | Clear = None
    conservation: str | None | Clear = None
    final_state: str | None | Clear = None
