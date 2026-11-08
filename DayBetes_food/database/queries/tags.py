"""Queries for the `tags` table (code_conventions.md §11.2.8).

A user sees the system tags and their own personal tags, and only edits or
deletes their own: the owner travels in the SQL (§5.3), so another user's tag
and one that does not exist give the same result (§5.4). A system tag is
identified by `system_key`, never by its name.
"""

from psycopg.errors import UniqueViolation

from DayBetes_food.database.mappers import tag_read_from_row
from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many
from DayBetes_food.domain.search_text import normalize_search_text, search_text_sql
from DayBetes_food.domain.tag import TagCreate, TagRead, TagUpdate
from DayBetes_food.errors import ConflictError, NotFoundError

_TAG_COLUMNS = "t.id, t.users_id, t.system_key, t.name, t.color"
# The tags a user can see and put on a food: the system ones and their own.
_VISIBLE = "(t.users_id IS NULL OR t.users_id = %(user_id)s)"
_OWN = "t.users_id = %(user_id)s"

_DUPLICATE_NAME = "You already have a tag with that name."


def list_tags(connection, user_id: int, search: str = "", limit: int = 500) -> list[TagRead]:
    """System tags first, then the user's own, by name. The search ignores case and
    accents, like the other searches (§11.7)."""
    term = normalize_search_text(search)
    rows = _execute_query_many(
        connection,
        f"""
        SELECT {_TAG_COLUMNS}
        FROM tags t
        WHERE {_VISIBLE}
          AND (%(term)s = '' OR {search_text_sql("t.name")} LIKE %(term_like)s)
        ORDER BY (t.system_key IS NULL), lower(t.name), t.id
        LIMIT %(limit)s;
        """,
        {
            "user_id": user_id,
            "term": term,
            "term_like": f"%{term}%",
            "limit": max(1, min(int(limit or 500), 2000)),
        },
        commit=False,
    )
    return [tag_read_from_row(row) for row in rows]


def get_tag(connection, user_id: int, tag_id: int) -> TagRead | None:
    """A system tag or one of the user's own; None for any other."""
    row = _execute_query(
        connection,
        f"SELECT {_TAG_COLUMNS} FROM tags t WHERE t.id = %(tag_id)s AND {_VISIBLE};",
        {"tag_id": tag_id, "user_id": user_id},
        commit=False,
    )
    return tag_read_from_row(row) if row else None


def get_tag_by_name(connection, user_id: int, name: str) -> TagRead | None:
    """The system or own tag with that name, ignoring case: typing the name of a
    tag that exists reuses it instead of failing."""
    row = _execute_query(
        connection,
        f"""
        SELECT {_TAG_COLUMNS} FROM tags t
        WHERE lower(t.name) = lower(%(name)s) AND {_VISIBLE}
        ORDER BY (t.system_key IS NULL), t.id
        LIMIT 1;
        """,
        {"name": name, "user_id": user_id},
        commit=False,
    )
    return tag_read_from_row(row) if row else None


def create_tag(connection, payload: TagCreate, commit: bool = True) -> int:
    """Raises ConflictError when the user already has a tag with that name
    (uq_tags_users_id_name), or a system tag is called like that (§6.2)."""
    try:
        row = _execute_query(
            connection,
            """
            INSERT INTO tags (users_id, name, color)
            SELECT %(user_id)s::integer, %(name)s::text, %(color)s::text
            WHERE NOT EXISTS (
                SELECT 1 FROM tags s WHERE s.system_key IS NOT NULL AND lower(s.name) = lower(%(name)s::text)
            )
            RETURNING id;
            """,
            {"user_id": payload.user_id, "name": payload.name, "color": payload.color},
            commit=commit,
        )
    except UniqueViolation as exc:
        raise ConflictError(_DUPLICATE_NAME) from exc
    if row is None:
        raise ConflictError(_DUPLICATE_NAME)
    return int(row["id"])


def update_tag(connection, user_id: int, tag_id: int, payload: TagUpdate, commit: bool = True) -> None:
    """Rename or recolor one of the user's own tags.

    Raises:
        NotFoundError: not a tag of the user (a system tag included: it is not theirs).
        ConflictError: the name is taken by another tag of theirs or a system tag.
    """
    try:
        row = _execute_query(
            connection,
            f"""
            UPDATE tags t
            SET name = %(name)s, color = %(color)s
            WHERE t.id = %(tag_id)s AND {_OWN}
              AND NOT EXISTS (
                  SELECT 1 FROM tags s WHERE s.system_key IS NOT NULL AND lower(s.name) = lower(%(name)s)
              )
            RETURNING t.id;
            """,
            {"tag_id": tag_id, "user_id": user_id, "name": payload.name, "color": payload.color},
            commit=commit,
        )
    except UniqueViolation as exc:
        raise ConflictError(_DUPLICATE_NAME) from exc
    if row is None:
        tag = get_tag(connection, user_id, tag_id)
        if tag is None or tag.is_system:
            raise NotFoundError("Tag not found.")
        raise ConflictError(_DUPLICATE_NAME)


def delete_tag(connection, user_id: int, tag_id: int, commit: bool = True) -> bool:
    """Physical delete of one of the user's own tags; its links go with it (CASCADE).
    False if it is not one of theirs: the caller answers 404 (§5.4)."""
    row = _execute_query(
        connection,
        f"DELETE FROM tags t WHERE t.id = %(tag_id)s AND {_OWN} RETURNING t.id;",
        {"tag_id": tag_id, "user_id": user_id},
        commit=commit,
    )
    return row is not None
