"""CRUD for insulin_injections (code_conventions.md §3.3, §3.4, §3.5).

Public functions:
- create_insulin_injection: inserts and returns the id
- list_insulin_injections: paginated list
- get_insulin_injection: fetches one injection
- get_injection_shot_time_at_offset: helper for backwards pagination
- update_insulin_injection: update by user_id + injection_id
- delete_insulin_injection: delete by user_id + injection_id

Contracts (code_conventions.md §3.4):
- create_*: returns the id; an infrastructure failure raises an exception
- update_*/delete_*: raise NotFoundError if it does not exist or is not the user's
- They never return False; None means "not found"
"""

from datetime import datetime

from DayBetes_food.database.mappers import insulin_injection_read_from_row
from DayBetes_food.domain.insulin import (
    InsulinInjectionCreate,
    InsulinInjectionRead,
    InsulinInjectionUpdate,
    validate_insulin_dose,
)
from DayBetes_food.errors import InfrastructureError, NotFoundError


def create_insulin_injection(
    connection,
    payload: InsulinInjectionCreate,
    *,
    commit: bool = True,
) -> int:
    """Create an insulin injection.

    Args:
        connection: DB connection
        payload: InsulinInjectionCreate with every field
        commit: if True, commits the transaction

    Returns:
        id of the created row

    Raises:
        ValidationError: if insulin_type/units are not consistent
        InfrastructureError: if the insert fails
    """
    # Validate before reaching the DB
    validate_insulin_dose(payload.insulin_type, payload.units)

    query = """
        INSERT INTO insulin_injections (
            users_id, intake_event_id, shot_time, insulin_type, units, injection_zone,
            notes, needle_leak, skin_pinch, timezone_at_event
        )
        VALUES (
            %(user_id)s, %(intake_event_id)s, %(shot_time)s, %(insulin_type)s, %(units)s, %(injection_zone)s,
            %(notes)s, %(needle_leak)s, %(skin_pinch)s, %(timezone_at_event)s
        )
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "user_id": payload.user_id,
                    "intake_event_id": payload.intake_event_id,
                    "shot_time": payload.shot_time,
                    "insulin_type": payload.insulin_type.value,
                    "units": payload.units,
                    "injection_zone": payload.injection_zone.value if payload.injection_zone else None,
                    "notes": payload.notes,
                    "needle_leak": payload.needle_leak,
                    "skin_pinch": payload.skin_pinch,
                    "timezone_at_event": payload.timezone_at_event,
                },
            )
            row = cursor.fetchone()
        if row is None:
            raise InfrastructureError("Insulin injection INSERT returned no row")
        injection_id = int(row["id"])
        if commit:
            connection.commit()
        return injection_id
    except Exception:
        if commit:
            connection.rollback()
        raise


def list_insulin_injections(
    connection,
    user_id: int,
    *,
    limit: int = 15,
    offset: int = 0,
) -> list[InsulinInjectionRead]:
    """List the user's injections with pagination.

    Order: shot_time DESC, id DESC (index: idx_insulin_injections_users_id_shot_time).

    Args:
        connection: DB connection
        user_id: id of the owner user
        limit: maximum rows per page
        offset: rows to skip

    Returns:
        list of InsulinInjectionRead (empty if there are no rows)
    """
    query = """
        SELECT
            id, users_id, intake_event_id, shot_time, insulin_type, units, injection_zone,
            notes, needle_leak, skin_pinch, timezone_at_event, created_at, updated_at
        FROM insulin_injections
        WHERE users_id = %(user_id)s
        ORDER BY shot_time DESC, id DESC
        LIMIT %(limit)s OFFSET %(offset)s;
    """
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            {"user_id": user_id, "limit": limit, "offset": offset},
        )
        rows = cursor.fetchall()
    return [insulin_injection_read_from_row(row) for row in rows]


def get_insulin_injection(
    connection,
    user_id: int,
    injection_id: int,
) -> InsulinInjectionRead | None:
    """Fetch an injection by id, checking its owner.

    Args:
        connection: DB connection
        user_id: id of the user (ownership filter)
        injection_id: id of the injection

    Returns:
        InsulinInjectionRead if it exists and belongs to the user, None otherwise
    """
    query = """
        SELECT
            id, users_id, intake_event_id, shot_time, insulin_type, units, injection_zone,
            notes, needle_leak, skin_pinch, timezone_at_event, created_at, updated_at
        FROM insulin_injections
        WHERE id = %(injection_id)s AND users_id = %(user_id)s;
    """
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            {"injection_id": injection_id, "user_id": user_id},
        )
        row = cursor.fetchone()
    return insulin_injection_read_from_row(row) if row else None


def get_injection_shot_time_at_offset(
    connection,
    user_id: int,
    offset: int,
) -> datetime | None:
    """Fetch the shot_time of the injection at a pagination position.

    Used to show the boundary date in the pagination (e.g. "Previous: 2026-09-06").

    Args:
        connection: DB connection
        user_id: id of the user
        offset: position in the ordered list

    Returns:
        datetime (aware UTC) if it exists, None otherwise
    """
    query = """
        SELECT shot_time
        FROM insulin_injections
        WHERE users_id = %(user_id)s
        ORDER BY shot_time DESC, id DESC
        LIMIT 1 OFFSET %(offset)s;
    """
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            {"user_id": user_id, "offset": offset},
        )
        row = cursor.fetchone()
    return row["shot_time"] if row else None


def update_insulin_injection(
    connection,
    user_id: int,
    injection_id: int,
    payload: InsulinInjectionUpdate,
    *,
    commit: bool = True,
) -> None:
    """Update an existing injection.

    Updatable fields: insulin_type, shot_time, injection_zone, units.
    updated_at is set automatically by DEFAULT CURRENT_TIMESTAMP in the DB.

    Args:
        connection: DB connection
        user_id: id of the user (ownership filter)
        injection_id: id of the injection
        payload: InsulinInjectionUpdate with the new values
        commit: if True, commits the transaction

    Returns:
        None. Raises NotFoundError if the row does not exist or is not the user's.

    Raises:
        ValidationError: if insulin_type/units are not consistent
        NotFoundError: if the row does not exist or is not the user's
    """
    # Validate before reaching the DB
    validate_insulin_dose(payload.insulin_type, payload.units)

    query = """
        UPDATE insulin_injections
        SET
            insulin_type = %(insulin_type)s,
            shot_time = %(shot_time)s,
            injection_zone = %(injection_zone)s,
            units = %(units)s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %(injection_id)s AND users_id = %(user_id)s
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "injection_id": injection_id,
                    "user_id": user_id,
                    "insulin_type": payload.insulin_type.value,
                    "shot_time": payload.shot_time,
                    "injection_zone": payload.injection_zone.value if payload.injection_zone else None,
                    "units": payload.units,
                },
            )
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(f"Insulin injection {injection_id} not found or not owned by user {user_id}")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def delete_insulin_injection(
    connection,
    user_id: int,
    injection_id: int,
    *,
    commit: bool = True,
) -> None:
    """Delete an existing injection.

    Args:
        connection: DB connection
        user_id: id of the user (ownership filter)
        injection_id: id of the injection
        commit: if True, commits the transaction

    Returns:
        None. Raises NotFoundError if the row does not exist or is not the user's.

    Raises:
        NotFoundError: if the row does not exist or is not the user's
    """
    query = """
        DELETE FROM insulin_injections
        WHERE id = %(injection_id)s AND users_id = %(user_id)s
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"injection_id": injection_id, "user_id": user_id},
            )
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError(f"Insulin injection {injection_id} not found or not owned by user {user_id}")
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise
