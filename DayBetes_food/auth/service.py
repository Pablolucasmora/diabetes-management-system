from datetime import datetime, timedelta
from typing import Optional

from psycopg.errors import UniqueViolation

from DayBetes_food.config import (
    AUTH_RATE_LIMIT_ATTEMPTS,
    AUTH_RATE_LIMIT_BLOCK_SECONDS,
    AUTH_RATE_LIMIT_WINDOW_SECONDS,
    SESSION_TTL_SECONDS,
)
from DayBetes_food.auth.models import (
    CreateUserCommand,
    UserAuthRead,
    UserRead,
    user_auth_read_from_row,
    user_read_from_row,
)
from DayBetes_food.auth.security import hash_token, normalize_identifier
from DayBetes_food.errors import ConflictError, InfrastructureError


GENERIC_AUTH_ERROR = "Credenciales no validas"


def _utcnow() -> datetime:
    return datetime.utcnow()


def create_user(connection, command: CreateUserCommand, commit: bool = True) -> int:
    query = """
        INSERT INTO users (email, username, password_hash, is_active, created_at, updated_at)
        VALUES (%(email)s, %(username)s, %(password_hash)s, TRUE, NOW(), NOW())
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, {
                "email": command.email,
                "username": command.username,
                "password_hash": command.password_hash,
            })
            user = cursor.fetchone()
        if commit:
            connection.commit()
        if not user:
            raise InfrastructureError("User INSERT returned no identifier")
        return int(user["id"])
    except UniqueViolation as exc:
        if commit:
            connection.rollback()
        raise ConflictError("User email or username already exists") from exc
    except InfrastructureError:
        if commit:
            connection.rollback()
        raise
    except Exception as exc:
        if commit:
            connection.rollback()
        raise InfrastructureError("Could not create user") from exc


def get_user_by_identifier(connection, identifier: str) -> Optional[UserAuthRead]:
    normalized = normalize_identifier(identifier)
    query = """
        SELECT id, email, username, password_hash, is_active
        FROM users
        WHERE lower(email) = %(identifier)s OR lower(username) = %(identifier)s
        LIMIT 1;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"identifier": normalized})
        row = cursor.fetchone()
    return user_auth_read_from_row(row) if row else None


def get_user_by_id(connection, user_id: int) -> Optional[UserRead]:
    query = """
        SELECT id, email, username, is_active
        FROM users
        WHERE id = %(id)s
        LIMIT 1;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"id": user_id})
        row = cursor.fetchone()
    return user_read_from_row(row) if row else None


def touch_user_login(connection, user_id: int, commit: bool = True) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE users SET last_login_at = NOW(), updated_at = NOW() WHERE id = %(id)s;",
            {"id": user_id},
        )
    if commit:
        connection.commit()


def create_session(connection, user_id: int, session_token: str, csrf_token: str, ip_hash: str, user_agent_hash: str, commit: bool = True):
    now = _utcnow()
    expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)
    query = """
        INSERT INTO auth_sessions (
            user_id, session_token_hash, csrf_token_hash,
            ip_hash, user_agent_hash,
            created_at, last_seen_at, expires_at
        )
        VALUES (
            %(user_id)s, %(session_token_hash)s, %(csrf_token_hash)s,
            %(ip_hash)s, %(user_agent_hash)s,
            %(created_at)s, %(last_seen_at)s, %(expires_at)s
        )
        RETURNING id, expires_at;
    """
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            {
                "user_id": user_id,
                "session_token_hash": hash_token(session_token),
                "csrf_token_hash": hash_token(csrf_token),
                "ip_hash": ip_hash,
                "user_agent_hash": user_agent_hash,
                "created_at": now,
                "last_seen_at": now,
                "expires_at": expires_at,
            },
        )
        row = cursor.fetchone()
    if commit:
        connection.commit()
    return row


def revoke_session(connection, session_token: str, commit: bool = True) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = NOW()
            WHERE session_token_hash = %(token_hash)s AND revoked_at IS NULL;
            """,
            {"token_hash": hash_token(session_token)},
        )
    if commit:
        connection.commit()


def get_session_with_user(connection, session_token: str) -> Optional[dict]:
    token_hash = hash_token(session_token)
    query = """
        SELECT
            s.id,
            s.user_id,
            s.csrf_token_hash,
            s.expires_at,
            s.revoked_at,
            s.last_seen_at,
            u.email,
            u.username,
            u.is_active
        FROM auth_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.session_token_hash = %(token_hash)s
        LIMIT 1;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"token_hash": token_hash})
        row = cursor.fetchone()
    if not row:
        return None
    now = _utcnow()
    if row["revoked_at"] is not None or row["expires_at"] <= now or not row["is_active"]:
        return None
    return row


def refresh_session(connection, session_id: int, commit: bool = True) -> None:
    now = _utcnow()
    expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE auth_sessions
            SET last_seen_at = %(now)s,
                expires_at = %(expires_at)s
            WHERE id = %(id)s;
            """,
            {"id": session_id, "now": now, "expires_at": expires_at},
        )
    if commit:
        connection.commit()


def is_csrf_valid(session_row: Optional[dict], csrf_token: str) -> bool:
    if not csrf_token:
        return False
    token_hash = hash_token(csrf_token)
    if session_row is None:
        return True
    return token_hash == session_row["csrf_token_hash"]


def _get_rate_limit(connection, key_hash: str) -> Optional[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT key_hash, attempts, first_attempt_at, blocked_until FROM auth_rate_limits WHERE key_hash = %(key)s FOR UPDATE;",
            {"key": key_hash},
        )
        return cursor.fetchone()


def _upsert_rate_limit(connection, key_hash: str, attempts: int, first_attempt_at: datetime, blocked_until: Optional[datetime]):
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


def rate_limit_login_allowed(connection, limiter_key_hash: str, commit: bool = True) -> bool:
    now = _utcnow()
    row = _get_rate_limit(connection, limiter_key_hash)
    if row and row["blocked_until"] and row["blocked_until"] > now:
        if commit:
            connection.commit()
        return False
    if commit:
        connection.commit()
    return True


def register_login_failure(connection, limiter_key_hash: str, commit: bool = True) -> None:
    now = _utcnow()
    row = _get_rate_limit(connection, limiter_key_hash)
    if not row:
        _upsert_rate_limit(connection, limiter_key_hash, 1, now, None)
        if commit:
            connection.commit()
        return

    first_attempt_at = row["first_attempt_at"]
    attempts = int(row["attempts"] or 0)
    if (now - first_attempt_at).total_seconds() > AUTH_RATE_LIMIT_WINDOW_SECONDS:
        first_attempt_at = now
        attempts = 0

    attempts += 1
    blocked_until = None
    if attempts >= AUTH_RATE_LIMIT_ATTEMPTS:
        blocked_until = now + timedelta(seconds=AUTH_RATE_LIMIT_BLOCK_SECONDS)

    _upsert_rate_limit(connection, limiter_key_hash, attempts, first_attempt_at, blocked_until)
    if commit:
        connection.commit()


def clear_login_failures(connection, limiter_key_hash: str, commit: bool = True) -> None:
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM auth_rate_limits WHERE key_hash = %(key)s;", {"key": limiter_key_hash})
    if commit:
        connection.commit()
