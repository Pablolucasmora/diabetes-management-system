"""Queries para la tabla puente `user_favorites` (catalog/manual_intake/recipe)."""

from DayBetes_food.database.queries.crud import _execute_query


_FAVORITE_ENTRY_COLUMNS = {
    "catalog": "catalog_id",
    "manual_intake": "manual_intake_id",
    "recipe": "recipe_id",
}


def toggle_user_favorite(
    connection,
    user_id: int,
    entry_type: str,
    entry_id: int,
    commit: bool = True,
) -> bool | None:
    favorite_column = _FAVORITE_ENTRY_COLUMNS.get(entry_type)
    if not favorite_column or not user_id or not entry_id:
        return None
    query = f"""
        WITH deleted AS (
            DELETE FROM user_favorites
            WHERE user_id = %(user_id)s
              AND {favorite_column} = %(entry_id)s
            RETURNING id
        ), inserted AS (
            INSERT INTO user_favorites (user_id, {favorite_column})
            SELECT %(user_id)s, %(entry_id)s
            WHERE NOT EXISTS (SELECT 1 FROM deleted)
            ON CONFLICT DO NOTHING
            RETURNING id
        )
        SELECT FALSE AS favorite FROM deleted
        UNION ALL
        SELECT TRUE AS favorite FROM inserted;
    """
    row = _execute_query(
        connection,
        query,
        {"user_id": user_id, "entry_id": entry_id},
        commit=commit,
    )
    return bool(row["favorite"]) if row else None


def set_user_favorite(
    connection,
    user_id: int,
    entry_type: str,
    entry_id: int,
    favorite: bool,
    commit: bool = True,
) -> bool:
    favorite_column = _FAVORITE_ENTRY_COLUMNS.get(entry_type)
    if not favorite_column or not user_id or not entry_id:
        return False
    try:
        with connection.cursor() as cursor:
            if favorite:
                cursor.execute(
                    f"""
                    INSERT INTO user_favorites (user_id, {favorite_column})
                    VALUES (%(user_id)s, %(entry_id)s)
                    ON CONFLICT DO NOTHING;
                    """,
                    {"user_id": user_id, "entry_id": entry_id},
                )
            else:
                cursor.execute(
                    f"""
                    DELETE FROM user_favorites
                    WHERE user_id = %(user_id)s
                      AND {favorite_column} = %(entry_id)s;
                    """,
                    {"user_id": user_id, "entry_id": entry_id},
                )
        if commit:
            connection.commit()
        return True
    except Exception:
        if commit:
            connection.rollback()
        raise
