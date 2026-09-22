"""Queries para la tabla `portion_detail`."""

from typing import Any, Optional

from DayBetes_food.database.queries.crud import _build_update_query, _execute_query, _execute_query_many, logger
from DayBetes_food.errors import ValidationError


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
    plate_id: int = None,
    commit: bool = True,
) -> Optional[int]:
    """Adds a record to portion_detail in a centralized way.

    Para destino `intake_event`, `plate_id` es obligatorio: toda porción de un
    evento pertenece a una tanda (measurement_conventions.md §4.6.1). Si no se
    pasa `offset_minutes`, la porción **hereda** el de su tanda (§4.6.2): ese
    es el mecanismo que evita corregir el offset ingrediente a ingrediente, y
    vive aquí para no repetirlo en cada punto de inserción.

    Si la tanda ya contiene ese alimento con la misma preparación, la fila
    existente **absorbe** la cantidad nueva en vez de crearse una segunda
    (§4.6.4). En la fusión gana la fila existente: los tres booleanos de
    calidad del dato y el offset no se tocan.
    """
    if origin not in ("catalog", "manual_intake"):
        raise ValueError("Invalid origin")
    if destination not in ("intake_event", "recipe", "fridge"):
        raise ValueError("Invalid destination")
    if amount_g <= 0:
        raise ValueError("amount_g must be positive")
    if offset_minutes is not None and destination != "intake_event":
        raise ValueError("offset_minutes only for intake_event")
    if destination == "intake_event" and plate_id is None:
        raise ValueError("plate_id is required for intake_event")
    if plate_id is not None and destination != "intake_event":
        raise ValueError("plate_id only for intake_event")
    if plate_amount is None:
        plate_amount = amount_g
    if plate_amount < 0:
        raise ValueError("plate_amount must be non-negative")

    if offset_minutes is None and plate_id is not None:
        offset_minutes = _plate_offset_minutes(connection, plate_id)

    data = {
        "amount_g": amount_g,
        "catalog_id": origin_id if origin == "catalog" else None,
        "manual_intake_id": origin_id if origin == "manual_intake" else None,
        "intake_event_id": destination_id if destination == "intake_event" else None,
        "recipe_id": destination_id if destination == "recipe" else None,
        "fridge_id": destination_id if destination == "fridge" else None,
        "plate_id": plate_id,
        "cooking": cooking,
        "conservation": conservation,
        "final_state": final_state,
        "strictly_weighed": strictly_weighed,
        "macros_quality": macros_quality,
        "plate_amount": plate_amount,
        "is_cooked_weight": is_cooked_weight,
        "offset_minutes": offset_minutes,
    }

    # ON CONFLICT sobre el índice único parcial de §4.6.4: la inferencia
    # necesita repetir su WHERE para identificarlo. Las porciones de receta y
    # de nevera tienen plate_id NULL, no entran en el índice y por tanto nunca
    # fusionan: cada una sigue insertando su propia fila.
    query = """
        INSERT INTO portion_detail (
            amount_g, catalog_id, manual_intake_id,
            intake_event_id, recipe_id, fridge_id, plate_id,
            cooking, conservation, final_state,
            strictly_weighed, macros_quality, plate_amount,
            is_cooked_weight, offset_minutes
        )
        VALUES (
            %(amount_g)s, %(catalog_id)s, %(manual_intake_id)s,
            %(intake_event_id)s, %(recipe_id)s, %(fridge_id)s, %(plate_id)s,
            %(cooking)s, %(conservation)s, %(final_state)s,
            %(strictly_weighed)s, %(macros_quality)s, %(plate_amount)s,
            %(is_cooked_weight)s, %(offset_minutes)s
        )
        ON CONFLICT (plate_id, catalog_id, manual_intake_id, cooking, conservation, final_state)
        WHERE plate_id IS NOT NULL
        DO UPDATE SET
            amount_g = portion_detail.amount_g + EXCLUDED.amount_g,
            plate_amount = COALESCE(portion_detail.plate_amount, portion_detail.amount_g)
                           + EXCLUDED.plate_amount
        RETURNING id;
    """

    result = _execute_query(connection, query, data, commit=commit, rollback_on_error=commit)
    return result["id"] if result else None


