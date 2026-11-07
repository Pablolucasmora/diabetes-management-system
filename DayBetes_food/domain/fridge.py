"""Pure rules of `fridge`, a container kept in the fridge or the freezer
(code_conventions.md §11.2.6, measurement_conventions.md §4.8).

This module imports no psycopg, routes or components.
"""

from datetime import datetime, timedelta

from DayBetes_food.domain.constants import MASS_SANITY_MAX_G, StorageLocation
from DayBetes_food.domain.nutrition import NumericRange

# Real weight of the content, in grams (measurement_conventions.md §4.8.3): > 0 and
# the shared sanity ceiling (§6.9.2). NaN and Infinity fail the same CHECK.
FRIDGE_CONTENT_WEIGHT_RANGE = NumericRange(0, MASS_SANITY_MAX_G, minimum_exclusive=True)
# How long a container keeps by default, with a safety margin on purpose
# (measurement_conventions.md §4.8.2). The user can change the date by hand.
FRIDGE_SHELF_LIFE: dict[StorageLocation, timedelta] = {
    StorageLocation.FRIDGE: timedelta(days=10),
    StorageLocation.FREEZER: timedelta(days=90),
}


def default_expires_at(location: StorageLocation, since: datetime) -> datetime:
    """Expiry of a container stored, or moved, to `location` at `since`.

    `since` is the moment it entered that place: `stored_at` for a new
    container, the move time when it changes place (§4.8.2).
    """
    return since + FRIDGE_SHELF_LIFE[location]
