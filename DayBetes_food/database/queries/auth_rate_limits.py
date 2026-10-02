"""Queries for auth_rate_limits (login attempt throttling)."""

from datetime import datetime
from typing import Optional


def get_auth_rate_limit(connection, key_hash: str) -> Optional[dict]:
    """Read a key's attempt counter, locking the row.

    It must run on the same connection/transaction as the later write
    (upsert_auth_rate_limit or delete_auth_rate_limit), as required by
    code_conventions.md §6.8 (SELECT ... FOR UPDATE).
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT key_hash, attempts, first_attempt_at, blocked_until
            FROM auth_rate_limits
            WHERE key_hash = %(key)s
            FOR UPDATE;
            """,
            {"key": key_hash},
        )
        return cursor.fetchone()


def upsert_auth_rate_limit(
    connection,
    key_hash: str,
    attempts: int,
    first_attempt_at: datetime,
    blocked_until: Optional[datetime],
    commit: bool = True,
) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO auth_rate_limits (key_hash, attempts, first_attempt_at, blocked_until)
                VALUES (%(key_hash)s, %(attempts)s, %(first_attempt_at)s, %(blocked_until)s)
                ON CONFLICT (key_hash)
                DO UPDATE SET attempts = EXCLUDED.attempts,
                              first_attempt_at = EXCLUDED.first_attempt_at,
                              blocked_until = EXCLUDED.blocked_until;
                """,
                {
                    "key_hash": key_hash,
                    "attempts": attempts,
                    "first_attempt_at": first_attempt_at,
                    "blocked_until": blocked_until,
                },
            )
        if commit:
            connection.commit()
    except Exception:
        # Caller-owned (commit=False): propagated as is; translating it to
        # InfrastructureError is the responsibility of whoever owns the
        # operation (auth/service.py or the transaction coordinator).
        if commit:
            connection.rollback()
        raise


def delete_auth_rate_limit(connection, key_hash: str, commit: bool = True) -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM auth_rate_limits WHERE key_hash = %(key)s;",
                {"key": key_hash},
            )
            deleted = cursor.rowcount > 0
        if commit:
            connection.commit()
        return deleted
    except Exception:
        if commit:
            connection.rollback()
        raise
