"""Queries para la tabla puente `linked_tags` (catalog/manual_intake/recipe <-> tags).

`set_entry_tags` crea o reutiliza tags al enlazarlos (mismo criterio que
`ensure_tag`), por lo que reutiliza los helpers de normalización de
`crud.py` en vez de duplicarlos.
"""

from DayBetes_food.database.queries.crud import (
    _execute_query_many,
    _normalize_tag_name,
    _tag_color_from_name,
    logger,
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
    except Exception as e:
        if commit:
            connection.rollback()
            logger.error("Error in query: %s", e, exc_info=True)
            return False
        raise
