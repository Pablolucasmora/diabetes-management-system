"""Domain of the automatic `meal_type` assignment schedule (conventions/code_conventions.md §3.6).

This module imports no psycopg, routes or components. It is pure: it
receives the time slots already read from the database (or none) and decides
which `MealType` matches a given local time.

Context (decision 2026-09-11): an `intake_event` created automatically
(adding a food with no open cart) was born with `meal_type=None`, but the
cart `<select>` (`components/cart/cart_components.py::EventHeader`) shows
the enum's first option as selected as soon as no `<option>` carries
`selected` — the user sees "breakfast" even though the database has `NULL`,
and since saving is autosave-on-change, if they never touch the control it
is never persisted. The real fix is not only visual: the event must be born
with the `meal_type` the interface is going to show, computed from the time
slot, so that "what is shown" and "what is in the database" are always the
same value from the moment of creation (general principle, see
code_conventions.md §7.14).
"""

from dataclasses import dataclass
from datetime import time

from DayBetes_food.domain.constants import MealType

# Meal types that can be assigned automatically by time slot. `snack` and
# `rescue` are left out on purpose: they are manual choices of the user
# (`rescue`, besides, is always created that way in food_routes.py, see
# audit/deuda_pendiente.md), never a default by hour (decision 2026-09-11).
AUTO_ASSIGNABLE_MEAL_TYPES: tuple[MealType, ...] = (
    MealType.BREAKFAST,
    MealType.BRUNCH,
    MealType.LUNCH,
    MealType.AFTERNOON_SNACK,
    MealType.DINNER,
)

# Default slots (local time), used for any meal_type the user has not
# customized yet in /settings/meal_type_schedule.
# `DINNER` wraps midnight: it ends at 00:00 exclusive and does not keep
# covering the early morning (decision 2026-09-11, agreed with the user).
DEFAULT_MEAL_TYPE_WINDOWS: dict[MealType, tuple[time, time]] = {
    MealType.BREAKFAST: (time(5, 0), time(11, 0)),
    MealType.BRUNCH: (time(11, 0), time(13, 30)),
    MealType.LUNCH: (time(13, 30), time(17, 0)),
    MealType.AFTERNOON_SNACK: (time(17, 0), time(19, 30)),
    MealType.DINNER: (time(19, 30), time(0, 0)),
}


@dataclass(frozen=True)
class MealTypeWindow:
    """A time slot customized by the user for a meal_type."""
    meal_type: MealType
    start_time: time
    end_time: time


def resolve_meal_type_window(
    meal_type: MealType, overrides: dict[MealType, tuple[time, time]]
) -> tuple[time, time]:
    """Effective slot of a meal_type: the user's if it exists, otherwise the default."""
    return overrides.get(meal_type) or DEFAULT_MEAL_TYPE_WINDOWS[meal_type]


def resolve_meal_type_for_time(
    local_time: time,
    overrides: dict[MealType, tuple[time, time]] | None = None,
) -> MealType | None:
    """
    Determine the automatic `meal_type` for a local time, merging the user's
    customized slots with the defaults for the ones they have not touched. If
    no slot covers the time (the gap between the end of `dinner` and the start
    of `breakfast`, e.g. 02:00, or a gap the user left when customizing their
    slots), it returns `None`: no `meal_type` is invented outside the declared
    slots, the user picks it by hand (decision 2026-09-11, same criterion as
    `snack`/`rescue`).
    """
    overrides = overrides or {}
    for meal_type in AUTO_ASSIGNABLE_MEAL_TYPES:
        start, end = resolve_meal_type_window(meal_type, overrides)
        if _time_in_window(local_time, start, end):
            return meal_type
    return None


def _time_in_window(value: time, start: time, end: time) -> bool:
    if start == end:
        # Degenerate slot (it should never be persisted, see the validation in
        # the settings route): it covers no hour instead of covering all of them.
        return False
    if start < end:
        return start <= value < end
    # Wraps midnight (e.g. dinner 19:30-00:00): it covers from start to the
    # end of the day and from the start of the day until end, exclusive.
    return value >= start or value < end
