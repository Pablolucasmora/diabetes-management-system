"""Queries for the `fridge` table and its place history, `fridge_move`
(code_conventions.md §11.2.6, measurement_conventions.md §4.8).

A container is private: every query carries its owner in the SQL (§5.3), so a
container of another user and one that does not exist give the same
`NotFoundError` (§5.4). Only open containers (`closed_at IS NULL`) are read or
changed: a closed one is never listed nor reopened.
"""

from datetime import datetime

from psycopg.errors import CheckViolation

from DayBetes_food.database.mappers import fridge_read_from_row
from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many
from DayBetes_food.domain.constants import StorageLocation
from DayBetes_food.domain.fridge import FridgeCreate, FridgeRead, FridgeUpdate
from DayBetes_food.errors import NotFoundError, ValidationError

_FRIDGE_COLUMNS = """
    f.id, f.users_id, f.name, f.location, f.stored_at, f.expires_at,
    f.content_weight, f.closed_at, f.created_at, f.updated_at
"""
_OPEN_AND_OWNED = "f.users_id = %(user_id)s AND f.closed_at IS NULL"


def create_fridge(connection, payload: FridgeCreate, commit: bool = True) -> int:
    """Store a new container. Its content is added afterwards, in the same
    transaction, as portions with destination `fridge` (§4.8.1)."""
    row = _execute_query(
        connection,
        """
        INSERT INTO fridge (users_id, name, location, stored_at, expires_at, content_weight)
        VALUES (%(user_id)s, %(name)s, %(location)s, %(stored_at)s, %(expires_at)s, %(content_weight)s)
        RETURNING id;
        """,
        {
            "user_id": payload.user_id,
            "name": payload.name,
            "location": payload.location.value,
            "stored_at": payload.stored_at,
            "expires_at": payload.expires_at,
            "content_weight": payload.content_weight,
        },
        commit=commit,
    )
    return int(row["id"])


def get_fridge(connection, user_id: int, fridge_id: int) -> FridgeRead | None:
    """An open container of the user, or None (it does not exist, is closed or is
    not theirs, §5.4)."""
    row = _execute_query(
        connection,
        f"SELECT {_FRIDGE_COLUMNS} FROM fridge f WHERE f.id = %(fridge_id)s AND {_OPEN_AND_OWNED};",
        {"fridge_id": fridge_id, "user_id": user_id},
        commit=False,
    )
    return fridge_read_from_row(row) if row else None


def list_fridges(connection, user_id: int) -> list[FridgeRead]:
    """The user's open containers, the soonest to expire first (idx_fridge_users_id_open)."""
    rows = _execute_query_many(
        connection,
        f"SELECT {_FRIDGE_COLUMNS} FROM fridge f WHERE {_OPEN_AND_OWNED} ORDER BY f.expires_at, f.id;",
        {"user_id": user_id},
        commit=False,
    )
    return [fridge_read_from_row(row) for row in rows]


def update_fridge(connection, user_id: int, fridge_id: int, payload: FridgeUpdate, commit: bool = True) -> None:
    """Full replacement of the editable fields (§3.4). Last write wins: it is the
    user's own label, expiry and weight, and only they edit it (§6.10).

    An expiry not after `stored_at` is rejected by ck_fridge_expires_after_stored
    and returned as ValidationError. No row -> NotFoundError.
    """
    try:
        row = _execute_query(
            connection,
            """
            UPDATE fridge
            SET name = %(name)s, expires_at = %(expires_at)s, content_weight = %(content_weight)s, updated_at = NOW()
            WHERE fridge.id = %(fridge_id)s
              AND fridge.users_id = %(user_id)s
              AND fridge.closed_at IS NULL
            RETURNING fridge.id;
            """,
            {
                "name": payload.name,
                "expires_at": payload.expires_at,
                "content_weight": payload.content_weight,
                "fridge_id": fridge_id,
                "user_id": user_id,
            },
            commit=commit,
        )
    except CheckViolation as exc:
        if getattr(exc.diag, "constraint_name", None) == "ck_fridge_expires_after_stored":
            raise ValidationError(
                "The expiry date cannot be before the day it was stored.", fields={"expires_at": "out_of_range"}
            ) from exc
        raise
    if row is None:
        raise NotFoundError("Container not found.")


