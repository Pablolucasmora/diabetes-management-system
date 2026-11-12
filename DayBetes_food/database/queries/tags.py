"""Queries for the `tags` table (code_conventions.md §11.2.8).

A user sees the system tags and their own personal tags, and only edits or
deletes their own: the owner travels in the SQL (§5.3), so another user's tag
and one that does not exist give the same result (§5.4). A system tag is
identified by `system_key`, never by its name: its row stores the key, and the
name shown is a presentation label (components/food/tags.py). A personal tag
cannot take that label: the route checks it before writing, against the labels.

Renaming or recoloring is last write wins: two tabs editing the same tag keep
the last save (§6.7 single user, §6.10: a preference, not clinical data).
"""

from psycopg.errors import UniqueViolation

from DayBetes_food.database.mappers import tag_read_from_row
from DayBetes_food.database.queries.crud import _escape_like, _execute_query, _execute_query_many
from DayBetes_food.domain.constants import SystemTag
from DayBetes_food.domain.search_text import normalize_search_text, search_text_sql
from DayBetes_food.domain.tag import TAG_NAME_TAKEN, TagCreate, TagRead, TagUpdate
from DayBetes_food.errors import ConflictError, NotFoundError

_TAG_COLUMNS = "t.id, t.users_id, t.system_key, t.name, t.color"
# The tags a user can see and put on a food: the system ones and their own.
_VISIBLE = "(t.users_id IS NULL OR t.users_id = %(user_id)s)"
_OWN = "t.users_id = %(user_id)s"


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
            "term_like": f"%{_escape_like(term)}%",
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


def get_system_tag(connection, system_key: SystemTag) -> TagRead | None:
    """The system tag with that key; None only if the bootstrap has not created it."""
    row = _execute_query(
        connection,
        f"SELECT {_TAG_COLUMNS} FROM tags t WHERE t.system_key = %(system_key)s;",
        {"system_key": system_key.value},
        commit=False,
    )
    return tag_read_from_row(row) if row else None


def get_tag_by_name(connection, user_id: int, name: str) -> TagRead | None:
    """The user's own tag with that name, ignoring case: typing the name of a tag
    that exists reuses it instead of failing. A system tag is found by its label,
    in the route, never by its stored name."""
    row = _execute_query(
        connection,
        f"SELECT {_TAG_COLUMNS} FROM tags t WHERE lower(t.name) = lower(%(name)s) AND {_OWN};",
        {"name": name, "user_id": user_id},
        commit=False,
    )
    return tag_read_from_row(row) if row else None


def create_tag(connection, payload: TagCreate, commit: bool = True) -> int:
    """Raises ConflictError when the user already has a tag with that name
    (uq_tags_users_id_name, §6.2)."""
    try:
        row = _execute_query(
            connection,
            "INSERT INTO tags (users_id, name, color) VALUES (%(user_id)s, %(name)s, %(color)s) RETURNING id;",
            {"user_id": payload.user_id, "name": payload.name, "color": payload.color},
            commit=commit,
        )
    except UniqueViolation as exc:
        raise ConflictError(TAG_NAME_TAKEN) from exc
    return int(row["id"])


def update_tag(connection, user_id: int, tag_id: int, payload: TagUpdate, commit: bool = True) -> None:
    """Rename or recolor one of the user's own tags. Last write wins (module
    docstring); repeating it leaves the same values.

    Raises:
        NotFoundError: not a tag of the user (a system tag included: it is not theirs).
        ConflictError: the name is taken by another tag of theirs.
    """
    try:
        row = _execute_query(
            connection,
            f"""
            UPDATE tags t
            SET name = %(name)s, color = %(color)s
            WHERE t.id = %(tag_id)s AND {_OWN}
            RETURNING t.id;
            """,
            {"tag_id": tag_id, "user_id": user_id, "name": payload.name, "color": payload.color},
            commit=commit,
        )
    except UniqueViolation as exc:
        raise ConflictError(TAG_NAME_TAKEN) from exc
    if row is None:
        raise NotFoundError("Tag not found.")


def delete_tag(connection, user_id: int, tag_id: int, commit: bool = True) -> None:
    """Physical delete of one of the user's own tags; its links go with it (CASCADE).

    Repeating it, another user's tag or a system tag -> NotFoundError (§3.4, §5.4).
    """
    row = _execute_query(
        connection,
        f"DELETE FROM tags t WHERE t.id = %(tag_id)s AND {_OWN} RETURNING t.id;",
        {"tag_id": tag_id, "user_id": user_id},
        commit=commit,
    )
    if row is None:
        raise NotFoundError("Tag not found.")
