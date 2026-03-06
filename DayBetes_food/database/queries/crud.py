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

All functions follow the same pattern:
- Input validation
- Query execution with parameters
- Transaction handling (commit/rollback)
- Return ID or result, or None on error
"""

import os
import re
from typing import Optional, Any

from DayBetes_food.auth.context import get_current_user_id

DEFAULT_USER_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "default@daybetes.local")
TRGM_SIMILARITY_THRESHOLD = 0.25
_HAS_PG_TRGM = None


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


def _build_update_query(table: str, params: dict, where_field: str = "id") -> Optional[str]:
    """
    Builds a generic and safe UPDATE query.
    Automatically filters the WHERE field to not update it in the SET
    and discards None values to avoid accidentally overwriting with NULL.
    
    Args:
        table: Table name
        params: Dictionary with all fields and values
        where_field: Field for WHERE (default: "id")
    
    Returns:
        Generated SQL query, or None if there are no valid fields to update.
    """
    fields = [k for k, v in params.items() if k != where_field and v is not None]
    
    if not fields:
        return None
        
    set_clause = ", ".join([f"{field} = %({field})s" for field in fields])
    return f"UPDATE {table} SET {set_clause} WHERE {where_field} = %({where_field})s RETURNING {where_field};"


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


def _add_fuzzy_name_condition(connection, conditions: list, params: dict, column: str, search: Optional[str]) -> None:
    normalized = (search or "").strip()
    if not normalized:
        return
    normalized_lower = normalized.lower()
    compact_search = re.sub(r"(.)\1+", r"\1", normalized_lower)
    if _pg_trgm_enabled(connection):
        conditions.append(
            f"({column} ILIKE %(search_like)s "
            f"OR lower({column}) %% %(search_norm)s "
            f"OR similarity(lower({column}), %(search_norm)s) >= %(search_threshold)s "
            f"OR regexp_replace(lower({column}), '(.)\\1+', '\\1', 'g') ILIKE %(search_compact_like)s)"
        )
        params["search_norm"] = normalized_lower
        params["search_threshold"] = TRGM_SIMILARITY_THRESHOLD
    else:
        conditions.append(
            f"({column} ILIKE %(search_like)s "
            f"OR regexp_replace(lower({column}), '(.)\\1+', '\\1', 'g') ILIKE %(search_compact_like)s)"
        )
    params["search_like"] = f"%{normalized}%"
    params["search_compact_like"] = f"%{compact_search}%"


# ============================================
# users
# ============================================


def get_users_by_email(connection, email: str) -> Optional[dict]:
    """Gets a users by email."""
    query = "SELECT * FROM users WHERE email = %(email)s;"
    return _execute_query(connection, query, {"email": email}, commit=False)


def get_all_users(connection) -> list:
    """Gets all users."""
    query = "SELECT * FROM users ORDER BY created_at DESC;"
    return _execute_query_many(connection, query, commit=False)


def get_default_user_id(connection) -> Optional[int]:
    """Gets current authenticated user id, falling back to default user for compatibility."""
    current_user_id = get_current_user_id()
    if current_user_id:
        return current_user_id

    user = get_users_by_email(connection, DEFAULT_USER_EMAIL)
    if user:
        return user["id"]

    users = get_all_users(connection)
    if users:
        return users[0]["id"]

    return None


# ============================================
# CATALOG
# ============================================

def add_food_brand(connection, brand_name: str) -> bool:
    clean_name = (brand_name or "").strip()
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
    normalized = (search or "").strip()
    params = {
        "q": normalized,
        "q_like": f"%{normalized}%",
        "q_prefix": f"{normalized.lower()}%",
        "q_lower": normalized.lower(),
        "limit": max(1, min(int(limit or 8), 25)),
    }
    query = """
        WITH source AS (
            SELECT DISTINCT trim(brand) AS name
            FROM catalog
            WHERE brand IS NOT NULL AND trim(brand) <> ''
            UNION
            SELECT DISTINCT trim(name) AS name
            FROM food_brands
            WHERE name IS NOT NULL AND trim(name) <> ''
        )
        SELECT name
        FROM source
        WHERE (%(q)s = '' OR name ILIKE %(q_like)s)
        ORDER BY
            CASE
                WHEN lower(name) = %(q_lower)s THEN 0
                WHEN lower(name) LIKE %(q_prefix)s THEN 1
                ELSE 2
            END,
            name
        LIMIT %(limit)s;
    """
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def get_subtype_suggestions(connection, search: str = "", limit: int = 50) -> list[str]:
    normalized = (search or "").strip()
    params = {
        "q": normalized,
        "q_like": f"%{normalized}%",
        "q_prefix": f"{normalized.lower()}%",
        "q_lower": normalized.lower(),
        "limit": max(1, min(int(limit or 50), 500)),
    }
    query = """
        WITH source AS (
            SELECT DISTINCT trim(subtype) AS name
            FROM catalog
            WHERE subtype IS NOT NULL AND trim(subtype) <> ''
            UNION
            SELECT DISTINCT trim(subtype) AS name
            FROM manual_intake
            WHERE subtype IS NOT NULL AND trim(subtype) <> ''
        )
        SELECT name
        FROM source
        WHERE (%(q)s = '' OR name ILIKE %(q_like)s)
        ORDER BY
            CASE
                WHEN lower(name) = %(q_lower)s THEN 0
                WHEN lower(name) LIKE %(q_prefix)s THEN 1
                ELSE 2
            END,
            name
        LIMIT %(limit)s;
    """
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def get_manual_origin_suggestions(connection, search: str = "", limit: int = 50) -> list[str]:
    normalized = (search or "").strip()
    params = {
        "q": normalized,
        "q_like": f"%{normalized}%",
        "q_prefix": f"{normalized.lower()}%",
        "q_lower": normalized.lower(),
        "limit": max(1, min(int(limit or 50), 500)),
    }
    query = """
        SELECT DISTINCT trim(origin) AS name
        FROM manual_intake
        WHERE origin IS NOT NULL
          AND trim(origin) <> ''
          AND (%(q)s = '' OR origin ILIKE %(q_like)s)
        ORDER BY
            CASE
                WHEN lower(trim(origin)) = %(q_lower)s THEN 0
                WHEN lower(trim(origin)) LIKE %(q_prefix)s THEN 1
                ELSE 2
            END,
            trim(origin)
        LIMIT %(limit)s;
    """
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def add_catalog_item(connection, data: dict) -> Optional[int]:
    """
    Adds a new item to the catalog.
    data: dict with the food item fields
    """
    query = """
        INSERT INTO catalog (
            created_by, name, brand, category, subtype, initial_state,
            nutriscore, nova, yuka, default_portion,
            calories_100g, carbs_100g, sugars_100g, fats_100g,
            saturated_100g, proteins_100g, fiber_100g,
            caffeine, alcohol, barcode, cooking_factor, favorite
        )
        VALUES (
            %(created_by)s, %(name)s, %(brand)s, %(category)s, %(subtype)s, %(initial_state)s,
            %(nutriscore)s, %(nova)s, %(yuka)s, %(default_portion)s,
            %(calories_100g)s, %(carbs_100g)s, %(sugars_100g)s, %(fats_100g)s,
            %(saturated_100g)s, %(proteins_100g)s, %(fiber_100g)s,
            %(caffeine)s, %(alcohol)s, %(barcode)s, %(cooking_factor)s, %(favorite)s
        )
        RETURNING id;
    """
    result = _execute_query(connection, query, data)
    return result["id"] if result else None


def get_catalog_item(connection, catalog_id: int) -> Optional[dict]:
    """Gets a catalog item by ID."""
    query = "SELECT * FROM catalog WHERE id = %(id)s;"
    return _execute_query(connection, query, {"id": catalog_id}, commit=False)


def get_all_catalog(connection, search: str = None, category: str = None, favorite: bool = None) -> list:
    """Gets all catalog items with optional filters."""
    conditions = []
    params = {}
    
    _add_fuzzy_name_condition(connection, conditions, params, "name", search)
    if category:
        conditions.append("category = %(category)s")
        params["category"] = category
    if favorite is not None:
        conditions.append("favorite = %(favorite)s")
        params["favorite"] = favorite
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM catalog {where_clause} ORDER BY name;"
    
    return _execute_query_many(connection, query, params, commit=False)


def update_catalog_favorite(connection, catalog_id: int, favorite: bool) -> bool:
    """Updates the favorite status of a catalog item."""
    query = "UPDATE catalog SET favorite = %(favorite)s WHERE id = %(id)s RETURNING id;"
    result = _execute_query(connection, query, {"id": catalog_id, "favorite": favorite})
    return result is not None


def update_catalog_item(connection, catalog_id: int, data: dict) -> bool:
    """Updates a catalog item."""
    if not data:
        return False

    params = {**data, "id": catalog_id}
    query = _build_update_query("catalog", params)
    if not query:
        return False

    result = _execute_query(connection, query, params)
    return result is not None


# ============================================
# MANUAL INTAKE
# ============================================

def add_manual_intake(connection, data: dict) -> Optional[int]:
    """Adds a new manual intake."""
    query = """
        INSERT INTO manual_intake (
            created_by, name, description, subtype, origin,
            amount_g, calories_100g, carbs_100g, sugars_100g,
            fats_100g, saturated_100g, proteins_100g, fiber_100g,
            caffeine, alcohol, glycemic_index, ig_confidence, favorite
        )
        VALUES (
            %(created_by)s, %(name)s, %(description)s, %(subtype)s, %(origin)s,
            %(amount_g)s, %(calories_100g)s, %(carbs_100g)s, %(sugars_100g)s,
            %(fats_100g)s, %(saturated_100g)s, %(proteins_100g)s, %(fiber_100g)s,
            %(caffeine)s, %(alcohol)s, %(glycemic_index)s, %(ig_confidence)s, %(favorite)s
        )
        RETURNING id;
    """
    result = _execute_query(connection, query, data)
    return result["id"] if result else None


def get_manual_intake(connection, intake_id: int) -> Optional[dict]:
    """Gets a manual intake by ID."""
    query = "SELECT * FROM manual_intake WHERE id = %(id)s;"
    return _execute_query(connection, query, {"id": intake_id}, commit=False)


def get_all_manual_intakes(connection, users_id: int = None, search: str = None, favorite: bool = None) -> list:
    """Gets all manual intakes with optional filters."""
    conditions = []
    params = {}
    
    if users_id:
        conditions.append("created_by = %(users_id)s")
        params["users_id"] = users_id
    _add_fuzzy_name_condition(connection, conditions, params, "name", search)
    if favorite is not None:
        conditions.append("favorite = %(favorite)s")
        params["favorite"] = favorite
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM manual_intake {where_clause} ORDER BY name;"
    
    return _execute_query_many(connection, query, params, commit=False)


def update_manual_intake(connection, intake_id: int, data: dict) -> bool:
    """Updates a manual intake."""
    if not data:
        return False
    
    params = {**data, "id": intake_id}
    query = _build_update_query("manual_intake", params)
    
    if not query:
        return False
        
    result = _execute_query(connection, query, params)
    return result is not None


# ============================================
# RECIPES
# ============================================

def add_recipe(connection, users_id: int, name: str, meal_type: str = None, notes: str = None, favorite: bool = False) -> Optional[int]:
    """Creates a new recipe."""
    query = """
        INSERT INTO recipe (users_id, meal_type, name, notes, favorite)
        VALUES (%(users_id)s, %(meal_type)s, %(name)s, %(notes)s, %(favorite)s)
        RETURNING id;
    """
    result = _execute_query(connection, query, {
        "users_id": users_id,
        "meal_type": meal_type,
        "name": name,
        "notes": notes,
        "favorite": favorite
    })
    return result["id"] if result else None


def get_recipe(connection, recipe_id: int) -> Optional[dict]:
    """Gets a recipe by ID."""
    query = "SELECT * FROM recipe WHERE id = %(id)s;"
    return _execute_query(connection, query, {"id": recipe_id}, commit=False)


def get_all_recipes(connection, users_id: int = None, meal_type: str = None, favorite: bool = None, search: str = None) -> list:
    """Gets all recipes with optional filters."""
    conditions = []
    params = {}
    
    if users_id:
        conditions.append("users_id = %(users_id)s")
        params["users_id"] = users_id
    if meal_type:
        conditions.append("meal_type = %(meal_type)s")
        params["meal_type"] = meal_type
    _add_fuzzy_name_condition(connection, conditions, params, "name", search)
    if favorite is not None:
        conditions.append("favorite = %(favorite)s")
        params["favorite"] = favorite
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM recipe {where_clause} ORDER BY name;"
    
    return _execute_query_many(connection, query, params, commit=False)


def update_recipe(connection, recipe_id: int, name: str = None, meal_type: str = None, notes: str = None, favorite: bool = None) -> bool:
    """Updates a recipe."""
    params = {
        "id": recipe_id, 
        "name": name, 
        "meal_type": meal_type, 
        "notes": notes, 
        "favorite": favorite
    }
    
    query = _build_update_query("recipe", params)
    
    if not query:
        return False
        
    result = _execute_query(connection, query, params)
    return result is not None


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


# ============================================
# PORTION DETAIL
# ============================================

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
    offset_minutes: int = None
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
        "offset_minutes": offset_minutes
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
            c.carbs_100g as catalog_carbs_100g,
            c.sugars_100g as catalog_sugars_100g,
            c.fats_100g as catalog_fats_100g,
            c.saturated_100g as catalog_saturated_100g,
            c.proteins_100g as catalog_proteins_100g,
            c.fiber_100g as catalog_fiber_100g,
            im.name as manual_intake_name,
            im.subtype as manual_subtype,
            im.amount_g as manual_amount_g,
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
            c.carbs_100g as catalog_carbs_100g,
            c.sugars_100g as catalog_sugars_100g,
            c.fats_100g as catalog_fats_100g,
            c.saturated_100g as catalog_saturated_100g,
            c.proteins_100g as catalog_proteins_100g,
            c.fiber_100g as catalog_fiber_100g,
            im.name as manual_intake_name,
            im.subtype as manual_subtype,
            im.amount_g as manual_amount_g,
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
