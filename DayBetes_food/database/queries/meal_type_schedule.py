"""Queries for the `meal_type_schedule` table (§1.3.1 of code_conventions.md).

Per-user customized time slots for the automatic meal_type of
`intake_event` (decision 2026-09-11, domain/meal_type_schedule.py). Rows
only exist for the meal_type the user has customized; the default for the
rest lives in code (`DEFAULT_MEAL_TYPE_WINDOWS`), not in the database.
"""

from datetime import time

from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many
from DayBetes_food.domain.constants import MealType
from DayBetes_food.domain.meal_type_schedule import AUTO_ASSIGNABLE_MEAL_TYPES
from DayBetes_food.errors import ValidationError


def get_meal_type_schedule(connection, user_id: int) -> dict[MealType, tuple[time, time]]:
    """
    Slots the user has customized. A meal_type missing from the returned dict
    uses the code default
    (`domain.meal_type_schedule.DEFAULT_MEAL_TYPE_WINDOWS`); this function
    does not know those defaults, it only reads what is persisted (§1.3, a
    CRUD does not decide business rules).
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
    Create or replace a user's customized slot for a meal_type.

    A `meal_type` outside `AUTO_ASSIGNABLE_MEAL_TYPES` or `start_time ==
    end_time` (degenerate slot, it would cover no hour) is rejected here with
    `ValidationError` instead of letting the database `CHECK` turn it into an
    infrastructure error (§7.1: validate before touching the database when
    the rule does not depend on its state).
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
    """Delete the customized slot: the meal_type goes back to the code default."""
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
