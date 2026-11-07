"""Use cases of insulin pens and brands (code_conventions.md §11.2.7,
measurement_conventions.md §8.4). Each runs inside the caller's transaction.
"""

from datetime import datetime

from DayBetes_food.database.queries import (
    archive_insulin_brand,
    close_insulin_pen,
    create_insulin_brand,
    create_insulin_pen,
    delete_insulin_brand,
    delete_insulin_pen,
    get_insulin_brand,
    get_insulin_pen,
    lock_insulin_brand,
    lock_insulin_pen,
    reassign_planned_events_pen,
)
from DayBetes_food.domain.constants import PenFormat
from DayBetes_food.domain.insulin_pen import InsulinBrandCreate, InsulinPenCreate, pen_expires_at
from DayBetes_food.errors import NotFoundError
from DayBetes_food.time_utils import utc_now


def open_insulin_pen(
    connection,
    user_id: int,
    brand: int | InsulinBrandCreate,
    pen_format: PenFormat,
    opened_at: datetime,
) -> int:
    """Open a pen of an existing brand (its id) or of a new one, created in the same
    transaction. Expiry and capacity are copied from the brand (§8.4).

    Raises:
        NotFoundError: the brand is not an active one of the user.
        ConflictError: the new brand's name is taken.
        ValidationError: a value leaves its limits.
    """
    brand_id = brand if isinstance(brand, int) else create_insulin_brand(connection, brand, commit=False)
    # Locked so that deleting the brand and opening a pen of it cannot cross (§6.8).
    if not lock_insulin_brand(connection, user_id, brand_id):
        raise NotFoundError("Brand not found.")
    brand_row = get_insulin_brand(connection, user_id, brand_id)
    return create_insulin_pen(
        connection,
        InsulinPenCreate(
            user_id=user_id,
            brand_id=brand_id,
            format=pen_format,
            opened_at=opened_at,
            expires_at=pen_expires_at(opened_at, brand_row.in_use_days),
            capacity_units=brand_row.pen_units,
        ),
        commit=False,
    )


def discard_insulin_pen(connection, user_id: int, pen_id: int) -> None:
    """Stop using a pen (§11.2.7): deleted if no injection uses it, closed with its
    reason otherwise. Planned meals that had it go to the default pen first.

    Raises:
        NotFoundError: it is not an open pen of the user.
    """
    # Locked first, in its own statement (§6.8): an injection that commits while
    # this waits is then seen, and the pen is closed instead of deleted.
    if not lock_insulin_pen(connection, user_id, pen_id):
        raise NotFoundError("Pen not found.")
    pen = get_insulin_pen(connection, user_id, pen_id)
    reassign_planned_events_pen(connection, user_id, pen_id, commit=False)
    if not delete_insulin_pen(connection, user_id, pen_id, commit=False):
        close_insulin_pen(connection, user_id, pen_id, pen.close_reason(utc_now()), commit=False)


def remove_insulin_brand(connection, user_id: int, brand_id: int) -> bool:
    """Delete a brand no pen uses, or archive it if one does (§11.2.7). Returns True
    when it was archived.

    Raises:
        NotFoundError: it is not an active brand of the user.
    """
    if not lock_insulin_brand(connection, user_id, brand_id):
        raise NotFoundError("Brand not found.")
    if delete_insulin_brand(connection, user_id, brand_id, commit=False):
        return False
    archive_insulin_brand(connection, user_id, brand_id, commit=False)
    return True
