"""Queries for the `users` table."""


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
