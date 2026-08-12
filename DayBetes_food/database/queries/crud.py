"""
Centralized queries module for all DayBetes tables.

This file contains CRUD functions (Create, Read, Update, Delete) for:
- users
- catalog
- manual_intake
- fridge
- tags
- recipe
- linked_tags
- intake_event
- portion_detail
- injection_zone

All functions follow the same pattern:
- Input validation
- Query execution with parameters
- Transaction handling (commit/rollback)
- Return ID or result, or None on error
"""

import re
from enum import Enum
from typing import Optional, Any

from psycopg import sql
from DayBetes_food.time_utils import local_today

TRGM_SIMILARITY_THRESHOLD = 0.25
APP_TIMEZONE_SQL = "Europe/Madrid"
_HAS_PG_TRGM = None
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_UPDATE_TABLES = {
    "catalog",
    "manual_intake",
    "recipe",
    "intake_event",
    "portion_detail",
}


class RawSQL(Enum):
    NOW = "NOW()"


_RAW_SQL_EXPRESSIONS = {
    RawSQL.NOW: sql.SQL("NOW()"),
}


class UnsupportedUpdateTarget(Exception):
    """Raised when a dynamic UPDATE target is not controlled by the backend."""


# ============================================
# GENERIC HELPERS
# ============================================

def _execute_query(connection, query: str, params: dict = None, commit: bool = True) -> Optional[Any]:
    """Generic helper to execute queries."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params or {})
            if commit:
                connection.commit()
            return cursor.fetchone()
    except Exception as e:
        connection.rollback()
        print(f"Error in query: {e}")
        return None


def _execute_query_many(connection, query: str, params: dict = None, commit: bool = True) -> list:
    """Generic helper to execute queries that return multiple rows."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params or {})
            if commit:
                connection.commit()
            return cursor.fetchall()
    except Exception as e:
        connection.rollback()
        print(f"Error in query: {e}")
        return []


def _validate_update_request(
    table: str,
    params: dict,
    where_field: str,
    auto_fields: dict,
    raw_fields: dict,
    null_fields: set[str],
) -> None:
    if table not in _ALLOWED_UPDATE_TABLES:
        raise UnsupportedUpdateTarget(f"Unsupported update table: {table!r}")

    identifiers = [where_field]
    identifiers.extend((params or {}).keys())
    identifiers.extend((auto_fields or {}).keys())
    identifiers.extend((raw_fields or {}).keys())
    identifiers.extend(null_fields or set())
    for field in identifiers:
        if not isinstance(field, str) or not _IDENTIFIER_RE.fullmatch(field):
            raise UnsupportedUpdateTarget(f"Invalid update identifier: {field!r}")

    if where_field not in (params or {}):
        raise UnsupportedUpdateTarget(f"Missing UPDATE key: {where_field!r}")

    groups = {
        "params": set((params or {}).keys()),
        "auto_fields": set((auto_fields or {}).keys()),
        "raw_fields": set((raw_fields or {}).keys()),
    }
    all_fields = set()
    for group_name, fields in groups.items():
        overlap = all_fields.intersection(fields)
        if overlap:
            raise UnsupportedUpdateTarget(
                f"UPDATE fields appear in multiple groups: {sorted(overlap)!r}"
            )
        all_fields.update(fields)

    for field, expression in (raw_fields or {}).items():
        if not isinstance(expression, RawSQL) or expression not in _RAW_SQL_EXPRESSIONS:
            raise UnsupportedUpdateTarget(f"Unsupported raw SQL expression for {field!r}")


def _build_update_query(
    table: str,
    params: dict,
    where_field: str = "id",
    auto_fields: dict = None,
    raw_fields: dict = None,
    null_fields: set[str] = None,
) -> Optional[sql.Composed]:
    """
    Builds a generic and safe UPDATE query.
    Automatically filters the WHERE field to not update it in the SET
    and discards None values to avoid accidentally overwriting with NULL.
    
    Args:
        table: Table name
        params: Dictionary with all fields and values
        where_field: Field for WHERE (default: "id")
        auto_fields: Fields always included in SET with normal param values
                     (e.g. {"is_active": True}). Values go as %(key)s parameters.
        raw_fields: Fields always included in SET with controlled RawSQL
                    expressions (e.g. {"updated_at": RawSQL.NOW}).
        null_fields: Fields explicitly allowed to be set to NULL when their
                     value in params is None. Fields not included here keep
                     the existing behavior and are skipped when None.
    
    Returns:
        Generated SQL query, or None if there are no valid fields to update.
    """
    params = dict(params or {})
    auto_fields = dict(auto_fields or {})
    raw_fields = dict(raw_fields or {})
    null_fields = set(null_fields or set())
    _validate_update_request(table, params, where_field, auto_fields, raw_fields, null_fields)

    for field, value in auto_fields.items():
        params[field] = value

    fields = [
        k
        for k, v in params.items()
        if k != where_field and (v is not None or k in null_fields or k in auto_fields)
    ]

    if not fields and not raw_fields:
        return None

    set_parts = [
        sql.SQL("{} = {}").format(sql.Identifier(field), sql.Placeholder(field))
        for field in fields
    ]
    set_parts.extend(
        sql.SQL("{} = {}").format(sql.Identifier(field), _RAW_SQL_EXPRESSIONS[expression])
        for field, expression in raw_fields.items()
    )
    return sql.SQL("UPDATE {} SET {} WHERE {} = {} RETURNING {};").format(
        sql.Identifier(table),
        sql.SQL(", ").join(set_parts),
        sql.Identifier(where_field),
        sql.Placeholder(where_field),
        sql.Identifier(where_field),
    )


def _pg_trgm_enabled(connection) -> bool:
    global _HAS_PG_TRGM
    if _HAS_PG_TRGM is not None:
        return _HAS_PG_TRGM
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') AS enabled;")
            row = cursor.fetchone()
            _HAS_PG_TRGM = bool(row and row.get("enabled"))
    except Exception:
        _HAS_PG_TRGM = False
    return _HAS_PG_TRGM


def _build_fuzzy_search(
    connection,
    column: str,
    search: Optional[str],
    param_prefix: str = "search",
) -> tuple[str, dict, str]:
    normalized = (search or "").strip()
    if not normalized:
        return "", {}, "1"

    normalized_lower = normalized.lower()
    compact_search = re.sub(r"(.)\1+", r"\1", normalized_lower)
    param = lambda name: f"{param_prefix}_{name}"
    params = {
        param("norm"): normalized_lower,
        param("like"): f"%{normalized}%",
        param("prefix"): f"{normalized_lower}%",
        param("compact_like"): f"%{compact_search}%",
        param("threshold"): TRGM_SIMILARITY_THRESHOLD,
    }

    if _pg_trgm_enabled(connection):
        condition = (
            f"({column} ILIKE %({param('like')})s "
            f"OR lower({column}) %% %({param('norm')})s "
            f"OR similarity(lower({column}), %({param('norm')})s) >= %({param('threshold')})s "
            f"OR regexp_replace(lower({column}), '(.)\\1+', '\\1', 'g') ILIKE %({param('compact_like')})s)"
        )
        order = (
            f"CASE "
            f"WHEN lower({column}) = %({param('norm')})s THEN 0 "
            f"WHEN lower({column}) LIKE %({param('prefix')})s THEN 1 "
            f"ELSE 2 END, "
            f"similarity(lower({column}), %({param('norm')})s) DESC, {column}"
        )
    else:
        condition = (
            f"({column} ILIKE %({param('like')})s "
            f"OR regexp_replace(lower({column}), '(.)\\1+', '\\1', 'g') ILIKE %({param('compact_like')})s)"
        )
        order = (
            f"CASE "
            f"WHEN lower({column}) = %({param('norm')})s THEN 0 "
            f"WHEN lower({column}) LIKE %({param('prefix')})s THEN 1 "
            f"ELSE 2 END, {column}"
        )

    return condition, params, order


