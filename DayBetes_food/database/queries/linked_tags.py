"""Queries for the `linked_tags` bridge table (catalog/manual_intake/recipe <-> tags).

`set_entry_tags` creates or reuses tags when linking them (same criterion as
`ensure_tag`), so it reuses the normalization helpers of `crud.py` instead
of duplicating them.
"""

from DayBetes_food.database.queries.crud import (
    _execute_query_many,
    _normalize_tag_name,
    _tag_color_from_name,
)


def get_entry_tags(connection, entry_type: str, entry_id: int) -> list[dict]:
    entry_col = {"catalog": "catalog_id", "manual_intake": "manual_intake_id", "recipe": "recipe_id"}.get(entry_type)
    if not entry_col or not entry_id:
        return []
    query = f"""
        SELECT t.id, t.name, t.color
        FROM linked_tags lt
        INNER JOIN tags t ON t.id = lt.tag_id
        WHERE lt.{entry_col} = %(entry_id)s
        ORDER BY lower(t.name), t.id;
    """
    return _execute_query_many(connection, query, {"entry_id": entry_id}, commit=False)


def set_entry_tags(
    connection,
    entry_type: str,
    entry_id: int,
    tag_names: list[str],
    commit: bool = True,
) -> bool:
    entry_col = {"catalog": "catalog_id", "manual_intake": "manual_intake_id", "recipe": "recipe_id"}.get(entry_type)
    if not entry_col or not entry_id:
        return False

    unique_names = []
    seen = set()
    for raw in tag_names or []:
        clean = _normalize_tag_name(raw)
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        unique_names.append(clean)

    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM linked_tags WHERE {entry_col} = %(entry_id)s;", {"entry_id": entry_id})
            for name in unique_names:
                cursor.execute(
                    """
                    INSERT INTO tags (name, color)
                    VALUES (%(name)s, %(color)s)
                    ON CONFLICT (name) DO UPDATE SET
                        color = COALESCE(NULLIF(tags.color, ''), EXCLUDED.color);
                    """,
                    {"name": name, "color": _tag_color_from_name(name)},
                )
                cursor.execute(
                    "SELECT id FROM tags WHERE lower(trim(name)) = lower(trim(%(name)s)) LIMIT 1;",
                    {"name": name},
                )
                tag_row = cursor.fetchone()
                if not tag_row or tag_row.get("id") is None:
                    continue
                cursor.execute(
                    f"""
                    INSERT INTO linked_tags (tag_id, {entry_col})
                    VALUES (%(tag_id)s, %(entry_id)s);
                    """,
                    {"tag_id": int(tag_row["id"]), "entry_id": entry_id},
                )
        if commit:
            connection.commit()
        return True
    except Exception:
        if commit:
            connection.rollback()
        raise


_TAG_ENTRY_COLUMNS = {"catalog": "catalog_id", "manual_intake": "manual_intake_id", "recipe": "recipe_id"}


def entry_has_tag(connection, entry_type: str, entry_id: int, tag_name: str) -> bool:
    """Whether the entry is linked to the tag named `tag_name` (case-insensitive)."""
    entry_col = _TAG_ENTRY_COLUMNS.get(entry_type)
    clean = _normalize_tag_name(tag_name)
    if not entry_col or not entry_id or not clean:
        return False
    query = f"""
        SELECT 1
        FROM linked_tags lt
        INNER JOIN tags t ON t.id = lt.tag_id
        WHERE lt.{entry_col} = %(entry_id)s
          AND lower(trim(t.name)) = lower(%(name)s)
        LIMIT 1;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"entry_id": entry_id, "name": clean})
        return cursor.fetchone() is not None


def add_entry_tag(connection, entry_type: str, entry_id: int, tag_name: str, commit: bool = True) -> None:
    """Link one tag to the entry, creating the tag if needed, without touching
    its other tags (frontend_conventions.md §9.6). Idempotent: linking a tag
    that is already linked does nothing. Ownership is the caller's job."""
    entry_col = _TAG_ENTRY_COLUMNS.get(entry_type)
    clean = _normalize_tag_name(tag_name)
    if not entry_col or not entry_id or not clean:
        raise ValueError(f"Invalid tag link: {entry_type!r} {entry_id!r} {tag_name!r}")
    try:
        with connection.cursor() as cursor:
            # The tag is matched case-insensitively ("Rescate" is stored
            # capitalized): it is only created when no spelling of it exists.
            cursor.execute(
                """
                INSERT INTO tags (name, color)
                SELECT %(name)s::text, %(color)s::text
                WHERE NOT EXISTS (
                    SELECT 1 FROM tags WHERE lower(trim(name)) = lower(%(name)s::text)
                )
                ON CONFLICT (name) DO NOTHING;
                """,
                {"name": clean, "color": _tag_color_from_name(clean)},
            )
            # linked_tags has no unique key: the NOT EXISTS keeps it
            # idempotent, against any spelling of the tag.
            cursor.execute(
                f"""
                INSERT INTO linked_tags (tag_id, {entry_col})
                SELECT t.id, %(entry_id)s
                FROM (
                    SELECT id FROM tags
                    WHERE lower(trim(name)) = lower(%(name)s)
                    ORDER BY id
                    LIMIT 1
                ) t
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM linked_tags lt
                    INNER JOIN tags lt_tag ON lt_tag.id = lt.tag_id
                    WHERE lt.{entry_col} = %(entry_id)s
                      AND lower(trim(lt_tag.name)) = lower(%(name)s)
                );
                """,
                {"entry_id": entry_id, "name": clean},
            )
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise


def remove_entry_tag(connection, entry_type: str, entry_id: int, tag_name: str, commit: bool = True) -> None:
    """Unlink one tag from the entry without touching its other tags. The tag
    itself stays in `tags`. Ownership is the caller's job."""
    entry_col = _TAG_ENTRY_COLUMNS.get(entry_type)
    clean = _normalize_tag_name(tag_name)
    if not entry_col or not entry_id or not clean:
        raise ValueError(f"Invalid tag link: {entry_type!r} {entry_id!r} {tag_name!r}")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                DELETE FROM linked_tags lt
                USING tags t
                WHERE t.id = lt.tag_id
                  AND lt.{entry_col} = %(entry_id)s
                  AND lower(trim(t.name)) = lower(%(name)s);
                """,
                {"entry_id": entry_id, "name": clean},
            )
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise
