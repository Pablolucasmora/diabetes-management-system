"""Dataclasses and pure rules of an event's plate (serving batch).

See conventions/code_conventions.md §3.6 and
conventions/measurement_conventions.md §4.6 (decision 2026-09-19).

This module imports no psycopg, routes or components. The conversion from a
SQL row to these dataclasses lives in DayBetes_food/database/mappers.py, not here.

A plate splits an `intake_event` into the dishes eaten at different moments,
without splitting the meal into several events: every offset is still
measured against the same `meal_time` (§4.6).
"""

import re
from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import AmountInputUnit
from DayBetes_food.domain.portion_detail import (
    PORTION_DETAIL_OFFSET_MAX_MINUTES,
    PORTION_DETAIL_OFFSET_MIN_MINUTES,
)
from DayBetes_food.errors import ValidationError

# Maximum length of intake_plate.name, equal to the column's VARCHAR(255)
# (database/schema.py). §7.3 requires declaring the maximum length per field
# and rejecting the excess at the boundary with 422, without truncating.
INTAKE_PLATE_NAME_MAX_LENGTH = 255

# Sanity bound for the plate offset: it is portion_detail.offset_minutes',
# imported and not repeated (§4.7), because the template cannot accept values
# the row would reject (measurement_conventions.md §4.5, §4.6.2). Equal to the
# CHECK ck_intake_plate_offset_minutes in database/schema.py.
INTAKE_PLATE_OFFSET_MIN_MINUTES = PORTION_DETAIL_OFFSET_MIN_MINUTES
INTAKE_PLATE_OFFSET_MAX_MINUTES = PORTION_DETAIL_OFFSET_MAX_MINUTES

# Name shown when the plate has neither its own name nor ingredients to derive
# it from (measurement_conventions.md §4.6.3). It is interface text, and the
# interface is in English (frontend_conventions.md §7.12).
#
# It is not an ordinal ("First"): an empty plate can be the event's second or
# third one, and calling it "First" would simply be false. It describes the
# state —no ingredients yet—, which is the only thing known about it.
INTAKE_PLATE_EMPTY_NAME = "Empty plate"

# How many ingredients take part in the derived name.
INTAKE_PLATE_NAME_INGREDIENTS = 2


def check_offset_minutes(value: int | None) -> int | None:
    """An offset within the sanity bound of measurement_conventions.md §4.5
    (`-300..300`), the one the `intake_plate` and `portion_detail` CHECKs declare:
    writing out of range would give a database error instead of a 422.

    Raises:
        ValidationError: out of range.
    """
    if value is not None and not (INTAKE_PLATE_OFFSET_MIN_MINUTES <= value <= INTAKE_PLATE_OFFSET_MAX_MINUTES):
        raise ValidationError(
            f"The offset must be between {INTAKE_PLATE_OFFSET_MIN_MINUTES} and "
            f"{INTAKE_PLATE_OFFSET_MAX_MINUTES} minutes."
        )
    return value


def parse_offset_minutes(raw_value: str) -> int | None:
    """Validate an offset in minutes typed in a form (code_conventions.md §7.4, §7.5).

    Empty is None: the offset is unknown, and it clears the stored value. Anything
    else is a whole number within `check_offset_minutes`.

    Raises:
        ValidationError: it is not an integer or is out of range.
    """
    text = (raw_value or "").strip()
    if not text:
        return None
    # Only ASCII digits: int() would also take "1_0" or other scripts' digits (§7.5).
    if not re.fullmatch(r"-?[0-9]{1,4}", text):
        raise ValidationError("The offset must be a whole number of minutes.")
    return check_offset_minutes(int(text))


@dataclass(frozen=True)
class IntakePlateRead:
    """Full read model of a plate.

    `name` set to None means the name is derived from its ingredients
    (§4.6.3): it is not an empty name, it is the absence of an own name.
    `offset_minutes` is the template the portions inherit when inserted, not
    clinical data: the authoritative value is each
    portion_detail.offset_minutes (§4.6.2).
    created_at and updated_at are aware datetimes in UTC (TIMESTAMPTZ).
    """
    id: int
    intake_event_id: int
    name: str | None
    offset_minutes: int | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class IntakePlateCreate:
    """Payload to create a plate inside an event."""
    intake_event_id: int
    name: str | None = None
    offset_minutes: int | None = None


def auto_offset_minutes(meal_time: datetime | None, now: datetime) -> int | None:
    """Offset a new plate is born with: minutes from `meal_time` to `now`.

    Outside the sanity bound it is None, in both directions: nobody knows when
    that plate is eaten, and a clamped value would be an invented one
    (measurement_conventions.md §4.5). Without a `meal_time` it is 0.
    """
    if meal_time is None:
        return 0
    offset = int((now - meal_time).total_seconds() // 60)
    if not INTAKE_PLATE_OFFSET_MIN_MINUTES <= offset <= INTAKE_PLATE_OFFSET_MAX_MINUTES:
        return None
    return offset


def derive_plate_name(ingredient_names: list[str]) -> str:
    """Name shown for a plate without its own name (§4.6.3).

    It takes the first word of the names of the first two ingredients, in
    insertion order, separated by a comma ("Arroz basmati Hacendado" +
    "Pechuga de pollo" -> "Arroz, Pechuga"). With a single ingredient, that
    single word; with no ingredients, INTAKE_PLATE_EMPTY_NAME.

    It is a derived value that is not stored: it changes when ingredients are
    added, deleted or moved, and stops being used as soon as the plate has
    its own name.
    """
    first_words = []
    for name in ingredient_names:
        word = (name or "").strip().split(" ")[0].strip()
        if word:
            first_words.append(word)
        if len(first_words) == INTAKE_PLATE_NAME_INGREDIENTS:
            break

    if not first_words:
        return INTAKE_PLATE_EMPTY_NAME
    return ", ".join(first_words)


@dataclass(frozen=True)
class PlateEaten:
    """How much of a plate was eaten, as typed at confirm (measurement §4.4). `value`
    None = all of it; otherwise a finite number >= 0 in `unit` (% or grams)."""

    plate_id: int
    value: float | None
    unit: AmountInputUnit


def eaten_fraction(eaten: PlateEaten | None, plate_total: float) -> float:
    """Fraction of a plate that was eaten, in (0, 1] (decision 2026-09-22). Grams
    are against the plate's live total; no entry means all of it (§4.4)."""
    if eaten is None or eaten.value is None:
        return 1.0
    if eaten.unit is AmountInputUnit.PERCENT:
        fraction = eaten.value / 100.0
    else:
        if plate_total <= 0:
            raise ValidationError("total_amount_not_positive")
        fraction = eaten.value / plate_total
    if not (0.0 < fraction <= 1.0):
        raise ValidationError("fraction_out_of_range")
    return fraction