def _plate_offset_minutes(connection, plate_id: int) -> Optional[int]:
    """Offset plantilla de una tanda, el que heredan sus porciones (§4.6.2)."""
    row = _execute_query(
        connection,
        "SELECT offset_minutes FROM intake_plate WHERE id = %(plate_id)s;",
        {"plate_id": plate_id},
        commit=False,
    )
    return row["offset_minutes"] if row else None


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


def get_plate_portion_rows_by_origin(connection, plate_id: int, origin: str, origin_id: int) -> list:
    """Gets all portion_detail rows in a plate matching origin and origin_id.

    La identidad del grupo es la tanda, no el evento (measurement_conventions.md
    §4.6.4): el mismo alimento en el primer plato y en el segundo son grupos
    distintos y se editan por separado.
    """
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
        WHERE pd.plate_id = %(plate_id)s
          AND pd.{origin_field} = %(origin_id)s
        ORDER BY pd.id;
    """
    return _execute_query_many(
        connection,
        query,
        {"plate_id": plate_id, "origin_id": origin_id},
        commit=False,
    )


def delete_plate_portion_group(connection, plate_id: int, origin: str, origin_id: int, commit: bool = True) -> bool:
    """Deletes all rows in a plate group (same origin + origin_id)."""
    rows = get_plate_portion_rows_by_origin(connection, plate_id, origin, origin_id)
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


def consolidate_plate_portion_group_amount(
    connection,
    plate_id: int,
    origin: str,
    origin_id: int,
    total_amount: float,
    commit: bool = True,
) -> bool:
    """Consolidates the rows of a plate group into one row and sets the total amount."""
    rows = get_plate_portion_rows_by_origin(connection, plate_id, origin, origin_id)
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
    El error de dominio es `ValidationError`, no `ValueError`, para que el
    boundary lo traduzca a `422` y no a `500` (error_conventions.md §3.2;
    hallazgo 41 de audit/audit_intake_event.md).

    La cantidad escalada es `COALESCE(plate_amount, amount_g)`, la misma
    definición que usa `cart_shared.portion_intake_amount` para calcular el
    `total_amount` del que sale la fracción: si una fila tuviera
    `plate_amount NULL`, escalar `NULL` la dejaría sin escalar mientras el
    `ingested_amount` del evento sí reflejaría la fracción (hallazgo 41).
    `amount_g` es `NOT NULL` y positivo por contrato (`add_portion_detail`),
    así que el `COALESCE` no puede producir `NULL`; una fila con `amount_g <= 0`
    sería un dato corrupto y se rechaza en vez de escalarse en silencio.

    Devuelve True si había al menos una fila (evento con porciones). Un evento
    sin porciones no es un error: no hay nada que escalar.
    """
    if not (0.0 <= fraction <= 1.0):
        raise ValidationError("fraction must be between 0 and 1")

    corrupt_query = """
        SELECT COUNT(*) AS corrupt_rows FROM portion_detail
        WHERE intake_event_id = %(event_id)s
          AND (amount_g IS NULL OR amount_g <= 0);
    """
    query = """
        UPDATE portion_detail
        SET plate_amount = COALESCE(plate_amount, amount_g) * %(fraction)s
        WHERE intake_event_id = %(event_id)s;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(corrupt_query, {"event_id": event_id})
            corrupt_row = cursor.fetchone()
            if corrupt_row and corrupt_row["corrupt_rows"]:
                raise ValidationError("portion_amount_not_positive")
            cursor.execute(query, {"fraction": fraction, "event_id": event_id})
            updated = cursor.rowcount
        if commit:
            connection.commit()
        return updated > 0
    except ValidationError:
        # Error de dominio: nunca se degrada a False (error_conventions.md §11,
        # "no ocultar errores SQL como resultados falsy"). El boundary lo
        # traduce a 422.
        if commit:
            connection.rollback()
        raise
    except Exception as e:
        if commit:
            connection.rollback()
            logger.error("Error in query: %s", e, exc_info=True)
            return False
        raise


def update_plate_portion_group_field(
    connection,
    plate_id: int,
    origin: str,
    origin_id: int,
    field_name: str,
    field_value: Any,
    commit: bool = True,
) -> bool:
    """Updates a whitelisted field for all rows in a plate group."""
    origin_field = _PORTION_ORIGIN_COLUMNS.get(origin)
    if not origin_field:
        return False

    allowed_fields = {"offset_minutes", "strictly_weighed", "macros_quality", "is_cooked_weight"}
    if field_name not in allowed_fields:
        return False

    query = f"""
        UPDATE portion_detail pd
        SET {field_name} = %(value)s
        WHERE pd.plate_id = %(plate_id)s
          AND pd.{origin_field} = %(origin_id)s;
    """
    params = {"value": field_value, "plate_id": plate_id, "origin_id": origin_id}
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


def move_portion_group_to_plate(
    connection,
    plate_id: int,
    origin: str,
    origin_id: int,
    target_plate_id: int,
    commit: bool = True,
) -> bool:
    """Mueve las filas de un grupo a otra tanda del mismo evento (§4.6.5).

    No toca `offset_minutes`: el offset que la porción heredó en su día sigue
    siendo lo que se comió, y cambiarlo es una acción aparte.

    Si la tanda destino ya contiene ese alimento con la misma preparación, las
    cantidades **se suman** en la fila que ya estaba, que es lo que exige la
    clave única de §4.6.4; en la fusión gana la fila existente, igual que al
    añadir. Las filas del grupo cuya preparación no exista en el destino se
    mueven tal cual.
    """
    origin_field = _PORTION_ORIGIN_COLUMNS.get(origin)
    if not origin_field:
        return False
    if target_plate_id == plate_id:
        return False

    # Las dos tandas deben pertenecer al mismo evento: mover una porción entre
    # comidas distintas cambiaría de evento sin pasar por su flujo (§4.6.1).
    same_event = _execute_query(
        connection,
        """
        SELECT count(DISTINCT intake_event_id) AS events
        FROM intake_plate
        WHERE id IN (%(plate_id)s, %(target_plate_id)s);
        """,
        {"plate_id": plate_id, "target_plate_id": target_plate_id},
        commit=False,
    )
    if not same_event or same_event["events"] != 1:
        raise ValidationError("plates_not_in_same_event")

    params = {"plate_id": plate_id, "target_plate_id": target_plate_id, "origin_id": origin_id}
    # Coincidencia por la clave de §4.6.4. IS NOT DISTINCT FROM es el equivalente
    # en SQL del NULLS NOT DISTINCT del índice: sin él, dos filas con cooking
    # NULL no se reconocerían como la misma preparación.
    same_preparation = f"""
        t.catalog_id IS NOT DISTINCT FROM s.catalog_id
        AND t.manual_intake_id IS NOT DISTINCT FROM s.manual_intake_id
        AND t.cooking IS NOT DISTINCT FROM s.cooking
        AND t.conservation IS NOT DISTINCT FROM s.conservation
        AND t.final_state IS NOT DISTINCT FROM s.final_state
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE portion_detail t
                SET amount_g = t.amount_g + s.amount_g,
                    plate_amount = COALESCE(t.plate_amount, t.amount_g)
                                   + COALESCE(s.plate_amount, s.amount_g)
                FROM portion_detail s
                WHERE t.plate_id = %(target_plate_id)s
                  AND s.plate_id = %(plate_id)s
                  AND s.{origin_field} = %(origin_id)s
                  AND {same_preparation};
                """,
                params,
            )
            cursor.execute(
                f"""
                DELETE FROM portion_detail s
                WHERE s.plate_id = %(plate_id)s
                  AND s.{origin_field} = %(origin_id)s
                  AND EXISTS (
                      SELECT 1 FROM portion_detail t
                      WHERE t.plate_id = %(target_plate_id)s AND {same_preparation}
                  );
                """,
                params,
            )
            merged = cursor.rowcount
            cursor.execute(
                f"""
                UPDATE portion_detail
                SET plate_id = %(target_plate_id)s
                WHERE plate_id = %(plate_id)s
                  AND {origin_field} = %(origin_id)s;
                """,
                params,
            )
            moved = cursor.rowcount
        if commit:
            connection.commit()
        # Falso solo si el grupo no existía en la tanda de origen: no se fusionó
        # ni se movió ninguna fila (§11 de error_conventions.md: el resultado
        # falsy significa "no había nada", no "falló").
        return (merged + moved) > 0
    except ValidationError:
        if commit:
            connection.rollback()
        raise
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
