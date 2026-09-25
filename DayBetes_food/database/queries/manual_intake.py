"""Queries para la tabla `manual_intake`."""

from typing import Optional

from psycopg import sql

from DayBetes_food.database.queries.crud import (
    RawSQL,
    _add_entity_filters,
    _build_fuzzy_search,
    _build_update_query,
    _execute_query,
    _execute_query_many,
    _favorite_filter_sql,
)


def get_manual_origin_suggestions(
    connection, *, user_id: int, search: str = "", limit: int = 50
) -> list[str]:
    """Distinct origins of the manual intakes the user can see (11.4).

    Only active rows that are public or owned by `user_id`: an origin is often a
    personal place ("grandma's"), so another user's private rows must not leak
    through the autocomplete.
    """
    search_condition, search_params, search_order = _build_fuzzy_search(connection, "name", search)
    params = {
        **search_params,
        "user_id": user_id,
        "limit": max(1, min(int(limit or 50), 500)),
    }
    query = """
        WITH source AS (
            SELECT DISTINCT trim(entity.origin) AS name
            FROM manual_intake entity
            WHERE entity.deleted_at IS NULL
              AND (entity.is_published OR entity.created_by = %(user_id)s)
              AND entity.origin IS NOT NULL
              AND trim(entity.origin) <> ''
        )
        SELECT name
        FROM source
        WHERE {search_condition}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """.format(search_condition=search_condition or "TRUE", search_order=search_order)
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def add_manual_intake(connection, data: dict, commit: bool = True) -> Optional[int]:
    """Adds a new manual intake."""
    query = """
        INSERT INTO manual_intake (
            created_by, origin_root_id, name, description, subtype, origin,
            amount_g, calories_100g, carbs_100g, sugars_100g,
            fats_100g, saturated_100g, proteins_100g, fiber_100g,
            caffeine, alcohol, glycemic_index, ig_confidence
        )
        VALUES (
            %(created_by)s, %(origin_root_id)s, %(name)s, %(description)s, %(subtype)s, %(origin)s,
            %(amount_g)s, %(calories_100g)s, %(carbs_100g)s, %(sugars_100g)s,
            %(fats_100g)s, %(saturated_100g)s, %(proteins_100g)s, %(fiber_100g)s,
            %(caffeine)s, %(alcohol)s, %(glycemic_index)s, %(ig_confidence)s
        )
        RETURNING id;
    """
    payload = dict(data or {})
    payload.setdefault("origin_root_id", None)
    result = _execute_query(
        connection,
        query,
        payload,
        commit=commit,
    )
    return result["id"] if result else None


def get_manual_intake(connection, intake_id: int, viewer_user_id: int = None) -> Optional[dict]:
    """Gets a manual intake by ID."""
    query = """
        SELECT entity.*,
               EXISTS (
                   SELECT 1 FROM user_favorites uf
                   WHERE uf.user_id = %(viewer_user_id)s
                     AND uf.manual_intake_id = entity.id
               ) AS favorite
        FROM manual_intake entity
        WHERE entity.id = %(id)s
          AND entity.deleted_at IS NULL;
    """
    return _execute_query(
        connection,
        query,
        {"id": intake_id, "viewer_user_id": viewer_user_id},
        commit=False,
    )


def get_all_manual_intakes(
    connection,
    users_id: int = None,
    search: str = None,
    favorite: bool = None,
    viewer_user_id: int = None,
) -> list:
    """Gets all manual intakes with optional filters."""
    conditions = []
    params = {}
    conditions.append("entity.deleted_at IS NULL")
    
    _add_entity_filters(
        conditions,
        params,
        owner_column="created_by",
        users_id=users_id,
        favorite_condition=(
            _favorite_filter_sql("manual_intake_id", favorite, params, viewer_user_id)
            if favorite is not None
            else None
        ),
        viewer_user_id=viewer_user_id,
    )
    normalized = (search or "").strip()
    if normalized:
        name_condition, name_params, _ = _build_fuzzy_search(
            connection, "name", normalized, param_prefix="manual_name"
        )
        origin_condition, origin_params, _ = _build_fuzzy_search(
            connection, "COALESCE(origin, '')", normalized, param_prefix="manual_origin"
        )
        conditions.append(f"({name_condition} OR {origin_condition})")
        params.update(name_params)
        params.update(origin_params)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params["favorite_viewer_id"] = viewer_user_id
    query = f"SELECT entity.*, EXISTS (SELECT 1 FROM user_favorites uf WHERE uf.user_id = %(favorite_viewer_id)s AND uf.manual_intake_id = entity.id) AS favorite FROM manual_intake entity {where_clause} ORDER BY entity.name;"
    
    return _execute_query_many(connection, query, params, commit=False)


def manual_intake_name_origin_exists(
    connection,
    users_id: int,
    name: str,
    origin: str | None = None,
    exclude_id: int | None = None,
) -> bool:
    normalized_name = " ".join((name or "").strip().split())
    normalized_origin = " ".join((origin or "").strip().split())
    if not normalized_name or not users_id:
        return False
    params = {
        "users_id": users_id,
        "name": normalized_name,
        "origin": normalized_origin,
    }
    exclusion = ""
    if exclude_id is not None:
        params["exclude_id"] = exclude_id
        exclusion = "AND id <> %(exclude_id)s"
    query = f"""
        SELECT 1
        FROM manual_intake
        WHERE created_by = %(users_id)s
          AND deleted_at IS NULL
          AND lower(trim(name)) = lower(trim(%(name)s))
          AND lower(trim(COALESCE(origin, ''))) = lower(trim(COALESCE(%(origin)s, '')))
          {exclusion}
        LIMIT 1;
    """
    row = _execute_query(connection, query, params, commit=False)
    return row is not None


def update_manual_intake(connection, intake_id: int, data: dict, commit: bool = True) -> bool:
    """Updates a manual intake."""
    if not data:
        return False
    
    payload = dict(data or {})
    payload.pop("favorite", None)
    params = {**payload, "id": intake_id}
    query = _build_update_query(
        "manual_intake",
        params,
        raw_fields={"updated_at": RawSQL.NOW},
        extra_where=sql.SQL("deleted_at IS NULL"),
    )
    
    if not query:
        return False
        
    result = _execute_query(
        connection,
        query,
        params,
        commit=commit,
    )
    return result is not None


def delete_manual_intake(connection, intake_id: int, commit: bool = True) -> bool:
    """Archives a manual intake by ID."""
    query = """
        UPDATE manual_intake
        SET deleted_at = NOW(),
            updated_at = NOW()
        WHERE id = %(id)s
          AND deleted_at IS NULL
        RETURNING id;
    """
    result = _execute_query(
        connection,
        query,
        {"id": intake_id},
        commit=commit,
    )
    return result is not None
