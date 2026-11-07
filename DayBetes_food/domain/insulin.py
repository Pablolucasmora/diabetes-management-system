"""Domain dataclasses for insulin_injections (conventions/code_conventions.md §3.6).

This module imports no psycopg, routes or components. The conversion from a
SQL row to these dataclasses lives in DayBetes_food/database/mappers.py, not here.
"""

import math
from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import InjectionZone, InsulinType
from DayBetes_food.domain.nutrition import NumericRange, parse_number
from DayBetes_food.errors import ValidationError

# Only parsing: positivity, the 0.5 U step and whether it is required are checked
# by validate_insulin_dose, the same for every way an injection is written.
_ANY_NUMBER = NumericRange(-math.inf, math.inf)


@dataclass(frozen=True)
class InsulinInjectionRead:
    """Read model of an insulin injection with all its fields.

    shot_time, created_at, updated_at are aware in UTC (measurement_conventions.md §9.3).
    needle_leak and skin_pinch can be None = not observed (measurement_conventions.md §2).
    """
    id: int
    user_id: int
    intake_event_id: int | None
    shot_time: datetime
    timezone_at_event: str
    insulin_type: InsulinType
    units: float | None
    injection_zone: InjectionZone | None
    notes: str | None
    needle_leak: bool | None
    skin_pinch: bool | None
    created_at: datetime
    updated_at: datetime
    # NULL only in injections logged before pens existed (measurement §8.4).
    insulin_pen_id: int | None = None


@dataclass(frozen=True)
class InsulinInjectionCreate:
    """Payload to create an insulin injection.

    Every optional parameter defaults to None.
    The user_id comes from the authentication context, not from the payload.
    """
    user_id: int
    insulin_type: InsulinType
    shot_time: datetime
    timezone_at_event: str
    injection_zone: InjectionZone | None = None
    units: float | None = None
    intake_event_id: int | None = None
    notes: str | None = None
    needle_leak: bool | None = None
    skin_pinch: bool | None = None
    # Required for every new injection (measurement §8.4); the insulin_type
    # must be the one of the pen's brand, which the caller takes from the pen.
    insulin_pen_id: int | None = None


@dataclass(frozen=True)
class InsulinInjectionUpdate:
    """Payload to update an insulin injection.

    Full replacement of the fields editable in the settings form.
    It is not a partial update: the form always sends the four fields, so the
    absent/None/CLEAR distinction of code_conventions.md §3.4 does not apply.
    """
    insulin_type: InsulinType
    shot_time: datetime
    injection_zone: InjectionZone | None
    units: float | None
    insulin_pen_id: int | None  # None only to keep an old injection without a pen


def validate_insulin_dose(insulin_type: InsulinType, units: float | None) -> None:
    """Validate the consistency between insulin type and dose.

    Raises ValidationError if the combination is not valid (code_conventions.md §4.3).

    Rules:
    - Basal requires a dose (units > 0)
    - Rapid may have no dose (units is optional)
    - If there is a dose, it must be positive and a multiple of 0.5 U
    """
    if insulin_type is InsulinType.BASAL and units is None:
        raise ValidationError("Basal insulin requires a dose", fields={"units": "required"})

    if units is not None:
        if units <= 0:
            raise ValidationError("Insulin dose must be positive", fields={"units": "positive"})
        # Check it is a multiple of 0.5: (units * 2) must be an integer
        if abs((units * 2) - round(units * 2)) > 1e-8:
            raise ValidationError("Insulin dose must be a multiple of 0.5 U", fields={"units": "step"})


def parse_insulin_units(raw) -> float | None:
    """Dose typed in a form, in U (measurement_conventions.md §8.1). '' -> None,
    which means "dose not recorded", never zero; '8,5' -> 8.5; text, NaN or
    Infinity -> ValidationError. Valid for basal and rapid alike."""
    return parse_number(raw, "units", _ANY_NUMBER)
