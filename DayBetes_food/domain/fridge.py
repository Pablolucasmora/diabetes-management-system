"""Dataclasses and pure rules of `fridge`, a container kept in the fridge or the
freezer (code_conventions.md §11.2.6, measurement_conventions.md §4.8).

This module imports no psycopg, routes or components. The SQL-row-to-dataclass
conversion lives in DayBetes_food/database/mappers.py.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from DayBetes_food.domain.constants import (
    MASS_SANITY_MAX_G,
    CookingMethod,
    FoodPhysicalState,
    PortionOrigin,
    StorageLocation,
)
from DayBetes_food.domain.food import normalize_food_text
from DayBetes_food.domain.intake_plate import derive_plate_name
from DayBetes_food.domain.nutrition import NumericRange, parse_number
from DayBetes_food.domain.portion_detail import PortionDetailRead
from DayBetes_food.errors import ValidationError

FRIDGE_NAME_MAX_LENGTH = 255  # = VARCHAR(255)

# Real weight of the content, in grams (measurement_conventions.md §4.8.3): > 0 and
# the shared sanity ceiling (§6.9.2). NaN and Infinity fail the same CHECK.
FRIDGE_CONTENT_WEIGHT_RANGE = NumericRange(0, MASS_SANITY_MAX_G, minimum_exclusive=True)

# How long a container keeps by default, with a safety margin on purpose
# (measurement_conventions.md §4.8.2). The user can change the date by hand.
FRIDGE_SHELF_LIFE: dict[StorageLocation, timedelta] = {
    StorageLocation.FRIDGE: timedelta(days=10),
    StorageLocation.FREEZER: timedelta(days=90),
}

# A date typed by the user keeps the container until the end of that local day.
_END_OF_DAY = time(23, 59, 59)


def default_expires_at(location: StorageLocation, since: datetime) -> datetime:
    """Expiry of a container stored, or moved, to `location` at `since`.

    `since` is the moment it entered that place: `stored_at` for a new
    container, the move time when it changes place (§4.8.2).
    """
    return since + FRIDGE_SHELF_LIFE[location]


def other_location(location: StorageLocation) -> StorageLocation:
    """Where the move button of a container sends it (frontend_conventions.md §9.8)."""
    return StorageLocation.FREEZER if location is StorageLocation.FRIDGE else StorageLocation.FRIDGE


def parse_fridge_name(raw) -> str | None:
    """Optional name, normalized like a food name; '' -> None (derived name, §4.8.1)."""
    name = normalize_food_text(raw)
    if not name:
        return None
    if len(name) > FRIDGE_NAME_MAX_LENGTH:
        raise ValidationError(
            f"The name must be {FRIDGE_NAME_MAX_LENGTH} characters or fewer.", fields={"name": "too_long"}
        )
    return name


def parse_content_weight(raw) -> float | None:
    """Optional real weight of the content in grams; '' -> None (§4.8.3)."""
    try:
        return parse_number(raw, "content_weight", FRIDGE_CONTENT_WEIGHT_RANGE)
    except ValidationError as error:
        raise ValidationError(
            f"The weight must be greater than 0 g and at most {MASS_SANITY_MAX_G:g} g.", fields=error.fields
        ) from error


def parse_expiry_date(raw) -> date:
    """Required date of an expiry form field, `YYYY-MM-DD` (code_conventions.md §7.8)."""
    text = str(raw or "").strip()
    if not text:
        raise ValidationError("Choose an expiry date.", fields={"expires_at": "required"})
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError("Choose a valid expiry date.", fields={"expires_at": "invalid"}) from exc


def expiry_from_local_date(day: date) -> datetime:
    """Local naive end of `day`: a container is still good on the date it shows.
    The caller converts it to UTC with the common helper (§10.4)."""
    return datetime.combine(day, _END_OF_DAY)


@dataclass(frozen=True)
class FridgeRead:
    id: int
    user_id: int
    name: str | None   # None = derived from its ingredients (§4.8.1)
    location: StorageLocation
    stored_at: datetime
    expires_at: datetime
    content_weight: float | None   # None = not weighed
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class FridgeCreate:
    user_id: int
    location: StorageLocation
    stored_at: datetime
    expires_at: datetime
    name: str | None = None
    content_weight: float | None = None


@dataclass(frozen=True)
class FridgeUpdate:
    """Full replacement of the editable fields: None is written as NULL (§3.4)."""

    name: str | None
    expires_at: datetime
    content_weight: float | None


@dataclass(frozen=True)
class FridgeStoreCommand:
    """Store an amount of a food or a dish as a new container (measurement §4.8.5)."""

    user_id: int
    location: StorageLocation
    origin: PortionOrigin
    origin_id: int
    amount: float
    cooking: CookingMethod | None = None
    final_state: FoodPhysicalState | None = None
    strictly_weighed: bool | None = None
    is_cooked_weight: bool = False


@dataclass(frozen=True)
class FridgeItem:
    """A container with its content, as the fridge page shows it (frontend §9.8)."""

    fridge: FridgeRead
    portions: tuple[PortionDetailRead, ...]

    @property
    def display_name(self) -> str:
        """Its own name or, without one, the one derived from the ingredients (4.6.3)."""
        return self.fridge.name or derive_plate_name([portion.source.name for portion in self.portions])

    def is_expired(self, now: datetime) -> bool:
        return self.fridge.expires_at <= now
