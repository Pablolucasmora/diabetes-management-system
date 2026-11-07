"""Dataclasses and pure rules of `insulin_brand` and `insulin_pen`
(code_conventions.md §11.2.7, measurement_conventions.md §8.4).

This module imports no psycopg, routes or components. The SQL-row-to-dataclass
conversion lives in DayBetes_food/database/mappers.py.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from DayBetes_food.domain.constants import InsulinType, PenCloseReason, PenFormat
from DayBetes_food.domain.nutrition import NumericRange, parse_number
from DayBetes_food.errors import ValidationError

INSULIN_BRAND_NAME_MAX_LENGTH = 100  # = VARCHAR(100)

# Days a pen keeps once opened, and units in a full pen (measurement §8.4). The
# defaults are those of the usual U-100 pens; each brand can change them.
DEFAULT_IN_USE_DAYS = 30
IN_USE_DAYS_RANGE = NumericRange(1, 365)
DEFAULT_PEN_UNITS = 300.0
PEN_UNITS_RANGE = NumericRange(0, 3000, minimum_exclusive=True)

# Units purged before every injection: the user always primes the pen. They only
# count for what is left in the pen, never in insulin_injections.units (§8.4).
PEN_PRIMING_UNITS = 1.0

# A pen is about to run out with this many days or units left, or fewer (§8.4).
PEN_WARNING_DAYS = 3
PEN_WARNING_UNITS = 30.0


def _normalize_text(raw) -> str:
    """strip + collapse any whitespace run into one space (§7.3)."""
    return " ".join(str(raw or "").split())


def parse_insulin_brand_name(raw) -> str:
    name = _normalize_text(raw)
    if not name:
        raise ValidationError("Give the brand a name.", fields={"name": "required"})
    if len(name) > INSULIN_BRAND_NAME_MAX_LENGTH:
        raise ValidationError(
            f"The name must be {INSULIN_BRAND_NAME_MAX_LENGTH} characters or fewer.", fields={"name": "too_long"}
        )
    return name


def parse_in_use_days(raw) -> int:
    try:
        days = parse_number(raw, "in_use_days", IN_USE_DAYS_RANGE, integer=True)
    except ValidationError as error:
        raise ValidationError("The days in use must be a whole number from 1 to 365.", fields=error.fields) from error
    if days is None:
        raise ValidationError("Say how many days a pen lasts once opened.", fields={"in_use_days": "required"})
    return int(days)


def parse_pen_units(raw, field: str = "pen_units") -> float:
    try:
        units = parse_number(raw, field, PEN_UNITS_RANGE)
    except ValidationError as error:
        raise ValidationError("The units must be greater than 0 and at most 3000.", fields=error.fields) from error
    if units is None:
        raise ValidationError("Say how many units a full pen holds.", fields={field: "required"})
    return units


def parse_pen_date(raw, field: str) -> date:
    """Required date of a pen form, `YYYY-MM-DD` (code_conventions.md §7.8)."""
    text = str(raw or "").strip()
    if not text:
        raise ValidationError("Choose a date.", fields={field: "required"})
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError("Choose a valid date.", fields={field: "invalid"}) from exc


def opened_at_from_local_date(day: date, local_now: datetime) -> datetime:
    """When a pen was opened, local and naive: now if it is today, the start of
    the day for an earlier date. A future date is rejected. The caller converts it
    to UTC with the common helper (§10.4)."""
    today = local_now.date()
    if day > today:
        raise ValidationError("A pen cannot be opened in the future.", fields={"opened_date": "future"})
    if day == today:
        return local_now.replace(tzinfo=None, microsecond=0)
    return datetime.combine(day, time(0, 0))


def expires_from_local_date(day: date) -> datetime:
    """Local naive end of `day`: a pen is still good on the date it shows."""
    return datetime.combine(day, time(23, 59, 59))


def pen_expires_at(opened_at: datetime, in_use_days: int) -> datetime:
    return opened_at + timedelta(days=in_use_days)


@dataclass(frozen=True)
class InsulinBrandRead:
    id: int
    user_id: int
    name: str
    insulin_type: InsulinType
    in_use_days: int
    pen_units: float
    pen_count: int  # pens of the brand, open or closed: it cannot change type with any
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class InsulinBrandCreate:
    user_id: int
    name: str
    insulin_type: InsulinType
    in_use_days: int
    pen_units: float


@dataclass(frozen=True)
class InsulinBrandUpdate:
    """Full replacement of the editable fields: the form always sends the four."""
    name: str
    insulin_type: InsulinType
    in_use_days: int
    pen_units: float


@dataclass(frozen=True)
class InsulinPenRead:
    id: int
    user_id: int
    brand_id: int
    brand_name: str
    insulin_type: InsulinType  # the brand's
    format: PenFormat
    opened_at: datetime
    expires_at: datetime
    capacity_units: float
    closed_at: datetime | None
    closed_reason: PenCloseReason | None
    injection_count: int
    dosed_units: float  # sum of the recorded doses, without the priming
    undosed_count: int  # injections without a recorded dose (§8.1)
    created_at: datetime
    updated_at: datetime

    @property
    def remaining_units(self) -> float:
        """capacity − (doses + 1 U of priming per injection), never below 0 (§8.4)."""
        used = self.dosed_units + PEN_PRIMING_UNITS * self.injection_count
        return max(self.capacity_units - used, 0.0)

    @property
    def remaining_is_estimate(self) -> bool:
        return self.undosed_count > 0

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def days_left(self, now: datetime) -> int:
        return max(math.ceil((self.expires_at - now).total_seconds() / 86400), 0)

    def few_days_left(self, now: datetime) -> bool:
        return not self.is_expired(now) and self.expires_at - now <= timedelta(days=PEN_WARNING_DAYS)

    @property
    def few_units_left(self) -> bool:
        return self.remaining_units <= PEN_WARNING_UNITS

    def close_reason(self, now: datetime) -> PenCloseReason:
        """Worked out when the pen is closed (§8.4)."""
        if self.is_expired(now):
            return PenCloseReason.EXPIRED
        if self.remaining_units <= 0:
            return PenCloseReason.EMPTY
        return PenCloseReason.DISCARDED


@dataclass(frozen=True)
class InsulinPenCreate:
    user_id: int
    brand_id: int
    format: PenFormat
    opened_at: datetime
    expires_at: datetime
    capacity_units: float


@dataclass(frozen=True)
class InsulinPenUpdate:
    """Full replacement of the editable fields of an open pen."""
    format: PenFormat
    expires_at: datetime
    capacity_units: float
