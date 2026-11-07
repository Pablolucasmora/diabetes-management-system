"""Queries for `insulin_pen` (code_conventions.md §11.2.7, measurement §8.4).

A pen is private: every query carries its owner in the SQL (§5.3), so a pen of
another user and one that does not exist give the same `NotFoundError` (§5.4).
What is left in a pen is never stored: every read sums its injections (§6.9).
"""

from psycopg.errors import CheckViolation

from DayBetes_food.database.mappers import insulin_pen_read_from_row
from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many
from DayBetes_food.domain.constants import InsulinType, PenCloseReason
from DayBetes_food.domain.insulin_pen import InsulinPenCreate, InsulinPenRead, InsulinPenUpdate
from DayBetes_food.errors import NotFoundError, ValidationError

# The pen, its brand and the usage of its injections (idx_insulin_injections_insulin_pen_id).
_PEN_SELECT = """
    SELECT p.id, p.users_id, p.insulin_brand_id, b.name AS brand_name, b.insulin_type,
           p.format, p.opened_at, p.expires_at, p.capacity_units, p.closed_at, p.closed_reason,
           p.created_at, p.updated_at,
           u.injection_count, u.dosed_units, u.undosed_count
    FROM insulin_pen p
    JOIN insulin_brand b ON b.id = p.insulin_brand_id
    CROSS JOIN LATERAL (
        SELECT count(i.id) AS injection_count,
               coalesce(sum(i.units), 0) AS dosed_units,
               count(i.id) FILTER (WHERE i.units IS NULL) AS undosed_count
        FROM insulin_injections i
        WHERE i.insulin_pen_id = p.id
    ) u
"""

# The default pen of a meal's bolus (measurement §8.4): the open rapid pen used
# most recently, else the one opened most recently. It is a subquery so that the
# INSERT or UPDATE that writes it resolves it in the same statement. It needs
# the parameters `user_id` and `exclude_pen_id` (None = exclude none).
DEFAULT_RAPID_PEN_SQL = f"""
    (SELECT dp.id
     FROM insulin_pen dp
     JOIN insulin_brand db ON db.id = dp.insulin_brand_id
     LEFT JOIN LATERAL (
         SELECT max(di.shot_time) AS last_used
         FROM insulin_injections di
         WHERE di.insulin_pen_id = dp.id
     ) du ON TRUE
     WHERE dp.users_id = %(user_id)s
       AND dp.closed_at IS NULL
       AND db.insulin_type = '{InsulinType.RAPID.value}'
       AND (%(exclude_pen_id)s::integer IS NULL OR dp.id <> %(exclude_pen_id)s::integer)
     ORDER BY du.last_used DESC NULLS LAST, dp.opened_at DESC, dp.id DESC
     LIMIT 1)
"""


def create_insulin_pen(connection, payload: InsulinPenCreate, commit: bool = True) -> int:
    """Open a pen of an active brand of the same user, checked in the INSERT itself.

    Raises:
        NotFoundError: the brand is not an active one of the user.
        ValidationError: the expiry is not after the opening.
    """
    try:
        row = _execute_query(
            connection,
            """
            INSERT INTO insulin_pen (users_id, insulin_brand_id, format, opened_at, expires_at, capacity_units)
            SELECT %(user_id)s, b.id, %(format)s, %(opened_at)s, %(expires_at)s, %(capacity_units)s
            FROM insulin_brand b
            WHERE b.id = %(brand_id)s AND b.users_id = %(user_id)s AND b.deleted_at IS NULL
            RETURNING id;
            """,
            {
                "user_id": payload.user_id,
                "brand_id": payload.brand_id,
                "format": payload.format.value,
                "opened_at": payload.opened_at,
                "expires_at": payload.expires_at,
                "capacity_units": payload.capacity_units,
            },
            commit=commit,
        )
    except CheckViolation as exc:
        raise ValidationError("The expiry must be after the day it was opened.") from exc
    if row is None:
        raise NotFoundError("Brand not found.")
    return int(row["id"])


def list_open_insulin_pens(
    connection, user_id: int, insulin_type: InsulinType | None = None
) -> list[InsulinPenRead]:
    """Open pens of the user, the soonest to expire first (idx_insulin_pen_users_id_open)."""
    rows = _execute_query_many(
        connection,
        f"""
        {_PEN_SELECT}
        WHERE p.users_id = %(user_id)s AND p.closed_at IS NULL
          AND (%(insulin_type)s::varchar IS NULL OR b.insulin_type = %(insulin_type)s::varchar)
        ORDER BY p.expires_at, p.id;
        """,
        {"user_id": user_id, "insulin_type": insulin_type.value if insulin_type else None},
        commit=False,
    )
    return [insulin_pen_read_from_row(row) for row in rows]


