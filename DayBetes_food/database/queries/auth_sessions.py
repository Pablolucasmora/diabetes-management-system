from datetime import datetime

from psycopg.errors import UniqueViolation

from DayBetes_food.auth.models import (
    AuthSessionCreated,
    AuthSessionRead,
    CreateAuthSessionCommand,
    auth_session_read_from_row,
)
from DayBetes_food.errors import ConflictError, InfrastructureError


def create_auth_session(
    connection,
    command: CreateAuthSessionCommand,
    commit: bool = True,
) -> AuthSessionCreated:
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
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {
                    "user_id": command.user_id,
                    "session_token_hash": command.session_token_hash,
                    "csrf_token_hash": command.csrf_token_hash,
                    "ip_hash": command.ip_hash,
                    "user_agent_hash": command.user_agent_hash,
                    "created_at": command.created_at,
                    "last_seen_at": command.last_seen_at,
                    "expires_at": command.expires_at,
                },
            )
            row = cursor.fetchone()
        if row is None:
            raise InfrastructureError("Auth session INSERT returned no row")
        if commit:
            connection.commit()
        return AuthSessionCreated(id=int(row["id"]), expires_at=row["expires_at"])
    except UniqueViolation as exc:
        if commit:
            connection.rollback()
        raise ConflictError("Could not create authentication session") from exc
    except Exception:
        # Caller-owned (commit=False): se propaga la excepción tal cual,
        # sin traducir. Clasificarla como InfrastructureError es
        # responsabilidad de quien posee la operación (auth/service.py o
        # el coordinador de la transacción compuesta), no del CRUD.
        if commit:
            connection.rollback()
        raise


def get_auth_session_with_user(
    connection,
    session_token_hash: str,
) -> AuthSessionRead | None:
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
        WHERE s.session_token_hash = %(session_token_hash)s
        LIMIT 1;
    """
    with connection.cursor() as cursor:
        cursor.execute(query, {"session_token_hash": session_token_hash})
        row = cursor.fetchone()
    return auth_session_read_from_row(row) if row else None


def refresh_auth_session(
    connection,
    session_id: int,
    now: datetime,
    expires_at: datetime,
    commit: bool = True,
) -> bool:
    query = """
        UPDATE auth_sessions
        SET last_seen_at = %(now)s,
            expires_at = %(expires_at)s
        WHERE id = %(id)s
          AND revoked_at IS NULL
          AND expires_at > CURRENT_TIMESTAMP
          AND EXISTS (
              SELECT 1
              FROM users
              WHERE users.id = auth_sessions.user_id
                AND users.is_active = TRUE
          )
        RETURNING id;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                {"id": session_id, "now": now, "expires_at": expires_at},
            )
            refreshed = cursor.fetchone() is not None
        if commit:
            connection.commit()
        return refreshed
    except Exception:
        if commit:
            connection.rollback()
        raise


def revoke_auth_session(
    connection,
    session_token_hash: str,
    commit: bool = True,
) -> bool:
    query = """
        UPDATE auth_sessions
        SET revoked_at = NOW()
        WHERE session_token_hash = %(session_token_hash)s
          AND revoked_at IS NULL;
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, {"session_token_hash": session_token_hash})
            revoked = cursor.rowcount > 0
        if commit:
            connection.commit()
        return revoked
    except Exception:
        if commit:
            connection.rollback()
        raise


def purge_auth_sessions(
    connection,
    retention_seconds: int,
    commit: bool = True,
) -> int:
    query = """
        DELETE FROM auth_sessions
        WHERE (
            revoked_at IS NOT NULL
            AND revoked_at <= CURRENT_TIMESTAMP - (%(retention_seconds)s * INTERVAL '1 second')
        )
        OR (
            revoked_at IS NULL
            AND expires_at <= CURRENT_TIMESTAMP - (%(retention_seconds)s * INTERVAL '1 second')
        );
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, {"retention_seconds": retention_seconds})
            deleted = cursor.rowcount
        if commit:
            connection.commit()
        return deleted
    except Exception:
        if commit:
            connection.rollback()
        raise
