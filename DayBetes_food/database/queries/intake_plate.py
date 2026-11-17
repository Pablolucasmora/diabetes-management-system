"""Queries for the `intake_plate` table (an event's plates or serving batches).

Model and rules: conventions/measurement_conventions.md §4.6
(decision 2026-09-19).
"""

from datetime import datetime

from psycopg.errors import ForeignKeyViolation

from DayBetes_food.database.mappers import intake_plate_read_from_row
from DayBetes_food.database.queries.crud import (
    _execute_query,
    _execute_query_many,
)
from DayBetes_food.domain.intake_plate import IntakePlateCreate, IntakePlateRead
from DayBetes_food.errors import ConflictError, InfrastructureError, NotFoundError, ValidationError

# Read columns of the table. Explicit list, never `SELECT *` (§3.2): adding a
# column must not change the read contract without touching the code that
# consumes it.
_INTAKE_PLATE_COLUMNS = """
    ip.id,
    ip.intake_event_id,
    ip.name,
    ip.offset_minutes,
    ip.eaten_at,
    ip.eaten_fraction,
    ip.created_at,
    ip.updated_at
"""

# Order of the plates inside an event (§4.6.1): chronological by the plate's
# offset and, for equal offsets, by creation order. It is written here once;
# no component reorders on its own.
_INTAKE_PLATE_ORDER = "ORDER BY ip.offset_minutes NULLS LAST, ip.id"


def create_intake_plate(connection, payload: IntakePlateCreate, *, commit: bool = True) -> int:
    """Create a plate inside an event and return its id."""
    query = """
        INSERT INTO intake_plate (intake_event_id, name, offset_minutes, eaten_at)
        VALUES (%(intake_event_id)s, %(name)s, %(offset_minutes)s, %(eaten_at)s)
        RETURNING id;
    """
    row = _execute_query(
        connection,
        query,
        {
            "intake_event_id": payload.intake_event_id,
            "name": payload.name,
            "offset_minutes": payload.offset_minutes,
            "eaten_at": payload.eaten_at,
        },
        commit=commit,
    )
    if row is None:
        raise InfrastructureError("Intake plate INSERT returned no row")
    return int(row["id"])


def list_intake_plates(connection, user_id: int, event_id: int) -> list[IntakePlateRead]:
    """Plates of an event of the user, in the §4.6.1 order. Ownership is
    checked in the SQL itself (code_conventions.md §5.3): another user's
    event returns no plates."""
    query = f"""
        SELECT {_INTAKE_PLATE_COLUMNS}
        FROM intake_plate ip
        JOIN intake_event ie ON ie.id = ip.intake_event_id
        WHERE ip.intake_event_id = %(event_id)s
          AND ie.users_id = %(user_id)s
        {_INTAKE_PLATE_ORDER};
    """
    rows = _execute_query_many(
        connection, query, {"event_id": event_id, "user_id": user_id}, commit=False
    )
    return [intake_plate_read_from_row(row) for row in rows]


def list_intake_plates_by_events(connection, user_id: int, event_ids: list[int]) -> list[IntakePlateRead]:
    """Plates of several events in a single query (§6.9: no N+1 in the cart list).

    The order is by event and, inside each one, the §4.6.1 order. The caller
    distributes the plates by `intake_event_id` without reordering them.
    """
    if not event_ids:
        return []
    query = f"""
        SELECT {_INTAKE_PLATE_COLUMNS}
        FROM intake_plate ip
        JOIN intake_event ie ON ie.id = ip.intake_event_id
        WHERE ip.intake_event_id = ANY(%(event_ids)s)
          AND ie.users_id = %(user_id)s
        ORDER BY ip.intake_event_id, ip.offset_minutes NULLS LAST, ip.id;
    """
    rows = _execute_query_many(
        connection, query, {"event_ids": list(event_ids), "user_id": user_id}, commit=False
    )
    return [intake_plate_read_from_row(row) for row in rows]


