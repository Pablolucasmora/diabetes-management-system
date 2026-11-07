"""Queries for `insulin_brand` (code_conventions.md §11.2.7, measurement §8.4).

A brand is private: every query carries its owner in the SQL (§5.3), so a brand
of another user and one that does not exist give the same `NotFoundError` (§5.4).
Only active brands (`deleted_at IS NULL`) are read or edited.
"""

from psycopg.errors import UniqueViolation

from DayBetes_food.database.mappers import insulin_brand_read_from_row
from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many
from DayBetes_food.domain.insulin_pen import InsulinBrandCreate, InsulinBrandRead, InsulinBrandUpdate
from DayBetes_food.errors import ConflictError, NotFoundError

_BRAND_COLUMNS = """
    b.id, b.users_id, b.name, b.insulin_type, b.in_use_days, b.pen_units, b.created_at, b.updated_at,
    (SELECT count(*) FROM insulin_pen p WHERE p.insulin_brand_id = b.id) AS pen_count
"""
_ACTIVE_AND_OWNED = "b.users_id = %(user_id)s AND b.deleted_at IS NULL"

_DUPLICATE_NAME = "You already have a brand with that name."


def create_insulin_brand(connection, payload: InsulinBrandCreate, commit: bool = True) -> int:
    """Raises ConflictError when the user already has an active brand with that name (§6.2)."""
    try:
        row = _execute_query(
            connection,
            """
            INSERT INTO insulin_brand (users_id, name, insulin_type, in_use_days, pen_units)
            VALUES (%(user_id)s, %(name)s, %(insulin_type)s, %(in_use_days)s, %(pen_units)s)
            RETURNING id;
            """,
            {
                "user_id": payload.user_id,
                "name": payload.name,
                "insulin_type": payload.insulin_type.value,
                "in_use_days": payload.in_use_days,
                "pen_units": payload.pen_units,
            },
            commit=commit,
        )
    except UniqueViolation as exc:
        raise ConflictError(_DUPLICATE_NAME) from exc
    return int(row["id"])


def list_insulin_brands(connection, user_id: int) -> list[InsulinBrandRead]:
    """Active brands of the user, by name (uq_insulin_brand_users_id_name)."""
    rows = _execute_query_many(
        connection,
        f"SELECT {_BRAND_COLUMNS} FROM insulin_brand b WHERE {_ACTIVE_AND_OWNED} ORDER BY lower(b.name), b.id;",
        {"user_id": user_id},
        commit=False,
    )
    return [insulin_brand_read_from_row(row) for row in rows]


def get_insulin_brand(connection, user_id: int, brand_id: int) -> InsulinBrandRead | None:
    row = _execute_query(
        connection,
        f"SELECT {_BRAND_COLUMNS} FROM insulin_brand b WHERE b.id = %(brand_id)s AND {_ACTIVE_AND_OWNED};",
        {"brand_id": brand_id, "user_id": user_id},
        commit=False,
    )
    return insulin_brand_read_from_row(row) if row else None


def lock_insulin_brand(connection, user_id: int, brand_id: int) -> bool:
    """Lock an active brand of the user until the transaction ends (§6.8): deleting it
    and opening a pen of it must not cross. False if it is not there."""
    row = _execute_query(
        connection,
        "SELECT b.id FROM insulin_brand b WHERE b.id = %(brand_id)s AND "
        f"{_ACTIVE_AND_OWNED} FOR UPDATE;",
        {"brand_id": brand_id, "user_id": user_id},
        commit=False,
    )
    return row is not None


def update_insulin_brand(
    connection, user_id: int, brand_id: int, payload: InsulinBrandUpdate, commit: bool = True
) -> None:
    """Replace the editable fields. The type only changes while no pen uses the brand
    (measurement §8.4), checked in the same UPDATE.

    Raises:
        NotFoundError: the brand is not an active one of the user.
        ConflictError: the name is taken, or the type changes and it has pens.
    """
    params = {
        "brand_id": brand_id,
        "user_id": user_id,
        "name": payload.name,
        "insulin_type": payload.insulin_type.value,
        "in_use_days": payload.in_use_days,
        "pen_units": payload.pen_units,
    }
    try:
        row = _execute_query(
            connection,
            f"""
            UPDATE insulin_brand b
            SET name = %(name)s,
                insulin_type = %(insulin_type)s,
                in_use_days = %(in_use_days)s,
                pen_units = %(pen_units)s,
                updated_at = CURRENT_TIMESTAMP
            WHERE b.id = %(brand_id)s AND {_ACTIVE_AND_OWNED}
              AND (b.insulin_type = %(insulin_type)s
                   OR NOT EXISTS (SELECT 1 FROM insulin_pen p WHERE p.insulin_brand_id = b.id))
            RETURNING b.id;
            """,
            params,
            commit=commit,
        )
    except UniqueViolation as exc:
        raise ConflictError(_DUPLICATE_NAME) from exc
    if row is None:
        if get_insulin_brand(connection, user_id, brand_id) is None:
            raise NotFoundError("Brand not found.")
        raise ConflictError("A brand with pens cannot change its insulin type.")


def delete_insulin_brand(connection, user_id: int, brand_id: int, commit: bool = True) -> bool:
    """Physical delete of a brand no pen uses (§11.2.7). False if it has pens or is
    not an active one of the user: the caller then archives it or answers 404."""
    row = _execute_query(
        connection,
        f"""
        DELETE FROM insulin_brand b
        WHERE b.id = %(brand_id)s AND {_ACTIVE_AND_OWNED}
          AND NOT EXISTS (SELECT 1 FROM insulin_pen p WHERE p.insulin_brand_id = b.id)
        RETURNING b.id;
        """,
        {"brand_id": brand_id, "user_id": user_id},
        commit=commit,
    )
    return row is not None


def archive_insulin_brand(connection, user_id: int, brand_id: int, commit: bool = True) -> bool:
    """Archive a brand that has pens (§11.2.7, §11.3). No restore_ (decision 2026-09-23)."""
    row = _execute_query(
        connection,
        f"""
        UPDATE insulin_brand b
        SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE b.id = %(brand_id)s AND {_ACTIVE_AND_OWNED}
        RETURNING b.id;
        """,
        {"brand_id": brand_id, "user_id": user_id},
        commit=commit,
    )
    return row is not None
