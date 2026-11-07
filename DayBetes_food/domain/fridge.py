"""Dataclasses and pure rules of `fridge`, a container kept in the fridge or the
freezer (code_conventions.md §11.2.6, measurement_conventions.md §4.8).

This module imports no psycopg, routes or components. The SQL-row-to-dataclass
conversion lives in DayBetes_food/database/mappers.py.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta

from DayBetes_food.domain.constants import (
    MASS_SANITY_MAX_G,
    AmountInputUnit,
    ConservationMethod,
    CookingMethod,
    FoodPhysicalState,
    FridgeCloseReason,
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


# Typed grams are compared with a weight shown with one decimal: a gap this small
# is display rounding, not more than the container holds.
_GRAMS_DISPLAY_TOLERANCE_G = 0.05
_TAKE_PERCENT_RANGE = NumericRange(0, 100, minimum_exclusive=True)

_CONSERVATION_OF = {
    StorageLocation.FRIDGE: ConservationMethod.FRIDGE,
    StorageLocation.FREEZER: ConservationMethod.FREEZER,
}


def parse_take_fraction(raw_value, unit: AmountInputUnit, content_weight: float | None) -> float:
    """Part of a container that is taken out, in (0, 1] (measurement §4.8.3).

    In % by default. In grams only when the container has its real weight: the
    amounts of its portions are not its weight (cooked, raw...)."""
    if unit is AmountInputUnit.PERCENT:
        try:
            percent = parse_number(raw_value, "amount", _TAKE_PERCENT_RANGE)
        except ValidationError as error:
            raise ValidationError("Take between 0 and 100 %.", fields=error.fields) from error
        if percent is None:
            raise ValidationError("Say how much to take.", fields={"amount": "required"})
        return percent / 100.0
    if unit is not AmountInputUnit.GRAMS:
        raise ValidationError("Take it in % or in grams.", fields={"unit": "invalid"})
    if content_weight is None:
        raise ValidationError(
            "Weigh the container first to take it in grams, or use %.", fields={"unit": "requires_content_weight"}
        )
    limit = NumericRange(0, content_weight + _GRAMS_DISPLAY_TOLERANCE_G, minimum_exclusive=True)
    try:
        grams = parse_number(raw_value, "amount", limit)
    except ValidationError as error:
        raise ValidationError(
            f"Take between 0 and {content_weight:.1f} g.", fields=error.fields
        ) from error
    if grams is None:
        raise ValidationError("Say how much to take.", fields={"amount": "required"})
    return min(grams / content_weight, 1.0)


def conservation_when_taken(
    fridge: "FridgeRead", moves: list["FridgeMoveRead"], taken_at: datetime
) -> ConservationMethod:
    """Conservation of what is taken: the place where the container spent more time
    from `stored_at` to `taken_at`; the freezer on a tie (measurement §4.8.4)."""
    time_in = {location: timedelta(0) for location in StorageLocation}
    since = fridge.stored_at
    place = moves[0].from_location if moves else fridge.location
    for move in sorted(moves, key=lambda move: move.moved_at):
        time_in[place] += move.moved_at - since
        since, place = move.moved_at, move.to_location
    time_in[place] += max(taken_at - since, timedelta(0))
    longest = (
        StorageLocation.FREEZER
        if time_in[StorageLocation.FREEZER] >= time_in[StorageLocation.FRIDGE]
        else StorageLocation.FRIDGE
    )
    return _CONSERVATION_OF[longest]


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
    closed_reason: FridgeCloseReason | None   # None while it is still stored
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class FridgeMoveRead:
    from_location: StorageLocation
    to_location: StorageLocation
    moved_at: datetime


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
class FridgeContent:
    """One ingredient that goes into a container (measurement §4.8.1). It has no
    conservation: the container says where it is (§4.8.4)."""

    origin: PortionOrigin
    origin_id: int
    amount: float
    cooking: CookingMethod | None = None
    final_state: FoodPhysicalState | None = None
    strictly_weighed: bool | None = None
    is_cooked_weight: bool = False


@dataclass(frozen=True)
class FridgeStoreCommand:
    """Store a new container: a food, a recipe or the leftovers of a plate (§4.8.5)."""

    user_id: int
    location: StorageLocation
    contents: tuple[FridgeContent, ...]
    name: str | None = None


# How many equal containers the leftovers of one plate can be split into at
# confirm (frontend_conventions.md §7.14): a sanity limit, not a kitchen one.
LEFTOVER_CONTAINERS_RANGE = NumericRange(1, 10)


@dataclass(frozen=True)
class LeftoverPlan:
    """What to do with what was left of a plate at confirm (measurement §4.8.5).
    `location` None = not saved."""

    plate_id: int
    location: StorageLocation | None
    containers: int = 1
    name: str | None = None


def parse_leftover_containers(raw) -> int:
    """Required whole number of containers, from 1 to 10."""
    try:
        containers = parse_number(raw, "containers", LEFTOVER_CONTAINERS_RANGE, integer=True)
    except ValidationError as error:
        raise ValidationError("Split the leftovers into 1 to 10 containers.", fields=error.fields) from error
    if containers is None:
        raise ValidationError("Say into how many containers.", fields={"containers": "required"})
    return int(containers)


def merge_contents(contents) -> tuple[FridgeContent, ...]:
    """Sum the amounts of the same ingredient (origin, preparation and weighing), in
    the order they come: a container has no plates, so a recipe's are joined."""
    merged: dict[tuple, FridgeContent] = {}
    for content in contents:
        key = (content.origin, content.origin_id, content.cooking, content.final_state, content.is_cooked_weight)
        existing = merged.get(key)
        merged[key] = replace(existing, amount=existing.amount + content.amount) if existing else content
    return tuple(merged.values())


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
