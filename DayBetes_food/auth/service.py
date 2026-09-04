from datetime import datetime, timedelta, timezone
from typing import Optional

from psycopg.errors import UniqueViolation

from DayBetes_food.config import (
    AUTH_RATE_LIMIT_ATTEMPTS,
    AUTH_RATE_LIMIT_BLOCK_SECONDS,
    AUTH_RATE_LIMIT_WINDOW_SECONDS,
    SESSION_RETENTION_SECONDS,
    SESSION_TTL_SECONDS,
)
from DayBetes_food.auth.models import (
    AuthSessionCreated,
    CreateUserCommand,
    UserAuthRead,
    UserRead,
    AuthSessionRead,
    CreateAuthSessionCommand,
    user_auth_read_from_row,
    user_read_from_row,
)
from DayBetes_food.auth.security import hash_token, normalize_identifier
from DayBetes_food.errors import AppError, ConflictError, InfrastructureError
from DayBetes_food.database.queries.auth_sessions import (
    create_auth_session,
    get_auth_session_with_user as query_get_auth_session_with_user,
    purge_auth_sessions,
    refresh_auth_session,
    revoke_auth_session,
)
from DayBetes_food.database.queries.auth_rate_limits import (
    delete_auth_rate_limit,
    get_auth_rate_limit,
    upsert_auth_rate_limit,
)


GENERIC_AUTH_ERROR = "Credenciales no validas"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
        WHERE lower(btrim(email)) = %(identifier)s
           OR lower(btrim(username)) = %(identifier)s
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


def create_session(
    connection,
    user_id: int,
    session_token: str,
    csrf_token: str,
    ip_hash: str,
    user_agent_hash: str,
    commit: bool = True,
) -> AuthSessionCreated:
    now = _utcnow()
    expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)
    command = CreateAuthSessionCommand(
        user_id=user_id,
        session_token_hash=hash_token(session_token),
        csrf_token_hash=hash_token(csrf_token),
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
        created_at=now,
        last_seen_at=now,
        expires_at=expires_at,
    )
    try:
        return create_auth_session(connection, command, commit=commit)
    except AppError:
        raise
    except Exception as exc:
        # Solo se traduce a InfrastructureError cuando este servicio es
        # dueño de la operación (commit=True). En modo caller-owned se
        # propaga tal cual para que decida el coordinador de la
        # transacción compuesta.
        if not commit:
            raise
        raise InfrastructureError("Could not create authentication session") from exc


def revoke_session(connection, session_token: str, commit: bool = True) -> bool:
    try:
        return revoke_auth_session(connection, hash_token(session_token), commit=commit)
    except AppError:
        raise
    except Exception as exc:
        if not commit:
            raise
        raise InfrastructureError("Could not revoke authentication session") from exc


def get_session_with_user(connection, session_token: str) -> Optional[AuthSessionRead]:
    session_row = query_get_auth_session_with_user(connection, hash_token(session_token))
    if session_row is None:
        return None
    now = _utcnow()
    if (
        session_row.revoked_at is not None
        or session_row.expires_at <= now
        or not session_row.is_active
    ):
        return None
    return session_row


def refresh_session(connection, session_id: int, commit: bool = True) -> bool:
    now = _utcnow()
    expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)
    try:
        return refresh_auth_session(
            connection,
            session_id,
            now,
            expires_at,
            commit=commit,
        )
    except AppError:
        raise
    except Exception as exc:
        if not commit:
            raise
        raise InfrastructureError("Could not refresh authentication session") from exc


def purge_expired_sessions(connection, commit: bool = True) -> int:
    try:
        return purge_auth_sessions(
            connection,
            SESSION_RETENTION_SECONDS,
            commit=commit,
        )
    except AppError:
        raise
    except Exception as exc:
        if not commit:
            raise
        raise InfrastructureError("Could not purge expired sessions") from exc


def is_csrf_valid(session_row: Optional[AuthSessionRead], csrf_token: str) -> bool:
    if not csrf_token:
        return False
    token_hash = hash_token(csrf_token)
    if session_row is None:
        return True
    return token_hash == session_row.csrf_token_hash


def rate_limit_login_allowed(connection, limiter_key_hash: str, commit: bool = True) -> bool:
    now = _utcnow()
    row = get_auth_rate_limit(connection, limiter_key_hash)
    allowed = not (row and row["blocked_until"] and row["blocked_until"] > now)
    if commit:
        connection.commit()
    return allowed


def register_login_failure(connection, limiter_key_hash: str, commit: bool = True) -> None:
    now = _utcnow()
    row = get_auth_rate_limit(connection, limiter_key_hash)
    if not row:
        upsert_auth_rate_limit(connection, limiter_key_hash, 1, now, None, commit=False)
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

    upsert_auth_rate_limit(connection, limiter_key_hash, attempts, first_attempt_at, blocked_until, commit=False)
    if commit:
        connection.commit()


def clear_login_failures(connection, limiter_key_hash: str, commit: bool = True) -> None:
    delete_auth_rate_limit(connection, limiter_key_hash, commit=commit)
