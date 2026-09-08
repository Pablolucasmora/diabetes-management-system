"""Queries para la tabla `tags`."""

from typing import Optional

from DayBetes_food.database.queries.crud import (
    _build_fuzzy_search,
    _execute_query,
    _execute_query_many,
    _normalize_tag_name,
    _tag_color_from_name,
)


def get_tag_suggestions(connection, search: str = "", limit: int = 100) -> list[str]:
    search_condition, search_params, search_order = _build_fuzzy_search(connection, "name", search)
    params = {**search_params, "limit": max(1, min(int(limit or 100), 500))}
    query = """
        WITH source AS (
            SELECT DISTINCT trim(name) AS name
            FROM tags
            WHERE name IS NOT NULL
              AND trim(name) <> ''
        )
        SELECT name
        FROM source
        WHERE {search_condition}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """.format(search_condition=search_condition or "TRUE", search_order=search_order)
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def ensure_tag(connection, tag_name: str, commit: bool = True) -> Optional[int]:
    clean = _normalize_tag_name(tag_name)
    if not clean:
        return None
    query = """
        INSERT INTO tags (name, color)
        VALUES (%(name)s, %(color)s)
        ON CONFLICT (name) DO UPDATE SET
            name = EXCLUDED.name,
            color = COALESCE(NULLIF(tags.color, ''), EXCLUDED.color)
        RETURNING id;
    """
    row = _execute_query(
        connection,
        query,
        {"name": clean, "color": _tag_color_from_name(clean)},
        commit=commit,
        rollback_on_error=commit,
    )
    return int(row["id"]) if row and row.get("id") is not None else None


def get_all_tags(connection, search: str = "", limit: int = 500) -> list[dict]:
    normalized = (search or "").strip()
    params = {
        "q": normalized,
        "q_like": f"%{normalized}%",
        "limit": max(1, min(int(limit or 500), 2000)),
    }
    query = """
        SELECT t.id, t.name, t.color, t.description
        FROM tags t
        WHERE (%(q)s = '' OR t.name ILIKE %(q_like)s)
        ORDER BY lower(t.name), t.id
        LIMIT %(limit)s;
    """
    return _execute_query_many(connection, query, params, commit=False)


def update_tag(connection, tag_id: int, name: str, color: str, commit: bool = True) -> bool:
    clean_name = _normalize_tag_name(name)
    clean_color = " ".join((color or "").strip().split())
    if not clean_name or not clean_color:
        return False
    query = """
        UPDATE tags
        SET name = %(name)s,
            color = %(color)s
        WHERE id = %(id)s
        RETURNING id;
    """
    row = _execute_query(
        connection,
        query,
        {"id": tag_id, "name": clean_name, "color": clean_color},
        commit=commit,
        rollback_on_error=commit,
    )
    return row is not None