def get_intake_plate(connection, user_id: int, plate_id: int) -> IntakePlateRead:
    """Read a plate, checking ownership inside the SQL (§5.3).

    The plate -> event -> user ownership is resolved in the query: a route
    can never trust the `event_id` that comes in the URL. It does not require
    the 'planned' state: the plates of an already consumed event are edited
    too (measurement_conventions.md §6.9.3).

    Raises:
        NotFoundError: it does not exist, is not the user's or its event is archived.
    """
    query = f"""
        SELECT {_INTAKE_PLATE_COLUMNS}
        FROM intake_plate ip
        JOIN intake_event ie ON ie.id = ip.intake_event_id
        WHERE ip.id = %(plate_id)s
          AND ie.users_id = %(user_id)s
          AND ie.deleted_at IS NULL;
    """
    row = _execute_query(connection, query, {"plate_id": plate_id, "user_id": user_id}, commit=False)
    if row is None:
        raise NotFoundError(
            f"Intake plate {plate_id} not found or not owned by user {user_id}"
        )
    return intake_plate_read_from_row(row)


def update_intake_plate_name(
    connection, plate_id: int, name: str | None, *, commit: bool = True
) -> None:
    """Write the plate's own name, or clear it with `name=None`.

    A dedicated function, like `update_intake_event_name` and for the same
    reason: a generic update reads None as "leave untouched", so clearing the
    name —and going back to the §4.6.3 derived one— cannot be done that way.

    Raises:
        NotFoundError: the plate does not exist.
    """
    query = """
        UPDATE intake_plate
        SET name = %(name)s,
            updated_at = NOW()
        WHERE id = %(plate_id)s
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, {"plate_id": plate_id, "name": name})
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(f"Intake plate {plate_id} not found")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def update_intake_plate_offset(
    connection,
    plate_id: int,
    offset_minutes: int | None,
    *,
    eaten_at: datetime | None = None,
    commit: bool = True,
) -> None:
    """Write the plate's template offset, or clear it with `offset_minutes=None`.

    `eaten_at` is the exact time it was written as, with `offset_minutes` already
    derived from it; None means the offset was written in minutes, and clears the
    time (measurement_conventions.md §4.5.1). A dedicated function for the same
    reason as `update_intake_plate_name`.

    Raises:
        NotFoundError: the plate does not exist.
    """
    query = """
        UPDATE intake_plate
        SET offset_minutes = %(offset_minutes)s,
            eaten_at = %(eaten_at)s,
            updated_at = NOW()
        WHERE id = %(plate_id)s
        RETURNING id;
    """
    row = _execute_query(
        connection,
        query,
        {"plate_id": plate_id, "offset_minutes": offset_minutes, "eaten_at": eaten_at},
        commit=commit,
    )
    if row is None:
        raise NotFoundError(f"Intake plate {plate_id} not found")


def list_event_exact_times(connection, event_id: int) -> list[tuple[str, int, datetime]]:
    """`(table, id, eaten_at)` of the plates and portions of an event whose offset
    was written as an exact time (measurement_conventions.md §4.5.1)."""
    query = """
        SELECT 'intake_plate' AS table_name, id, eaten_at
        FROM intake_plate
        WHERE intake_event_id = %(event_id)s AND eaten_at IS NOT NULL
        UNION ALL
        SELECT 'portion_detail' AS table_name, id, eaten_at
        FROM portion_detail
        WHERE intake_event_id = %(event_id)s AND eaten_at IS NOT NULL;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"event_id": event_id})
        return [(row["table_name"], int(row["id"]), row["eaten_at"]) for row in cursor.fetchall()]


# The two tables that hold an exact time; the name goes into the SQL, so it is
# never taken from outside this list.
_EXACT_TIME_TABLES = {"intake_plate", "portion_detail"}


def set_exact_time(
    connection, table: str, row_id: int, eaten_at: datetime, offset_minutes: int | None
) -> None:
    """Write an exact time and its derived offset on one plate or portion, inside
    the caller's transaction (§4.5.1)."""
    if table not in _EXACT_TIME_TABLES:
        raise ValueError(f"No exact time in {table}")
    _execute_query(
        connection,
        f"""
        UPDATE {table}
        SET eaten_at = %(eaten_at)s, offset_minutes = %(offset_minutes)s, updated_at = NOW()
        WHERE id = %(id)s
        RETURNING id;
        """,
        {"eaten_at": eaten_at, "offset_minutes": offset_minutes, "id": row_id},
        commit=False,
    )