def set_fridge_location(
    connection,
    user_id: int,
    fridge_id: int,
    location: StorageLocation,
    moved_at: datetime,
    expires_at: datetime,
    commit: bool = True,
) -> bool:
    """Move a container to `location` and record it in `fridge_move`, in one statement.

    It sets a state, it is not a toggle (§6.3): True when it moved; False when it
    was already there, which leaves it and its history untouched, so repeating the
    request is a no-op. `expires_at` is the new expiry (§4.8.2), computed by the
    caller from `moved_at`. No row -> NotFoundError.
    """
    row = _execute_query(
        connection,
        """
        WITH current AS (
            SELECT f.id, f.location
            FROM fridge f
            WHERE f.id = %(fridge_id)s AND f.users_id = %(user_id)s AND f.closed_at IS NULL
            FOR UPDATE
        ), moved AS (
            UPDATE fridge
            SET location = %(location)s, expires_at = %(expires_at)s, updated_at = NOW()
            FROM current c
            WHERE fridge.id = c.id AND c.location <> %(location)s
            RETURNING fridge.id, c.location AS from_location
        ), history AS (
            INSERT INTO fridge_move (fridge_id, from_location, to_location, moved_at)
            SELECT m.id, m.from_location, %(location)s, %(moved_at)s
            FROM moved m
            RETURNING fridge_move.fridge_id
        )
        SELECT (SELECT count(*) FROM current) AS found, (SELECT count(*) FROM history) AS moved;
        """,
        {
            "fridge_id": fridge_id,
            "user_id": user_id,
            "location": location.value,
            "moved_at": moved_at,
            "expires_at": expires_at,
        },
        commit=commit,
    )
    if not row["found"]:
        raise NotFoundError("Container not found.")
    return bool(row["moved"])


def delete_fridge(connection, user_id: int, fridge_id: int, commit: bool = True) -> bool:
    """Physical delete of a container nothing eaten references (§11.2.6), with its
    content and history (CASCADE): what is thrown away is not kept.

    True when deleted; False when a portion of a meal references it, so it must be
    closed instead (§3.4: the row exists, the operation does not apply). No row ->
    NotFoundError.
    """
    row = _execute_query(
        connection,
        """
        WITH target AS (
            SELECT f.id,
                   EXISTS (SELECT 1 FROM portion_detail pd WHERE pd.source_fridge_id = f.id) AS is_referenced
            FROM fridge f
            WHERE f.id = %(fridge_id)s AND f.users_id = %(user_id)s AND f.closed_at IS NULL
            FOR UPDATE
        ), deleted AS (
            DELETE FROM fridge
            USING target t
            WHERE fridge.id = t.id AND NOT t.is_referenced
            RETURNING fridge.id
        )
        SELECT (SELECT count(*) FROM target) AS found, (SELECT count(*) FROM deleted) AS deleted;
        """,
        {"fridge_id": fridge_id, "user_id": user_id},
        commit=commit,
    )
    if not row["found"]:
        raise NotFoundError("Container not found.")
    return bool(row["deleted"])


def close_fridge(connection, user_id: int, fridge_id: int, commit: bool = True) -> None:
    """Take a container out of the fridge for good (`closed_at`, §11.2.6). It keeps
    its row because the portions eaten from it reference it. No open row ->
    NotFoundError, so repeating it is a 404, as for a deleted one."""
    row = _execute_query(
        connection,
        """
        UPDATE fridge
        SET closed_at = NOW(), updated_at = NOW()
        WHERE fridge.id = %(fridge_id)s AND fridge.users_id = %(user_id)s AND fridge.closed_at IS NULL
        RETURNING fridge.id;
        """,
        {"fridge_id": fridge_id, "user_id": user_id},
        commit=commit,
    )
    if row is None:
        raise NotFoundError("Container not found.")
