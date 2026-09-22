"""Queries para la tabla `users`."""

from typing import Optional

from DayBetes_food.database.queries.crud import _execute_query, _execute_query_many


def get_users_by_email(connection, email: str) -> Optional[dict]:
    """Gets a users by email."""
    query = "SELECT * FROM users WHERE email = %(email)s;"
    return _execute_query(connection, query, {"email": email}, commit=False)


def get_all_users(connection) -> list:
    """Gets all users."""
    query = "SELECT * FROM users ORDER BY created_at DESC;"
    return _execute_query_many(connection, query, commit=False)

def update_password_hash(connection, user_id: int, new_hash: str, commit: bool = True) -> None:
    try:
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s",
                (new_hash, user_id),
            )
        if commit:
            connection.commit()
    except Exception:
        if commit:
            connection.rollback()
        raise
