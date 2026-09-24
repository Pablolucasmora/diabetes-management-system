"""Queries para la tabla `meal_type_schedule` (§1.3.1 de code_conventions.md).

Franjas horarias personalizadas por usuario para el meal_type automático de
`intake_event` (decisión 2026-09-11, domain/meal_type_schedule.py). Solo
existen filas para el meal_type que el usuario ha personalizado; el default
de los demás vive en código (`DEFAULT_MEAL_TYPE_WINDOWS`), no en la base.
"""

from datetime import time

from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many
from DayBetes_food.domain.constants import MealType
from DayBetes_food.domain.meal_type_schedule import AUTO_ASSIGNABLE_MEAL_TYPES
from DayBetes_food.errors import ValidationError


def get_meal_type_schedule(connection, user_id: int) -> dict[MealType, tuple[time, time]]:
    """
    Franjas que el usuario ha personalizado. Un meal_type ausente del dict
    devuelto usa el default de código
    (`domain.meal_type_schedule.DEFAULT_MEAL_TYPE_WINDOWS`); esta función no
    conoce esos defaults, solo lee lo que hay persistido (§1.3, un CRUD no
    decide reglas de negocio).
    """
    query = """
        SELECT meal_type, start_time, end_time
        FROM meal_type_schedule
        WHERE users_id = %(user_id)s;
    """
    rows = _execute_query_many(connection, query, {"user_id": user_id}, commit=False)
    overrides: dict[MealType, tuple[time, time]] = {}
    for row in rows:
        try:
            meal_type = MealType(row["meal_type"])
        except ValueError:
            continue
        overrides[meal_type] = (row["start_time"], row["end_time"])
    return overrides


def upsert_meal_type_window(
    connection,
    user_id: int,
    meal_type: MealType,
    start_time: time,
    end_time: time,
    commit: bool = True,
) -> bool:
    """
    Crea o reemplaza la franja personalizada de un meal_type para un usuario.

    `meal_type` fuera de `AUTO_ASSIGNABLE_MEAL_TYPES` o `start_time ==
    end_time` (franja degenerada, no cubriría ninguna hora) se rechazan aquí
    con `ValidationError` en vez de dejar que el `CHECK` de la base lo
    traduzca en un error de infraestructura (§7.1: validar antes de tocar la
    base cuando la regla no depende de su estado).
    """
    if meal_type not in AUTO_ASSIGNABLE_MEAL_TYPES:
        raise ValidationError("meal_type_not_auto_assignable")
    if start_time == end_time:
        raise ValidationError("meal_type_window_degenerate")
    query = """
        INSERT INTO meal_type_schedule (users_id, meal_type, start_time, end_time)
        VALUES (%(user_id)s, %(meal_type)s, %(start_time)s, %(end_time)s)
        ON CONFLICT (users_id, meal_type) DO UPDATE SET
            start_time = EXCLUDED.start_time,
            end_time = EXCLUDED.end_time,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id;
    """
    row = _execute_query(
        connection,
        query,
        {
            "user_id": user_id,
            "meal_type": meal_type.value,
            "start_time": start_time,
            "end_time": end_time,
        },
        commit=commit,
    )
    return row is not None


def delete_meal_type_window(connection, user_id: int, meal_type: MealType, commit: bool = True) -> bool:
    """Borra la franja personalizada: el meal_type vuelve a usar el default de código."""
    query = """
        DELETE FROM meal_type_schedule
        WHERE users_id = %(user_id)s AND meal_type = %(meal_type)s
        RETURNING id;
    """
    row = _execute_query(
        connection,
        query,
        {"user_id": user_id, "meal_type": meal_type.value},
        commit=commit,
    )
    return row is not None
