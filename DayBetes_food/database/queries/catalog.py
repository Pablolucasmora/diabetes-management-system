"""Queries para la tabla `catalog`."""

from typing import Optional

from DayBetes_food.database.queries.crud import (
    RawSQL,
    _add_entity_filters,
    _build_fuzzy_search,
    _build_update_query,
    _execute_query,
    _execute_query_many,
    _favorite_filter_sql,
)


_NULLABLE_CATALOG_FIELDS = {
    "brand_id",
    "initial_state",
    "nutriscore",
    "nova",
    "yuka",
    "default_portion",
    "calories_100g",
    "carbs_100g",
    "sugars_100g",
    "fats_100g",
    "saturated_100g",
    "proteins_100g",
    "fiber_100g",
    "caffeine",
    "alcohol",
    "barcode",
    "cooking_factor",
}


def add_catalog_item(connection, data: dict, commit: bool = True) -> Optional[int]:
    """
    Adds a new item to the catalog.
    data: dict with the food item fields
    """
    query = """
        INSERT INTO catalog (
            created_by, origin_root_id, name, brand_id, category, subtype, initial_state,
            nutriscore, nova, yuka, default_portion,
            calories_100g, carbs_100g, sugars_100g, fats_100g,
            saturated_100g, proteins_100g, fiber_100g,
            caffeine, alcohol, barcode, cooking_factor, is_private,
            created_at, updated_at
        )
        VALUES (
            %(created_by)s, %(origin_root_id)s, %(name)s, %(brand_id)s, %(category)s, %(subtype)s, %(initial_state)s,
            %(nutriscore)s, %(nova)s, %(yuka)s, %(default_portion)s,
            %(calories_100g)s, %(carbs_100g)s, %(sugars_100g)s, %(fats_100g)s,
            %(saturated_100g)s, %(proteins_100g)s, %(fiber_100g)s,
            %(caffeine)s, %(alcohol)s, %(barcode)s, %(cooking_factor)s, %(is_private)s,
            NOW(), NOW()
        )
        RETURNING id;
    """
    payload = dict(data or {})
    payload.setdefault("origin_root_id", None)
    payload.setdefault("brand_id", None)
    if payload.get("cooking_factor") is None:
        payload["cooking_factor"] = 1.0
    result = _execute_query(connection, query, payload, commit=commit, rollback_on_error=commit)
    return result["id"] if result else None


def get_catalog_item(connection, catalog_id: int, viewer_user_id: int = None) -> Optional[dict]:
    """Gets a catalog item by ID."""
    query = """
        SELECT entity.*, fb.label AS brand,
               EXISTS (
                   SELECT 1 FROM user_favorites uf
                   WHERE uf.user_id = %(viewer_user_id)s
                     AND uf.catalog_id = entity.id
               ) AS favorite
        FROM catalog entity
        LEFT JOIN food_brands fb ON fb.id = entity.brand_id
        WHERE entity.id = %(id)s;
    """
    return _execute_query(
        connection,
        query,
        {"id": catalog_id, "viewer_user_id": viewer_user_id},
        commit=False,
    )


def get_catalog_item_by_barcode(connection, barcode: str, viewer_user_id: int = None) -> Optional[dict]:
    """Gets a catalog item by barcode."""
    clean = (barcode or "").strip()
    if not clean:
        return None
    params = {"barcode": clean, "viewer_user_id": viewer_user_id}
    visibility_clause = ""
    if viewer_user_id is not None:
        visibility_clause = "AND (is_private = FALSE OR created_by = %(viewer_user_id)s)"
    query = f"""
        SELECT entity.*, fb.label AS brand,
               EXISTS (
                   SELECT 1 FROM user_favorites uf
                   WHERE uf.user_id = %(viewer_user_id)s
                     AND uf.catalog_id = entity.id
               ) AS favorite
        FROM catalog entity
        LEFT JOIN food_brands fb ON fb.id = entity.brand_id
        WHERE entity.deleted_at IS NULL
          AND trim(entity.barcode) = %(barcode)s
          {visibility_clause}
        ORDER BY entity.id
        LIMIT 1;
    """
    return _execute_query(connection, query, params, commit=False)


