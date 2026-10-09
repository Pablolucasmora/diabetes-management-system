"""Queries for the `intake_plate` table (an event's plates or serving batches).

Model and rules: conventions/measurement_conventions.md §4.6
(decision 2026-09-19).
"""

from dataclasses import fields as dataclass_fields

from psycopg.errors import ForeignKeyViolation

from DayBetes_food.database.mappers import intake_plate_read_from_row
from DayBetes_food.database.queries.crud import (
    RawSQL,
    _build_update_query,
    _execute_query,
    _execute_query_many,
)
from DayBetes_food.domain.intake_plate import IntakePlateCreate, IntakePlateRead, IntakePlateUpdate
from DayBetes_food.errors import ConflictError, InfrastructureError, NotFoundError

# Read columns of the table. Explicit list, never `SELECT *` (§3.2): adding a
# column must not change the read contract without touching the code that
# consumes it.
_INTAKE_PLATE_COLUMNS = """
    ip.id,
    ip.intake_event_id,
    ip.name,
    ip.offset_minutes,
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
        INSERT INTO intake_plate (intake_event_id, name, offset_minutes)
        VALUES (%(intake_event_id)s, %(name)s, %(offset_minutes)s)
        RETURNING id;
    """
    row = _execute_query(
        connection,
        query,
        {
            "intake_event_id": payload.intake_event_id,
            "name": payload.name,
            "offset_minutes": payload.offset_minutes,
        },
        commit=commit,
    )
    if row is None:
        raise InfrastructureError("Intake plate INSERT returned no row")
    return int(row["id"])


def list_intake_plates(connection, event_id: int) -> list[IntakePlateRead]:
    """Plates of an event, in the §4.6.1 order."""
    query = f"""
        SELECT {_INTAKE_PLATE_COLUMNS}
        FROM intake_plate ip
        WHERE ip.intake_event_id = %(event_id)s
        {_INTAKE_PLATE_ORDER};
    """
    rows = _execute_query_many(connection, query, {"event_id": event_id}, commit=False)
    return [intake_plate_read_from_row(row) for row in rows]


def list_intake_plates_by_events(connection, event_ids: list[int]) -> list[IntakePlateRead]:
    """Plates of several events in a single query (§6.9: no N+1 in the cart list).

    The order is by event and, inside each one, the §4.6.1 order. The caller
    distributes the plates by `intake_event_id` without reordering them.
    """
    if not event_ids:
        return []
    query = f"""
        SELECT {_INTAKE_PLATE_COLUMNS}
        FROM intake_plate ip
        WHERE ip.intake_event_id = ANY(%(event_ids)s)
        ORDER BY ip.intake_event_id, ip.offset_minutes NULLS LAST, ip.id;
    """
    rows = _execute_query_many(connection, query, {"event_ids": list(event_ids)}, commit=False)
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


def update_intake_plate(
    connection,
    plate_id: int,
    data: IntakePlateUpdate,
    *,
    commit: bool = True,
) -> None:
    """Update fields of a plate (§3.1).

    Fields set to None are ignored (behaviour of `_build_update_query`); to
    set `name` to NULL —returning the plate to its derived name— there is
    `update_intake_plate_name`, as in intake_event.

    Ownership is not checked here: the route has already resolved the plate
    with `get_intake_plate`, which JOINs the event and the user (§5.3).

    Raises:
        NotFoundError: the plate does not exist.
    """
    payload = {
        field.name: getattr(data, field.name)
        for field in dataclass_fields(data)
        if getattr(data, field.name) is not None
    }
    if not payload:
        return None

    params = {**payload, "id": plate_id}
    query = _build_update_query("intake_plate", params, raw_fields={"updated_at": RawSQL.NOW})
    if query is None:
        return None

    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(f"Intake plate {plate_id} not found")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def update_intake_plate_name(
    connection, plate_id: int, name: str | None, *, commit: bool = True
) -> None:
    """Write the plate's own name, or clear it with `name=None`.

    A dedicated function, like `update_intake_event_name` and for the same
    reason: `IntakePlateUpdate` reads None as "leave untouched", so clearing
    the name —and going back to the §4.6.3 derived one— cannot be done that way.

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


def apply_plate_offset_to_portions(
    connection,
    plate_id: int,
    offset_minutes: int,
    *,
    commit: bool = True,
) -> bool:
    """`Apply all`: set the plate's offset and propagate it to all its portions.

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
                    updated_at = NOW()
                WHERE id = %(plate_id)s;
                """,
                {"offset_minutes": offset_minutes, "plate_id": plate_id},
            )
            if cursor.rowcount != 1:
                if commit:
                    connection.rollback()
                return False
            cursor.execute(
                """
                UPDATE portion_detail
                SET offset_minutes = %(offset_minutes)s,
                    updated_at = NOW()
                WHERE plate_id = %(plate_id)s;
                """,
                {"offset_minutes": offset_minutes, "plate_id": plate_id},
            )
        if commit:
            connection.commit()
        return True
    except Exception:
        if commit:
            connection.rollback()
        raise


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