def _add_fuzzy_name_condition(
    connection,
    conditions: list,
    params: dict,
    column: str,
    search: Optional[str],
    param_prefix: str = "search",
) -> None:
    condition, search_params, _ = _build_fuzzy_search(connection, column, search, param_prefix=param_prefix)
    if not condition:
        return
    conditions.append(condition)
    params.update(search_params)


# ============================================
# USERS
# ============================================


def get_users_by_email(connection, email: str) -> Optional[dict]:
    """Gets a users by email."""
    query = "SELECT * FROM users WHERE email = %(email)s;"
    return _execute_query(connection, query, {"email": email}, commit=False)


def get_all_users(connection) -> list:
    """Gets all users."""
    query = "SELECT * FROM users ORDER BY created_at DESC;"
    return _execute_query_many(connection, query, commit=False)

def update_password_hash(connection, user_id: int, new_hash: str) -> None:
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s",
            (new_hash, user_id),
        )


# ============================================
# CATALOG
# ============================================

_NULLABLE_CATALOG_FIELDS = {
    "brand",
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


def normalize_brand_name(brand_name: str) -> str:
    clean_name = " ".join((brand_name or "").strip().split())
    if not clean_name:
        return ""
    lowered = clean_name.lower()
    return " ".join(token[:1].upper() + token[1:] for token in lowered.split(" "))


def add_food_brand(connection, brand_name: str) -> bool:
    clean_name = normalize_brand_name(brand_name)
    if not clean_name:
        return False
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO food_brands (name)
                VALUES (%(name)s)
                ON CONFLICT (name) DO NOTHING;
                """,
                {"name": clean_name},
            )
        connection.commit()
        return True
    except Exception as e:
        connection.rollback()
        print(f"Error in query: {e}")
        return False


def get_food_brand_suggestions(connection, search: str = "", limit: int = 8) -> list[str]:
    search_condition, search_params, search_order = _build_fuzzy_search(connection, "name", search)
    params = {**search_params, "limit": max(1, min(int(limit or 8), 25))}
    query = """
        WITH source AS (
            SELECT DISTINCT trim(brand) AS name
            FROM catalog
            WHERE deleted_at IS NULL
              AND brand IS NOT NULL AND trim(brand) <> ''
            UNION
            SELECT DISTINCT trim(name) AS name
            FROM food_brands
            WHERE name IS NOT NULL AND trim(name) <> ''
        )
        SELECT name
        FROM source
        WHERE {search_condition}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """.format(search_condition=search_condition or "TRUE", search_order=search_order)
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def get_subtype_suggestions(connection, search: str = "", limit: int = 50) -> list[str]:
    search_condition, search_params, search_order = _build_fuzzy_search(connection, "name", search)
    params = {**search_params, "limit": max(1, min(int(limit or 50), 500))}
    query = """
        WITH source AS (
            SELECT DISTINCT trim(subtype) AS name
            FROM catalog
            WHERE deleted_at IS NULL
              AND subtype IS NOT NULL AND trim(subtype) <> ''
            UNION
            SELECT DISTINCT trim(subtype) AS name
            FROM manual_intake
            WHERE subtype IS NOT NULL AND trim(subtype) <> ''
        )
        SELECT name
        FROM source
        WHERE {search_condition}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """.format(search_condition=search_condition or "TRUE", search_order=search_order)
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]

def get_category_suggestions(connection, search: str = "", limit: int = 50) -> list[str]:
    search_condition, search_params, search_order = _build_fuzzy_search(connection, "name", search)
    params = {**search_params, "limit": max(1, min(int(limit or 50), 500))}
    query = """
        WITH defaults AS (
            SELECT unnest(ARRAY[
                'meat', 'fish', 'dairy', 'eggs', 'processed_meat',
                'legumes', 'tubers', 'nuts', 'vegetables', 'fruits',
                'cereals', 'oils_and_fats', 'sweets', 'beverages',
                'sauces', 'condiments', 'supplements'
            ]) AS name
        ),
        source AS (
            SELECT DISTINCT trim(category) AS name
            FROM catalog
            WHERE deleted_at IS NULL
              AND category IS NOT NULL AND trim(category) <> ''
            UNION
            SELECT name FROM defaults
        )
        SELECT name
        FROM source
        WHERE {search_condition}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """.format(search_condition=search_condition or "TRUE", search_order=search_order)
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def get_manual_origin_suggestions(connection, search: str = "", limit: int = 50) -> list[str]:
    search_condition, search_params, search_order = _build_fuzzy_search(connection, "name", search)
    params = {**search_params, "limit": max(1, min(int(limit or 50), 500))}
    query = """
        WITH source AS (
            SELECT DISTINCT trim(origin) AS name
            FROM manual_intake
            WHERE origin IS NOT NULL
              AND trim(origin) <> ''
        )
        SELECT name
        FROM source
        WHERE {search_condition}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """.format(search_condition=search_condition or "TRUE", search_order=search_order)
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def add_catalog_item(connection, data: dict) -> Optional[int]:
    """
    Adds a new item to the catalog.
    data: dict with the food item fields
    """
    query = """
        INSERT INTO catalog (
            created_by, origin_root_id, name, brand, category, subtype, initial_state,
            nutriscore, nova, yuka, default_portion,
            calories_100g, carbs_100g, sugars_100g, fats_100g,
            saturated_100g, proteins_100g, fiber_100g,
            caffeine, alcohol, barcode, cooking_factor, is_private,
            created_at, updated_at
        )
        VALUES (
            %(created_by)s, %(origin_root_id)s, %(name)s, %(brand)s, %(category)s, %(subtype)s, %(initial_state)s,
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
    if payload.get("cooking_factor") is None:
        payload["cooking_factor"] = 1.0
    if "brand" in payload:
        payload["brand"] = normalize_brand_name(payload.get("brand")) or None
    result = _execute_query(connection, query, payload)
    return result["id"] if result else None


def get_catalog_item(connection, catalog_id: int, viewer_user_id: int = None) -> Optional[dict]:
    """Gets a catalog item by ID."""
    query = """
        SELECT entity.*,
               EXISTS (
                   SELECT 1 FROM user_favorites uf
                   WHERE uf.user_id = %(viewer_user_id)s
                     AND uf.catalog_id = entity.id
               ) AS favorite
        FROM catalog entity
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
        SELECT entity.*,
               EXISTS (
                   SELECT 1 FROM user_favorites uf
                   WHERE uf.user_id = %(viewer_user_id)s
                     AND uf.catalog_id = entity.id
               ) AS favorite
        FROM catalog entity
        WHERE entity.deleted_at IS NULL
          AND trim(entity.barcode) = %(barcode)s
          {visibility_clause}
        ORDER BY entity.id
        LIMIT 1;
    """
    return _execute_query(connection, query, params, commit=False)


def _add_entity_filters(
    conditions: list,
    params: dict,
    owner_column: str,
    users_id: int = None,
    favorite_condition: str = None,
    viewer_user_id: int = None,
) -> None:
    if users_id:
        conditions.append(f"{owner_column} = %(users_id)s")
        params["users_id"] = users_id
    if favorite_condition:
        conditions.append(favorite_condition)
    if viewer_user_id is not None:
        conditions.append(f"(is_private = FALSE OR {owner_column} = %(viewer_user_id)s)")
        params["viewer_user_id"] = viewer_user_id


def _favorite_filter_sql(target_column: str, favorite: bool, params: dict, viewer_user_id: int = None) -> str:
    params["favorite_filter_user_id"] = viewer_user_id
    operator = "EXISTS" if favorite else "NOT EXISTS"
    return (
        f"{operator} ("
        "SELECT 1 FROM user_favorites uf "
        f"WHERE uf.user_id = %(favorite_filter_user_id)s AND uf.{target_column} = entity.id"
        ")"
    )


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
        conditions.append("deleted_at IS NULL")
    else:
        params["catalog_viewer_user_id"] = viewer_user_id
        conditions.append(
            "(deleted_at IS NULL OR (is_private = FALSE AND created_by <> %(catalog_viewer_user_id)s))"
        )

    normalized = (search or "").strip()
    if normalized:
        name_condition, name_params, _ = _build_fuzzy_search(
            connection, "name", normalized, param_prefix="catalog_name"
        )
        brand_condition, brand_params, _ = _build_fuzzy_search(
            connection, "COALESCE(brand, '')", normalized, param_prefix="catalog_brand"
        )
        conditions.append(f"({name_condition} OR {brand_condition})")
        params.update(name_params)
        params.update(brand_params)
    if category:
        conditions.append("category = %(category)s")
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
    query = f"SELECT entity.*, EXISTS (SELECT 1 FROM user_favorites uf WHERE uf.user_id = %(favorite_viewer_id)s AND uf.catalog_id = entity.id) AS favorite FROM catalog entity {where_clause} ORDER BY entity.name;"
    
    return _execute_query_many(connection, query, params, commit=False)


def catalog_name_brand_exists(
    connection,
    name: str,
    brand: str | None = None,
    exclude_id: int | None = None,
) -> bool:
    normalized_name = " ".join((name or "").strip().split())
    normalized_brand = normalize_brand_name(brand or "")
    if not normalized_name:
        return False
    params = {
        "name": normalized_name,
        "brand": normalized_brand,
    }
    exclusion = ""
    if exclude_id is not None:
        params["exclude_id"] = exclude_id
        exclusion = "AND id <> %(exclude_id)s"
    query = f"""
        SELECT 1
        FROM catalog
        WHERE deleted_at IS NULL
          AND lower(trim(name)) = lower(trim(%(name)s))
          AND lower(trim(COALESCE(brand, ''))) = lower(trim(COALESCE(%(brand)s, '')))
          {exclusion}
        LIMIT 1;
    """
    row = _execute_query(connection, query, params, commit=False)
    return row is not None


def update_catalog_item(connection, catalog_id: int, data: dict) -> bool:
    """Updates a catalog item."""
    if not data:
        return False

    payload = dict(data or {})
    payload.pop("favorite", None)
    if "brand" in payload:
        payload["brand"] = normalize_brand_name(payload.get("brand")) or None
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

    result = _execute_query(connection, query, params)
    return result is not None


def delete_catalog_item(connection, catalog_id: int) -> bool:
    """Logically deletes a catalog item by ID."""
    query = """
        UPDATE catalog
        SET deleted_at = NOW(),
            updated_at = NOW()
        WHERE id = %(id)s
          AND deleted_at IS NULL
        RETURNING id;
    """
    result = _execute_query(connection, query, {"id": catalog_id})
    return result is not None


_FAVORITE_ENTRY_COLUMNS = {
    "catalog": "catalog_id",
    "manual_intake": "manual_intake_id",
    "recipe": "recipe_id",
}


def toggle_user_favorite(connection, user_id: int, entry_type: str, entry_id: int) -> bool | None:
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
    )
    return bool(row["favorite"]) if row else None


def set_user_favorite(connection, user_id: int, entry_type: str, entry_id: int, favorite: bool) -> bool:
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
        connection.commit()
        return True
    except Exception as e:
        connection.rollback()
        print(f"Error in query: {e}")
        return False




# ============================================
# MANUAL INTAKE
# ============================================

def add_manual_intake(connection, data: dict) -> Optional[int]:
    """Adds a new manual intake."""
    query = """
        INSERT INTO manual_intake (
            created_by, origin_root_id, name, description, subtype, origin,
            amount_g, calories_100g, carbs_100g, sugars_100g,
            fats_100g, saturated_100g, proteins_100g, fiber_100g,
            caffeine, alcohol, glycemic_index, ig_confidence, is_private
        )
        VALUES (
            %(created_by)s, %(origin_root_id)s, %(name)s, %(description)s, %(subtype)s, %(origin)s,
            %(amount_g)s, %(calories_100g)s, %(carbs_100g)s, %(sugars_100g)s,
            %(fats_100g)s, %(saturated_100g)s, %(proteins_100g)s, %(fiber_100g)s,
            %(caffeine)s, %(alcohol)s, %(glycemic_index)s, %(ig_confidence)s, %(is_private)s
        )
        RETURNING id;
    """
    payload = dict(data or {})
    payload.setdefault("origin_root_id", None)
    result = _execute_query(connection, query, payload)
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
        WHERE entity.id = %(id)s;
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
          AND lower(trim(name)) = lower(trim(%(name)s))
          AND lower(trim(COALESCE(origin, ''))) = lower(trim(COALESCE(%(origin)s, '')))
          {exclusion}
        LIMIT 1;
    """
    row = _execute_query(connection, query, params, commit=False)
    return row is not None


def update_manual_intake(connection, intake_id: int, data: dict) -> bool:
    """Updates a manual intake."""
    if not data:
        return False
    
    payload = dict(data or {})
    payload.pop("favorite", None)
    params = {**payload, "id": intake_id}
    query = _build_update_query("manual_intake", params)
    
    if not query:
        return False
        
    result = _execute_query(connection, query, params)
    return result is not None


def delete_manual_intake(connection, intake_id: int) -> bool:
    """Deletes a manual intake by ID."""
    query = "DELETE FROM manual_intake WHERE id = %(id)s RETURNING id;"
    result = _execute_query(connection, query, {"id": intake_id})
    return result is not None




# ============================================
# RECIPES
# ============================================

def add_recipe(
    connection,
    users_id: int,
    name: str,
    meal_type: str = None,
    notes: str = None,
    favorite: bool = False,
    is_private: bool = False,
    origin_root_id: int = None,
) -> Optional[int]:
    """Creates a new recipe."""
    query = """
        INSERT INTO recipe (users_id, origin_root_id, meal_type, name, notes, is_private)
        VALUES (%(users_id)s, %(origin_root_id)s, %(meal_type)s, %(name)s, %(notes)s, %(is_private)s)
        RETURNING id;
    """
    result = _execute_query(connection, query, {
        "users_id": users_id,
        "origin_root_id": origin_root_id,
        "meal_type": meal_type,
        "name": name,
        "notes": notes,
        "is_private": is_private,
    })
    return result["id"] if result else None


def get_recipe(connection, recipe_id: int, viewer_user_id: int = None) -> Optional[dict]:
    """Gets a recipe by ID."""
    query = """
        SELECT entity.*,
               EXISTS (
                   SELECT 1 FROM user_favorites uf
                   WHERE uf.user_id = %(viewer_user_id)s
                     AND uf.recipe_id = entity.id
               ) AS favorite
        FROM recipe entity
        WHERE entity.id = %(id)s;
    """
    return _execute_query(
        connection,
        query,
        {"id": recipe_id, "viewer_user_id": viewer_user_id},
        commit=False,
    )


def get_all_recipes(
    connection,
    users_id: int = None,
    meal_type: str = None,
    favorite: bool = None,
    search: str = None,
    viewer_user_id: int = None,
) -> list:
    """Gets all recipes with optional filters."""
    conditions = []
    params = {}
    
    if meal_type:
        conditions.append("meal_type = %(meal_type)s")
        params["meal_type"] = meal_type
    _add_fuzzy_name_condition(connection, conditions, params, "name", search)
    _add_entity_filters(
        conditions,
        params,
        owner_column="users_id",
        users_id=users_id,
        favorite_condition=(
            _favorite_filter_sql("recipe_id", favorite, params, viewer_user_id)
            if favorite is not None
            else None
        ),
        viewer_user_id=viewer_user_id,
    )
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params["favorite_viewer_id"] = viewer_user_id
    query = f"SELECT entity.*, EXISTS (SELECT 1 FROM user_favorites uf WHERE uf.user_id = %(favorite_viewer_id)s AND uf.recipe_id = entity.id) AS favorite FROM recipe entity {where_clause} ORDER BY entity.name;"
    
    return _execute_query_many(connection, query, params, commit=False)


def update_recipe(
    connection,
    recipe_id: int,
    name: str = None,
    meal_type: str = None,
    notes: str = None,
    favorite: bool = None,
    is_private: bool = None,
) -> bool:
    """Updates a recipe."""
    params = {
        "id": recipe_id, 
        "name": name, 
        "meal_type": meal_type, 
        "notes": notes, 
        "is_private": is_private,
    }
    
    query = _build_update_query("recipe", params)
    
    if not query:
        return False
        
    result = _execute_query(connection, query, params)
    return result is not None


def delete_recipe(connection, recipe_id: int) -> bool:
    """Deletes a recipe by ID."""
    query = "DELETE FROM recipe WHERE id = %(id)s RETURNING id;"
    result = _execute_query(connection, query, {"id": recipe_id})
    return result is not None


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


def get_rescue_entries_suggestions(connection, users_id: int, search: str = "", limit: int = 50) -> list[dict]:
    normalized = (search or "").strip()
    params = {
        "users_id": users_id,
        "q": normalized,
        "q_like": f"%{normalized}%",
        "limit": max(1, min(int(limit or 50), 200)),
    }
    query = """
        WITH rescue_tag AS (
            SELECT id
            FROM tags
            WHERE lower(trim(name)) = 'rescate'
            LIMIT 1
        ),
        catalog_rows AS (
            SELECT
                'catalog'::text AS entry_type,
                c.id AS entry_id,
                c.name AS name,
                COALESCE(c.brand, '') AS subtitle,
                COALESCE(c.default_portion, 100.0) AS serving_g,
                NULL::double precision AS available_g
            FROM linked_tags lt
            INNER JOIN rescue_tag rt ON rt.id = lt.tag_id
            INNER JOIN catalog c ON c.id = lt.catalog_id
            WHERE c.deleted_at IS NULL
              AND (c.is_private = FALSE OR c.created_by = %(users_id)s)
              AND (%(q)s = '' OR c.name ILIKE %(q_like)s OR COALESCE(c.brand, '') ILIKE %(q_like)s)
        ),
        manual_rows AS (
            SELECT
                'manual_intake'::text AS entry_type,
                m.id AS entry_id,
                m.name AS name,
                COALESCE(m.origin, '') AS subtitle,
                COALESCE(m.amount_g, 100.0) AS serving_g,
                COALESCE(m.amount_g, 0.0) AS available_g
            FROM linked_tags lt
            INNER JOIN rescue_tag rt ON rt.id = lt.tag_id
            INNER JOIN manual_intake m ON m.id = lt.manual_intake_id
            WHERE (m.is_private = FALSE OR m.created_by = %(users_id)s)
              AND (%(q)s = '' OR m.name ILIKE %(q_like)s OR COALESCE(m.origin, '') ILIKE %(q_like)s)
        )
        SELECT *
        FROM (
            SELECT * FROM catalog_rows
            UNION ALL
            SELECT * FROM manual_rows
        ) src
        ORDER BY name ASC, entry_type ASC, entry_id ASC
        LIMIT %(limit)s;
    """
    rows = _execute_query_many(connection, query, params, commit=False)
    out = []
    for row in rows:
        if not row:
            continue
        out.append(
            {
                "entry_type": str(row.get("entry_type") or ""),
                "entry_id": int(row.get("entry_id") or 0),
                "name": str(row.get("name") or "").strip(),
                "subtitle": str(row.get("subtitle") or "").strip(),
                "serving_g": float(row.get("serving_g") or 100.0),
                "available_g": (float(row.get("available_g")) if row.get("available_g") is not None else None),
            }
        )
    return out


def _normalize_tag_name(tag: str) -> str:
    return " ".join((tag or "").strip().split())


def _tag_color_from_name(tag_name: str) -> str:
    text = _normalize_tag_name(tag_name).lower()
    hue = 0
    for ch in text:
        hue = (hue * 31 + ord(ch)) % 360
    return f"hsl({hue} 80% 90%)"


def ensure_tag(connection, tag_name: str) -> Optional[int]:
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
    row = _execute_query(connection, query, {"name": clean, "color": _tag_color_from_name(clean)})
    return int(row["id"]) if row and row.get("id") is not None else None


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


def set_entry_tags(connection, entry_type: str, entry_id: int, tag_names: list[str]) -> bool:
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
        connection.commit()
        return True
    except Exception as e:
        connection.rollback()
        print(f"Error in query: {e}")
        return False


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


def update_tag(connection, tag_id: int, name: str, color: str) -> bool:
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
    row = _execute_query(connection, query, {"id": tag_id, "name": clean_name, "color": clean_color})
    return row is not None


def get_consumed_food_usage_rankings(connection, users_id: int, days: int = 60) -> list[dict]:
    """Gets personalized food rankings weighted by frequency and time-of-day proximity."""
    safe_days = max(1, int(days or 60))
    query = """
        WITH base AS (
            SELECT
                pd.catalog_id,
                pd.manual_intake_id,
                (
                    EXTRACT(HOUR FROM (ie.meal_time AT TIME ZONE 'UTC' AT TIME ZONE %(app_timezone)s)) * 60
                    + EXTRACT(MINUTE FROM (ie.meal_time AT TIME ZONE 'UTC' AT TIME ZONE %(app_timezone)s))
                )::int AS event_minute,
                (
                    EXTRACT(HOUR FROM (CURRENT_TIMESTAMP AT TIME ZONE %(app_timezone)s)) * 60
                    + EXTRACT(MINUTE FROM (CURRENT_TIMESTAMP AT TIME ZONE %(app_timezone)s))
                )::int AS now_minute
            FROM portion_detail pd
            INNER JOIN intake_event ie ON ie.id = pd.intake_event_id
            WHERE ie.users_id = %(users_id)s
              AND ie.state = 'consumed'
              AND ie.meal_time >= (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') - (%(days)s * INTERVAL '1 day')
        ),
        scored AS (
            SELECT
                catalog_id,
                manual_intake_id,
                LEAST(
                    ABS(event_minute - now_minute),
                    1440 - ABS(event_minute - now_minute)
                )::numeric AS minute_distance
            FROM base
        ),
        catalog_rank AS (
            SELECT
                'catalog'::text AS entry_type,
                catalog_id AS entry_id,
                COUNT(*)::int AS usage_count,
                AVG(minute_distance) AS avg_minute_distance,
                SUM(1.0 / (1.0 + (minute_distance / 60.0))) AS proximity_score
            FROM scored
            WHERE catalog_id IS NOT NULL
            GROUP BY catalog_id
        ),
        manual_rank AS (
            SELECT
                'manual_intake'::text AS entry_type,
                manual_intake_id AS entry_id,
                COUNT(*)::int AS usage_count,
                AVG(minute_distance) AS avg_minute_distance,
                SUM(1.0 / (1.0 + (minute_distance / 60.0))) AS proximity_score
            FROM scored
            WHERE manual_intake_id IS NOT NULL
            GROUP BY manual_intake_id
        ),
        combined AS (
            SELECT * FROM catalog_rank
            UNION ALL
            SELECT * FROM manual_rank
        )
        SELECT
            entry_type,
            entry_id,
            usage_count,
            avg_minute_distance,
            proximity_score,
            (usage_count * 100.0 + proximity_score * 10.0) AS rank_score
        FROM combined
        ORDER BY
            rank_score DESC,
            usage_count DESC,
            avg_minute_distance ASC,
            entry_type ASC,
            entry_id ASC;
    """
    return _execute_query_many(
        connection,
        query,
        {"users_id": users_id, "days": safe_days, "app_timezone": APP_TIMEZONE_SQL},
        commit=False,
    )




# ============================================
# INTAKE EVENT
# ============================================

def add_intake_event(connection, users_id: int, state: str, meal_type: str = None, name: str = None,
                       meal_time=None, eating_out: bool = False, insulin_dose: bool = True,
                       total_amount: float = None, ingested_amount: float = None,
                       amount_confidence: float = None, quality_confidence: float = None,
                       notes: str = None, **kwargs) -> Optional[int]:
    """Creates a new intake event."""

    data = {
        "users_id": users_id,
        "state": state,
        "eating_out": eating_out,
        "insulin_dose": insulin_dose,
    }

    optional = {
        "meal_type": meal_type,
        "name": name,
        "meal_time": meal_time,
        "total_amount": total_amount,
        "ingested_amount": ingested_amount,
        "amount_confidence": amount_confidence,
        "quality_confidence": quality_confidence,
        "notes": notes,
        "carbs_uncertainty": kwargs.get("carbs_uncertainty"),
        "sugars_uncertainty": kwargs.get("sugars_uncertainty"),
        "fats_uncertainty": kwargs.get("fats_uncertainty"),
        "saturated_uncertainty": kwargs.get("saturated_uncertainty"),
        "proteins_uncertainty": kwargs.get("proteins_uncertainty"),
        "fiber_uncertainty": kwargs.get("fiber_uncertainty"),
    }

    data.update({k: v for k, v in optional.items() if v is not None})

    columns = ", ".join(data.keys())
    values = ", ".join(f"%({k})s" for k in data.keys())

    query = f"""
        INSERT INTO intake_event ({columns})
        VALUES ({values})
        RETURNING id;
    """

    result = _execute_query(connection, query, data)
    return result["id"] if result else None

def get_intake_event(connection, event_id: int) -> Optional[dict]:
    """Gets an intake event by ID."""
    query = "SELECT * FROM intake_event WHERE id = %(id)s;"
    return _execute_query(connection, query, {"id": event_id}, commit=False)


def get_cart_events(connection, users_id: int) -> list:
    """Gets the events in 'planned' state (cart) for a users."""
    query = """
        SELECT * FROM intake_event 
        WHERE users_id = %(users_id)s AND state = 'planned' 
        ORDER BY meal_time DESC;
    """
    return _execute_query_many(connection, query, {"users_id": users_id}, commit=False)


def get_consumed_events_for_day(connection, users_id: int, day=None) -> list:
    """Gets events in 'consumed' state for a specific calendar day."""
    if day is None:
        day = local_today()
    query = """
        SELECT *
        FROM intake_event
        WHERE users_id = %(users_id)s
          AND state = 'consumed'
          AND DATE((meal_time AT TIME ZONE 'UTC' AT TIME ZONE %(app_timezone)s)) = %(day)s
        ORDER BY meal_time ASC, id ASC;
    """
    return _execute_query_many(
        connection,
        query,
        {"users_id": users_id, "day": day, "app_timezone": APP_TIMEZONE_SQL},
        commit=False,
    )


def get_consumed_events(connection, users_id: int) -> list:
    """Gets all events in 'consumed' state for a users."""
    query = """
        SELECT *
        FROM intake_event
        WHERE users_id = %(users_id)s
          AND state = 'consumed'
        ORDER BY meal_time ASC, id ASC;
    """
    return _execute_query_many(connection, query, {"users_id": users_id}, commit=False)


def update_intake_event(connection, event_id: int, data: dict) -> bool:
    """Updates an intake event."""
    if not data:
        return False
    
    params = {**data, "id": event_id}
    query = _build_update_query("intake_event", params)
    
    if not query:
        return False
        
    result = _execute_query(connection, query, params)
    return result is not None


def change_event_status(connection, event_id: int, new_state: str) -> bool:
    """Changes the status of an intake event (planned -> consumed)."""
    if new_state not in ("planned", "consumed"):
        raise ValueError("Invalid state. Must be 'planned' or 'consumed'")
    
    query = "UPDATE intake_event SET state = %(state)s WHERE id = %(id)s RETURNING id;"
    result = _execute_query(connection, query, {"id": event_id, "state": new_state})
    return result is not None


def delete_intake_event(connection, event_id: int) -> bool:
    """Deletes an intake event."""
    query = "DELETE FROM intake_event WHERE id = %(id)s RETURNING id;"
    result = _execute_query(connection, query, {"id": event_id})
    return result is not None


def update_intake_event_name(connection, event_id: int, name: Optional[str]) -> bool:
    """Updates intake event name."""
    query = """
        UPDATE intake_event
        SET name = %(name)s
        WHERE id = %(id)s
        RETURNING id;
    """
    result = _execute_query(connection, query, {"id": event_id, "name": name})
    return result is not None


# ============================================
# INJECTION ZONE
# ============================================

VALID_INJECTION_ZONES = {
    "right_arm",
    "left_arm",
    "right_thigh",
    "left_thigh",
    "abdomen",
    "right_gluteus",
    "left_gluteus",
}


def set_injection_zone(connection, intake_event_id: int, zone: str) -> bool:
    clean_zone = (zone or "").strip()
    if clean_zone not in VALID_INJECTION_ZONES:
        return False
    query = """
        UPDATE intake_event
        SET injection_zone = %(zone)s
        WHERE id = %(intake_event_id)s
        RETURNING id;
    """
    result = _execute_query(
        connection,
        query,
        {"intake_event_id": intake_event_id, "zone": clean_zone},
    )
    return result is not None


def get_latest_injection_zone_for_event(connection, intake_event_id: int) -> Optional[str]:
    query = """
        SELECT injection_zone
        FROM intake_event
        WHERE id = %(intake_event_id)s
        LIMIT 1;
    """
    row = _execute_query(connection, query, {"intake_event_id": intake_event_id}, commit=False)
    return row.get("injection_zone") if row else None


def finalize_injection_zone_for_event(connection, intake_event_id: int) -> bool:
    event = get_intake_event(connection, intake_event_id)
    if not event:
        return False
    zone = (event.get("injection_zone") or "").strip()
    if not zone or zone not in VALID_INJECTION_ZONES:
        return True
    if not bool(event.get("insulin_dose")):
        return True
    shot_time = event.get("meal_time")
    cleanup = _execute_query(
        connection,
        "DELETE FROM insulin_injections WHERE intake_event_id = %(intake_event_id)s RETURNING id;",
        {"intake_event_id": intake_event_id},
    )
    _ = cleanup
    insert_query = """
        INSERT INTO insulin_injections (users_id, intake_event_id, shot_time, insulin_type, basal_units, injection_zone)
        VALUES (%(users_id)s, %(intake_event_id)s, COALESCE(%(shot_time)s, CURRENT_TIMESTAMP), 'rapid', NULL, %(zone)s)
        RETURNING id;
    """
    inserted = _execute_query(
        connection,
        insert_query,
        {
            "users_id": event.get("users_id"),
            "intake_event_id": intake_event_id,
            "shot_time": shot_time,
            "zone": zone,
        },
    )
    return inserted is not None


def add_manual_injection_log(
    connection,
    users_id: int,
    insulin_type: str,
    injection_zone: str,
    basal_units: float | None = None,
    shot_time=None,
) -> bool:
    clean_type = (insulin_type or "").strip().lower()
    clean_zone = (injection_zone or "").strip()
    if clean_type not in {"rapid", "basal"}:
        return False
    if clean_zone not in VALID_INJECTION_ZONES:
        return False
    units = None
    if clean_type == "basal":
        if basal_units is None:
            return False
        try:
            units = float(basal_units)
        except (TypeError, ValueError):
            return False
        if units <= 0:
            return False
        if abs((units * 2) - round(units * 2)) > 1e-8:
            return False
    query = """
        INSERT INTO insulin_injections (users_id, intake_event_id, shot_time, insulin_type, basal_units, injection_zone)
        VALUES (%(users_id)s, NULL, COALESCE(%(shot_time)s, CURRENT_TIMESTAMP), %(insulin_type)s, %(basal_units)s, %(injection_zone)s)
        RETURNING id;
    """
    result = _execute_query(
        connection,
        query,
        {
            "users_id": users_id,
            "insulin_type": clean_type,
            "basal_units": units,
            "injection_zone": clean_zone,
            "shot_time": shot_time,
        },
    )
    return result is not None


def get_user_injection_logs(connection, users_id: int, limit: int = 15, offset: int = 0) -> list[dict]:
    clean_limit = max(1, min(int(limit or 15), 100))
    clean_offset = max(0, int(offset or 0))
    query = """
        SELECT
            id,
            shot_time,
            insulin_type,
            basal_units,
            injection_zone
        FROM insulin_injections
        WHERE users_id = %(users_id)s
        ORDER BY shot_time DESC, id DESC
        LIMIT %(limit)s
        OFFSET %(offset)s;
    """
    return _execute_query_many(
        connection,
        query,
        {
            "users_id": users_id,
            "limit": clean_limit,
            "offset": clean_offset,
        },
        commit=False,
    )


def get_user_injection_log_prev_day(connection, users_id: int, offset: int = 0):
    clean_offset = max(0, int(offset or 0))
    if clean_offset <= 0:
        return None
    query = """
        SELECT shot_time
        FROM insulin_injections
        WHERE users_id = %(users_id)s
        ORDER BY shot_time DESC, id DESC
        LIMIT 1
        OFFSET %(offset)s;
    """
    row = _execute_query(
        connection,
        query,
        {
            "users_id": users_id,
            "offset": clean_offset - 1,
        },
        commit=False,
    )
    return row.get("shot_time") if row else None


def get_user_injection_log_by_id(connection, users_id: int, injection_id: int) -> Optional[dict]:
    query = """
        SELECT id, users_id, shot_time, insulin_type, basal_units, injection_zone
        FROM insulin_injections
        WHERE id = %(injection_id)s
          AND users_id = %(users_id)s
        LIMIT 1;
    """
    return _execute_query(
        connection,
        query,
        {
            "injection_id": injection_id,
            "users_id": users_id,
        },
        commit=False,
    )


def update_user_injection_log(
    connection,
    users_id: int,
    injection_id: int,
    insulin_type: str,
    injection_zone: str,
    shot_time,
    basal_units: float | None = None,
) -> bool:
    clean_type = (insulin_type or "").strip().lower()
    clean_zone = (injection_zone or "").strip()
    if clean_type not in {"rapid", "basal"}:
        return False
    if clean_zone not in VALID_INJECTION_ZONES:
        return False
    units = None
    if clean_type == "basal":
        if basal_units is None:
            return False
        try:
            units = float(basal_units)
        except (TypeError, ValueError):
            return False
        if units <= 0:
            return False
        if abs((units * 2) - round(units * 2)) > 1e-8:
            return False
    query = """
        UPDATE insulin_injections
        SET
            shot_time = COALESCE(%(shot_time)s, shot_time),
            insulin_type = %(insulin_type)s,
            basal_units = %(basal_units)s,
            injection_zone = %(injection_zone)s
        WHERE id = %(injection_id)s
          AND users_id = %(users_id)s
        RETURNING id;
    """
    row = _execute_query(
        connection,
        query,
        {
            "shot_time": shot_time,
            "insulin_type": clean_type,
            "basal_units": units if clean_type == "basal" else None,
            "injection_zone": clean_zone,
            "injection_id": injection_id,
            "users_id": users_id,
        },
    )
    return row is not None


def delete_user_injection_log(connection, users_id: int, injection_id: int) -> bool:
    query = """
        DELETE FROM insulin_injections
        WHERE id = %(injection_id)s
          AND users_id = %(users_id)s
        RETURNING id;
    """
    row = _execute_query(
        connection,
        query,
        {
            "injection_id": injection_id,
            "users_id": users_id,
        },
    )
    return row is not None


# ============================================
# PORTION DETAIL
# ============================================

_PORTION_ORIGIN_COLUMNS = {
    "catalog": "catalog_id",
    "manual_intake": "manual_intake_id",
}

def add_portion_detail(
    connection,
    origin: str,
    origin_id: int,
    destination: str,
    destination_id: int,
    amount_g: float,
    cooking: str = None,
    conservation: str = None,
    final_state: str = None,
    strictly_weighed: bool = None,
    macros_quality: bool = None,
    plate_amount: float = None,
    is_cooked_weight: bool = False,
    offset_minutes: int = None,
) -> Optional[int]:
    """Adds a record to portion_detail in a centralized way."""
    if origin not in ("catalog", "manual_intake"):
        raise ValueError("Invalid origin")
    if destination not in ("intake_event", "recipe", "fridge"):
        raise ValueError("Invalid destination")
    if amount_g <= 0:
        raise ValueError("amount_g must be positive")
    if offset_minutes is not None and destination != "intake_event":
        raise ValueError("offset_minutes only for intake_event")

    data = {
        "amount_g": amount_g,
        "catalog_id": origin_id if origin == "catalog" else None,
        "manual_intake_id": origin_id if origin == "manual_intake" else None,
        "intake_event_id": destination_id if destination == "intake_event" else None,
        "recipe_id": destination_id if destination == "recipe" else None,
        "fridge_id": destination_id if destination == "fridge" else None,
        "cooking": cooking,
        "conservation": conservation,
        "final_state": final_state,
        "strictly_weighed": strictly_weighed,
        "macros_quality": macros_quality,
        "plate_amount": plate_amount,
        "is_cooked_weight": is_cooked_weight,
        "offset_minutes": offset_minutes,
    }
    
    query = """
        INSERT INTO portion_detail (
            amount_g, catalog_id, manual_intake_id,
            intake_event_id, recipe_id, fridge_id,
            cooking, conservation, final_state,
            strictly_weighed, macros_quality, plate_amount,
            is_cooked_weight, offset_minutes
        )
        VALUES (
            %(amount_g)s, %(catalog_id)s, %(manual_intake_id)s,
            %(intake_event_id)s, %(recipe_id)s, %(fridge_id)s,
            %(cooking)s, %(conservation)s, %(final_state)s,
            %(strictly_weighed)s, %(macros_quality)s, %(plate_amount)s,
            %(is_cooked_weight)s, %(offset_minutes)s
        )
        RETURNING id;
    """
    
    result = _execute_query(connection, query, data)
    return result["id"] if result else None


def get_portion_detail_by_event(connection, intake_event_id: int) -> list:
    """Gets all portions for an intake event."""
    query = """
        SELECT
            pd.*,
            c.name as catalog_name,
            c.category as catalog_category,
            c.default_portion as catalog_default_portion,
            c.calories_100g as catalog_calories_100g,
            c.carbs_100g as catalog_carbs_100g,
            c.sugars_100g as catalog_sugars_100g,
            c.fats_100g as catalog_fats_100g,
            c.saturated_100g as catalog_saturated_100g,
            c.proteins_100g as catalog_proteins_100g,
            c.fiber_100g as catalog_fiber_100g,
            im.name as manual_intake_name,
            im.subtype as manual_subtype,
            im.amount_g as manual_amount_g,
            im.calories_100g as manual_calories_100g,
            im.carbs_100g as manual_carbs_100g,
            im.sugars_100g as manual_sugars_100g,
            im.fats_100g as manual_fats_100g,
            im.saturated_100g as manual_saturated_100g,
            im.proteins_100g as manual_proteins_100g,
            im.fiber_100g as manual_fiber_100g
        FROM portion_detail pd
        LEFT JOIN catalog c ON pd.catalog_id = c.id
        LEFT JOIN manual_intake im ON pd.manual_intake_id = im.id
        WHERE pd.intake_event_id = %(id)s
        ORDER BY pd.id;
    """
    return _execute_query_many(connection, query, {"id": intake_event_id}, commit=False)


def get_event_portion_rows_by_origin(connection, event_id: int, origin: str, origin_id: int) -> list:
    """Gets all portion_detail rows in an intake event matching origin and origin_id."""
    origin_field = _PORTION_ORIGIN_COLUMNS.get(origin)
    if not origin_field:
        return []
    query = f"""
        SELECT
            pd.id,
            pd.amount_g,
            c.default_portion AS catalog_default_portion,
            im.amount_g AS manual_amount_g
        FROM portion_detail pd
        LEFT JOIN catalog c ON pd.catalog_id = c.id
        LEFT JOIN manual_intake im ON pd.manual_intake_id = im.id
        WHERE pd.intake_event_id = %(event_id)s
          AND pd.{origin_field} = %(origin_id)s
        ORDER BY pd.id;
    """
    return _execute_query_many(
        connection,
        query,
        {"event_id": event_id, "origin_id": origin_id},
        commit=False,
    )


def delete_event_portion_group(connection, event_id: int, origin: str, origin_id: int) -> bool:
    """Deletes all rows in an intake event group (same origin + origin_id)."""
    rows = get_event_portion_rows_by_origin(connection, event_id, origin, origin_id)
    if not rows:
        return False
    ids = [int(row["id"]) for row in rows]
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM portion_detail WHERE id = ANY(%(ids)s);",
                {"ids": ids},
            )
            deleted = cursor.rowcount
        connection.commit()
        return deleted == len(ids)
    except Exception as e:
        connection.rollback()
        print(f"Error in query: {e}")
        return False


def consolidate_event_portion_group_amount(connection, event_id: int, origin: str, origin_id: int, total_amount: float) -> bool:
    """Consolidates group rows into one row and sets the total amount."""
    rows = get_event_portion_rows_by_origin(connection, event_id, origin, origin_id)
    if not rows:
        return False

    keep_id = int(rows[0]["id"])
    delete_ids = [int(row["id"]) for row in rows[1:]]
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE portion_detail SET amount_g = %(amount)s WHERE id = %(id)s;",
                {"amount": total_amount, "id": keep_id},
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False

            if delete_ids:
                cursor.execute(
                    "DELETE FROM portion_detail WHERE id = ANY(%(ids)s);",
                    {"ids": delete_ids},
                )
                if cursor.rowcount != len(delete_ids):
                    connection.rollback()
                    return False
        connection.commit()
        return True
    except Exception as e:
        connection.rollback()
        print(f"Error in query: {e}")
        return False


def update_event_portion_group_field(
    connection,
    event_id: int,
    origin: str,
    origin_id: int,
    field_name: str,
    field_value: Any,
) -> bool:
    """Updates a whitelisted field for all rows in an intake event group."""
    origin_field = _PORTION_ORIGIN_COLUMNS.get(origin)
    if not origin_field:
        return False

    allowed_fields = {"offset_minutes", "strictly_weighed", "macros_quality", "is_cooked_weight"}
    if field_name not in allowed_fields:
        return False

    query = f"""
        UPDATE portion_detail pd
        SET {field_name} = %(value)s
        WHERE pd.intake_event_id = %(event_id)s
          AND pd.{origin_field} = %(origin_id)s;
    """
    params = {"value": field_value, "event_id": event_id, "origin_id": origin_id}
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                params,
            )
            updated = cursor.rowcount
        connection.commit()
        return updated > 0
    except Exception as e:
        connection.rollback()
        print(f"Error in query: {e}")
        return False
def get_portion_detail_by_events(connection, intake_event_ids: list[int]) -> list:
    """Gets all portions for multiple intake events in one query."""
    if not intake_event_ids:
        return []

    query = """
        SELECT
            pd.*,
            c.name as catalog_name,
            c.category as catalog_category,
            c.default_portion as catalog_default_portion,
            c.calories_100g as catalog_calories_100g,
            c.carbs_100g as catalog_carbs_100g,
            c.sugars_100g as catalog_sugars_100g,
            c.fats_100g as catalog_fats_100g,
            c.saturated_100g as catalog_saturated_100g,
            c.proteins_100g as catalog_proteins_100g,
            c.fiber_100g as catalog_fiber_100g,
            im.name as manual_intake_name,
            im.subtype as manual_subtype,
            im.amount_g as manual_amount_g,
            im.calories_100g as manual_calories_100g,
            im.carbs_100g as manual_carbs_100g,
            im.sugars_100g as manual_sugars_100g,
            im.fats_100g as manual_fats_100g,
            im.saturated_100g as manual_saturated_100g,
            im.proteins_100g as manual_proteins_100g,
            im.fiber_100g as manual_fiber_100g
        FROM portion_detail pd
        LEFT JOIN catalog c ON pd.catalog_id = c.id
        LEFT JOIN manual_intake im ON pd.manual_intake_id = im.id
        WHERE pd.intake_event_id = ANY(%(event_ids)s)
        ORDER BY pd.intake_event_id, pd.id;
    """
    return _execute_query_many(connection, query, {"event_ids": intake_event_ids}, commit=False)


def get_portion_detail_by_recipe(connection, recipe_id: int) -> list:
    """Gets all portions for a recipe."""
    query = """
        SELECT
            pd.*,
            c.name as catalog_name,
            c.category as catalog_category,
            c.default_portion as catalog_default_portion,
            c.calories_100g as catalog_calories_100g,
            c.carbs_100g as catalog_carbs_100g,
            c.sugars_100g as catalog_sugars_100g,
            c.fats_100g as catalog_fats_100g,
            c.saturated_100g as catalog_saturated_100g,
            c.proteins_100g as catalog_proteins_100g,
            c.fiber_100g as catalog_fiber_100g,
            im.name as manual_intake_name,
            im.subtype as manual_subtype,
            im.amount_g as manual_amount_g,
            im.calories_100g as manual_calories_100g,
            im.carbs_100g as manual_carbs_100g,
            im.sugars_100g as manual_sugars_100g,
            im.fats_100g as manual_fats_100g,
            im.saturated_100g as manual_saturated_100g,
            im.proteins_100g as manual_proteins_100g,
            im.fiber_100g as manual_fiber_100g
        FROM portion_detail pd
        LEFT JOIN catalog c ON pd.catalog_id = c.id
        LEFT JOIN manual_intake im ON pd.manual_intake_id = im.id
        WHERE pd.recipe_id = %(id)s
        ORDER BY pd.id;
    """
    return _execute_query_many(connection, query, {"id": recipe_id}, commit=False)


def get_portion_detail(connection, portion_id: int) -> Optional[dict]:
    """Gets one portion detail by ID with source metadata."""
    query = """
        SELECT
            pd.*,
            c.default_portion as catalog_default_portion,
            im.amount_g as manual_amount_g
        FROM portion_detail pd
        LEFT JOIN catalog c ON pd.catalog_id = c.id
        LEFT JOIN manual_intake im ON pd.manual_intake_id = im.id
        WHERE pd.id = %(id)s;
    """
    return _execute_query(connection, query, {"id": portion_id}, commit=False)


def update_portion_detail_amount(connection, portion_id: int, amount_g: float) -> bool:
    """Updates amount_g for a portion_detail row."""
    if amount_g <= 0:
        raise ValueError("amount_g must be positive")
    query = "UPDATE portion_detail SET amount_g = %(amount_g)s WHERE id = %(id)s RETURNING id;"
    result = _execute_query(connection, query, {"id": portion_id, "amount_g": amount_g})
    return result is not None


def update_portion_detail_fields(
    connection,
    portion_id: int,
    cooking: str = None,
    conservation: str = None,
    final_state: str = None,
    strictly_weighed: bool = None,
    macros_quality: bool = None,
) -> bool:
    """Updates editable metadata fields for a portion_detail row."""
    params = {
        "id": portion_id,
        "cooking": cooking,
        "conservation": conservation,
        "final_state": final_state,
        "strictly_weighed": strictly_weighed,
        "macros_quality": macros_quality,
    }
    query = _build_update_query("portion_detail", params)
    if not query:
        return False
    result = _execute_query(connection, query, params)
    return result is not None


def delete_portion_detail(connection, portion_id: int) -> bool:
    """Deletes one portion_detail row by id."""
    query = "DELETE FROM portion_detail WHERE id = %(id)s RETURNING id;"
    result = _execute_query(connection, query, {"id": portion_id})
    return result is not None


def get_recipe_portion_by_origin(connection, recipe_id: int, origin: str, origin_id: int) -> Optional[dict]:
    """Gets first portion_detail row in recipe matching origin and origin_id."""
    if origin not in ("catalog", "manual_intake"):
        raise ValueError("Invalid origin")
    origin_field = "catalog_id" if origin == "catalog" else "manual_intake_id"
    query = f"""
        SELECT *
        FROM portion_detail
        WHERE recipe_id = %(recipe_id)s AND {origin_field} = %(origin_id)s
        ORDER BY id
        LIMIT 1;
    """
    return _execute_query(connection, query, {"recipe_id": recipe_id, "origin_id": origin_id}, commit=False)


def get_recipe_portions_by_origin(connection, recipe_id: int, origin: str, origin_id: int) -> list:
    """Gets all portion_detail rows in recipe matching origin and origin_id."""
    if origin not in ("catalog", "manual_intake"):
        raise ValueError("Invalid origin")
    origin_field = "catalog_id" if origin == "catalog" else "manual_intake_id"
    query = f"""
        SELECT *
        FROM portion_detail
        WHERE recipe_id = %(recipe_id)s AND {origin_field} = %(origin_id)s
        ORDER BY id;
    """
    return _execute_query_many(connection, query, {"recipe_id": recipe_id, "origin_id": origin_id}, commit=False)
