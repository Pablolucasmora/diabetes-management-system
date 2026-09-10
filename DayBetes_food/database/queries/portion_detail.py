"""Queries para la tabla `portion_detail`."""

from typing import Any, Optional

from DayBetes_food.database.queries.crud import _build_update_query, _execute_query, _execute_query_many, logger


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
    commit: bool = True,
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
    if plate_amount is None:
        plate_amount = amount_g
    if plate_amount < 0:
        raise ValueError("plate_amount must be non-negative")

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
    
    result = _execute_query(connection, query, data, commit=commit, rollback_on_error=commit)
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


def delete_event_portion_group(connection, event_id: int, origin: str, origin_id: int, commit: bool = True) -> bool:
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
        if commit:
            connection.commit()
        return deleted == len(ids)
    except Exception as e:
        if commit:
            connection.rollback()
            logger.error("Error in query: %s", e, exc_info=True)
            return False
        raise


def consolidate_event_portion_group_amount(
    connection,
    event_id: int,
    origin: str,
    origin_id: int,
    total_amount: float,
    commit: bool = True,
) -> bool:
    """Consolidates group rows into one row and sets the total amount."""
    rows = get_event_portion_rows_by_origin(connection, event_id, origin, origin_id)
    if not rows:
        return False

    keep_id = int(rows[0]["id"])
    delete_ids = [int(row["id"]) for row in rows[1:]]
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE portion_detail
                SET amount_g = %(amount)s,
                    plate_amount = %(amount)s
                WHERE id = %(id)s;
                """,
                {"amount": total_amount, "id": keep_id},
            )
            if cursor.rowcount != 1:
                if commit:
                    connection.rollback()
                return False

            if delete_ids:
                cursor.execute(
                    "DELETE FROM portion_detail WHERE id = ANY(%(ids)s);",
                    {"ids": delete_ids},
                )
                if cursor.rowcount != len(delete_ids):
                    if commit:
                        connection.rollback()
                    return False
        if commit:
            connection.commit()
        return True
    except Exception as e:
        if commit:
            connection.rollback()
            logger.error("Error in query: %s", e, exc_info=True)
            return False
        raise


def scale_event_portion_amounts(
    connection,
    event_id: int,
    fraction: float,
    commit: bool = True,
) -> bool:
    """Escala plate_amount de todas las porciones de un evento por `fraction`.

    Único punto de escritura del flujo de `confirm` (measurement_conventions.md
    §4.4/§6.9.1, decisión 2026-09-10): sobrescribe, una sola vez y con una única
    sentencia SQL (no en un bucle Python), la cantidad servida por la cantidad
    realmente consumida. `amount_g` no se toca.

    `fraction` debe estar en [0, 1]; se valida aquí también como defensa en
    profundidad, aunque el boundary HTTP ya lo rechaza con 422 antes de llegar.

    Devuelve True si había al menos una fila (evento con porciones). Un evento
    sin porciones no es un error: no hay nada que escalar.
    """
    if not (0.0 <= fraction <= 1.0):
        raise ValueError("fraction must be between 0 and 1")

    query = """
        UPDATE portion_detail
        SET plate_amount = plate_amount * %(fraction)s
        WHERE intake_event_id = %(event_id)s;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, {"fraction": fraction, "event_id": event_id})
            updated = cursor.rowcount
        if commit:
            connection.commit()
        return updated > 0
    except Exception as e:
        if commit:
            connection.rollback()
            logger.error("Error in query: %s", e, exc_info=True)
            return False
        raise


def update_event_portion_group_field(
    connection,
    event_id: int,
    origin: str,
    origin_id: int,
    field_name: str,
    field_value: Any,
    commit: bool = True,
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
        if commit:
            connection.commit()
        return updated > 0
    except Exception as e:
        if commit:
            connection.rollback()
            logger.error("Error in query: %s", e, exc_info=True)
            return False
        raise


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


def update_portion_detail_amount(connection, portion_id: int, amount_g: float, commit: bool = True) -> bool:
    """Updates amount_g for a portion_detail row."""
    if amount_g <= 0:
        raise ValueError("amount_g must be positive")
    query = "UPDATE portion_detail SET amount_g = %(amount_g)s WHERE id = %(id)s RETURNING id;"
    result = _execute_query(
        connection,
        query,
        {"id": portion_id, "amount_g": amount_g},
        commit=commit,
        rollback_on_error=commit,
    )
    return result is not None


def update_portion_detail_fields(
    connection,
    portion_id: int,
    cooking: str = None,
    conservation: str = None,
    final_state: str = None,
    strictly_weighed: bool = None,
    macros_quality: bool = None,
    commit: bool = True,
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
    result = _execute_query(connection, query, params, commit=commit, rollback_on_error=commit)
    return result is not None


def delete_portion_detail(connection, portion_id: int, commit: bool = True) -> bool:
    """Deletes one portion_detail row by id."""
    query = "DELETE FROM portion_detail WHERE id = %(id)s RETURNING id;"
    result = _execute_query(
        connection, query, {"id": portion_id}, commit=commit, rollback_on_error=commit
    )
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