def get_all_catalog(
    connection,
    search: str = None,
    category: str = None,
    favorite: bool = None,
    users_id: int = None,
    viewer_user_id: int = None,
) -> list:
    """Gets all catalog items with optional filters."""
    conditions = []
    params = {}

    if viewer_user_id is None:
        conditions.append("entity.deleted_at IS NULL")
    else:
        params["catalog_viewer_user_id"] = viewer_user_id
        conditions.append(
            "(entity.deleted_at IS NULL OR (entity.is_private = FALSE AND entity.created_by <> %(catalog_viewer_user_id)s))"
        )

    normalized = (search or "").strip()
    if normalized:
        name_condition, name_params, _ = _build_fuzzy_search(
            connection, "name", normalized, param_prefix="catalog_name"
        )
        brand_condition, brand_params, _ = _build_fuzzy_search(
            connection, "COALESCE(fb.label, '')", normalized, param_prefix="catalog_brand"
        )
        conditions.append(f"({name_condition} OR {brand_condition})")
        params.update(name_params)
        params.update(brand_params)
    if category:
        conditions.append("entity.category = %(category)s")
        params["category"] = category
    _add_entity_filters(
        conditions,
        params,
        owner_column="created_by",
        users_id=users_id,
        favorite_condition=(
            _favorite_filter_sql("catalog_id", favorite, params, viewer_user_id)
            if favorite is not None
            else None
        ),
        viewer_user_id=viewer_user_id,
    )
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params["favorite_viewer_id"] = viewer_user_id
    query = f"SELECT entity.*, fb.label AS brand, EXISTS (SELECT 1 FROM user_favorites uf WHERE uf.user_id = %(favorite_viewer_id)s AND uf.catalog_id = entity.id) AS favorite FROM catalog entity LEFT JOIN food_brands fb ON fb.id = entity.brand_id {where_clause} ORDER BY entity.name;"
    
    return _execute_query_many(connection, query, params, commit=False)


def catalog_name_brand_exists(
    connection,
    name: str,
    brand_id: int | None = None,
    exclude_id: int | None = None,
) -> bool:
    normalized_name = " ".join((name or "").strip().split())
    if not normalized_name:
        return False
    params = {
        "name": normalized_name,
        "brand_id": brand_id,
    }
    exclusion = ""
    if exclude_id is not None:
        params["exclude_id"] = exclude_id
        exclusion = "AND id <> %(exclude_id)s"
    query = f"""
        SELECT 1
        FROM catalog
        WHERE deleted_at IS NULL
          AND lower(btrim(name)) = lower(btrim(%(name)s))
          AND COALESCE(brand_id, 0) = COALESCE(%(brand_id)s, 0)
          {exclusion}
        LIMIT 1;
    """
    row = _execute_query(connection, query, params, commit=False)
    return row is not None


def update_catalog_item(connection, catalog_id: int, data: dict, commit: bool = True) -> bool:
    """Updates a catalog item."""
    if not data:
        return False

    payload = dict(data or {})
    payload.pop("favorite", None)
    # brand_id llega ya resuelto desde la ruta
    params = {**payload, "id": catalog_id}
    null_fields = {
        field
        for field in _NULLABLE_CATALOG_FIELDS
        if field in payload and payload[field] is None
    }
    query = _build_update_query(
        "catalog",
        params,
        raw_fields={"updated_at": RawSQL.NOW},
        null_fields=null_fields,
    )
    if not query:
        return False

    result = _execute_query(connection, query, params, commit=commit, rollback_on_error=commit)
    return result is not None


def delete_catalog_item(connection, catalog_id: int, commit: bool = True) -> bool:
    """Logically deletes a catalog item by ID."""
    query = """
        UPDATE catalog
        SET deleted_at = NOW(),
            updated_at = NOW()
        WHERE id = %(id)s
          AND deleted_at IS NULL
        RETURNING id;
    """
    result = _execute_query(
        connection, query, {"id": catalog_id}, commit=commit, rollback_on_error=commit
    )
    return result is not None