def list_insulin_pens_by_ids(connection, user_id: int, pen_ids: list[int]) -> list[InsulinPenRead]:
    """Pens of the user with these ids, open or closed: the pen of each injection."""
    if not pen_ids:
        return []
    rows = _execute_query_many(
        connection,
        f"{_PEN_SELECT} WHERE p.users_id = %(user_id)s AND p.id = ANY(%(pen_ids)s) ORDER BY p.id;",
        {"user_id": user_id, "pen_ids": list(pen_ids)},
        commit=False,
    )
    return [insulin_pen_read_from_row(row) for row in rows]


def get_insulin_pen(connection, user_id: int, pen_id: int) -> InsulinPenRead | None:
    """A pen of the user, open or closed, or None (§5.4)."""
    row = _execute_query(
        connection,
        f"{_PEN_SELECT} WHERE p.id = %(pen_id)s AND p.users_id = %(user_id)s;",
        {"pen_id": pen_id, "user_id": user_id},
        commit=False,
    )
    return insulin_pen_read_from_row(row) if row else None


def get_open_insulin_pen(connection, user_id: int, pen_id: int) -> InsulinPenRead | None:
    """An open pen of the user, or None: the only kind a new injection can use."""
    pen = get_insulin_pen(connection, user_id, pen_id)
    return pen if pen is not None and pen.closed_at is None else None


def lock_insulin_pen(connection, user_id: int, pen_id: int) -> bool:
    """Lock an open pen of the user until the transaction ends (§6.8). Locked in its
    own statement: the aggregate read cannot take FOR UPDATE. False if it is not
    an open pen of the user."""
    row = _execute_query(
        connection,
        "SELECT p.id FROM insulin_pen p WHERE p.id = %(pen_id)s AND p.users_id = %(user_id)s "
        "AND p.closed_at IS NULL FOR UPDATE;",
        {"pen_id": pen_id, "user_id": user_id},
        commit=False,
    )
    return row is not None


def update_insulin_pen(
    connection, user_id: int, pen_id: int, payload: InsulinPenUpdate, commit: bool = True
) -> None:
    """Replace the editable fields of an open pen.

    Raises:
        NotFoundError: it is not an open pen of the user.
        ValidationError: the expiry is not after the opening.
    """
    try:
        row = _execute_query(
            connection,
            """
            UPDATE insulin_pen p
            SET format = %(format)s,
                expires_at = %(expires_at)s,
                capacity_units = %(capacity_units)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE p.id = %(pen_id)s AND p.users_id = %(user_id)s AND p.closed_at IS NULL
            RETURNING p.id;
            """,
            {
                "pen_id": pen_id,
                "user_id": user_id,
                "format": payload.format.value,
                "expires_at": payload.expires_at,
                "capacity_units": payload.capacity_units,
            },
            commit=commit,
        )
    except CheckViolation as exc:
        raise ValidationError("The expiry must be after the day it was opened.") from exc
    if row is None:
        raise NotFoundError("Pen not found.")


def delete_insulin_pen(connection, user_id: int, pen_id: int, commit: bool = True) -> bool:
    """Physical delete of an open pen no injection uses (§11.2.7). False otherwise: the
    caller then closes it."""
    row = _execute_query(
        connection,
        """
        DELETE FROM insulin_pen p
        WHERE p.id = %(pen_id)s AND p.users_id = %(user_id)s AND p.closed_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM insulin_injections i WHERE i.insulin_pen_id = p.id)
        RETURNING p.id;
        """,
        {"pen_id": pen_id, "user_id": user_id},
        commit=commit,
    )
    return row is not None


def close_insulin_pen(
    connection, user_id: int, pen_id: int, reason: PenCloseReason, commit: bool = True
) -> bool:
    """Close an open pen with its reason (§11.2.7). False if it is not an open pen of the user."""
    row = _execute_query(
        connection,
        """
        UPDATE insulin_pen p
        SET closed_at = greatest(CURRENT_TIMESTAMP, p.opened_at),
            closed_reason = %(reason)s,
            updated_at = CURRENT_TIMESTAMP
        WHERE p.id = %(pen_id)s AND p.users_id = %(user_id)s AND p.closed_at IS NULL
        RETURNING p.id;
        """,
        {"pen_id": pen_id, "user_id": user_id, "reason": reason.value},
        commit=commit,
    )
    return row is not None