def apply_plate_offset_to_portions(
    connection,
    plate_id: int,
    offset_minutes: int | None,
    *,
    eaten_at: datetime | None = None,
    commit: bool = True,
) -> bool:
    """`Apply all`: set the plate's offset and propagate it to all its portions,
    with its exact time when it was written as one (§4.5.1).

    Both writes are a single operation (§2.3): if the propagation fails, the
    plate does not keep the new value either. It is the only way the plate's
    offset touches existing rows; changing it on its own only affects the
    portions added afterwards (§4.6.2).
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE intake_plate
                SET offset_minutes = %(offset_minutes)s,
                    eaten_at = %(eaten_at)s,
                    updated_at = NOW()
                WHERE id = %(plate_id)s;
                """,
                {"offset_minutes": offset_minutes, "eaten_at": eaten_at, "plate_id": plate_id},
            )
            if cursor.rowcount != 1:
                if commit:
                    connection.rollback()
                return False
            cursor.execute(
                """
                UPDATE portion_detail
                SET offset_minutes = %(offset_minutes)s,
                    eaten_at = %(eaten_at)s,
                    updated_at = NOW()
                WHERE plate_id = %(plate_id)s;
                """,
                {"offset_minutes": offset_minutes, "eaten_at": eaten_at, "plate_id": plate_id},
            )
        if commit:
            connection.commit()
        return True
    except Exception:
        if commit:
            connection.rollback()
        raise


def set_intake_plate_eaten_fraction(
    connection, user_id: int, plate_id: int, fraction: float, *, commit: bool = True
) -> None:
    """Store what was eaten of a plate, in (0, 1], when its meal is confirmed
    (study_conventions.md §6.3). Ownership is checked in the SQL (§5.3).

    Raises:
        ValidationError: fraction out of (0, 1].
        NotFoundError: the plate does not exist or is not the user's.
    """
    if not (0.0 < fraction <= 1.0):
        raise ValidationError("invalid_fraction")
    row = _execute_query(
        connection,
        """
        UPDATE intake_plate ip
        SET eaten_fraction = %(fraction)s,
            updated_at = NOW()
        FROM intake_event ie
        WHERE ip.id = %(plate_id)s
          AND ie.id = ip.intake_event_id
          AND ie.users_id = %(user_id)s
        RETURNING ip.id;
        """,
        {"fraction": fraction, "plate_id": plate_id, "user_id": user_id},
        commit=commit,
    )
    if row is None:
        raise NotFoundError("intake_plate_not_found")


def delete_intake_plate(connection, plate_id: int, *, commit: bool = True) -> None:
    """Delete an empty plate.

    A plate with portions is not deleted: the FK is `ON DELETE RESTRICT` on
    purpose (§4.6.5), so that a click does not wipe out half a meal. The
    integrity violation is translated to ConflictError, not to a 500.

    Raises:
        NotFoundError: the plate does not exist.
        ConflictError: the plate still has ingredients.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM intake_plate WHERE id = %(id)s;", {"id": plate_id})
            deleted = cursor.rowcount
        if deleted != 1:
            if commit:
                connection.rollback()
            raise NotFoundError(f"Intake plate {plate_id} not found")
        if commit:
            connection.commit()
    except ForeignKeyViolation as exc:
        if commit:
            connection.rollback()
        raise ConflictError("Intake plate still has portions") from exc
    except NotFoundError:
        raise
    except Exception:
        if commit:
            connection.rollback()
        raise


def ensure_default_plate(connection, event_id: int, *, offset_minutes: int = None, commit: bool = True) -> int:
    """Return the plate a food added without choosing a plate must go to.

    It is the plate of the **last portion added** to the event —the one the
    user is putting together right now— and, if none has ingredients yet, the
    most recently created one. If the event has no plate at all, it creates
    one implicitly with the given offset (§4.6.1, §7.7).

    The plate selector preselects this same plate: what the interface shows
    and what happens when no `plate_id` is sent must match
    (frontend_conventions.md §6).
    """
    row = _execute_query(
        connection,
        """
        SELECT ip.id
        FROM intake_plate ip
        LEFT JOIN (
            SELECT plate_id, MAX(id) AS last_portion_id
            FROM portion_detail
            WHERE plate_id IS NOT NULL
            GROUP BY plate_id
        ) last_portion ON last_portion.plate_id = ip.id
        WHERE ip.intake_event_id = %(event_id)s
        ORDER BY last_portion.last_portion_id DESC NULLS LAST, ip.id DESC
        LIMIT 1;
        """,
        {"event_id": event_id},
        commit=False,
    )
    if row is not None:
        return int(row["id"])
    return create_intake_plate(
        connection,
        IntakePlateCreate(intake_event_id=event_id, offset_minutes=offset_minutes),
        commit=commit,
    )
