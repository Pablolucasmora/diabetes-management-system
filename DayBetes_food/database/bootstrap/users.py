"""Bootstrap of users, sessions and login rate limits, and the default development user."""

import os
from psycopg import sql
from DayBetes_food.auth.models import USER_EMAIL_MAX_LENGTH, USER_USERNAME_MAX_LENGTH
from DayBetes_food.auth.security import hash_password, normalize_identifier, sanitize_text
from DayBetes_food import config
from DayBetes_food.database.bootstrap.helpers import (
    _column_data_type,
    _has_column,
)


DEFAULT_USER_EMAIL = normalize_identifier(config.DEFAULT_USER_EMAIL)
DEFAULT_USER_USERNAME = normalize_identifier(config.DEFAULT_USER_USERNAME)
DEFAULT_USER_PASSWORD = config.DEFAULT_USER_PASSWORD


def _ensure_users_schema(cursor):
    if _has_column(cursor, "users", "mail") and not _has_column(cursor, "users", "email"):
        cursor.execute("ALTER TABLE users RENAME COLUMN mail TO email;")

    if not _has_column(cursor, "users", "username"):
        cursor.execute("ALTER TABLE users ADD COLUMN username VARCHAR(50);")

    if not _has_column(cursor, "users", "password_hash"):
        cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT;")

    if not _has_column(cursor, "users", "is_active"):
        cursor.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;")

    if not _has_column(cursor, "users", "last_login_at"):
        cursor.execute("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMPTZ;")

    if not _has_column(cursor, "users", "created_at"):
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMPTZ;")

    if not _has_column(cursor, "users", "updated_at"):
        cursor.execute("ALTER TABLE users ADD COLUMN updated_at TIMESTAMPTZ;")

    if _has_column(cursor, "users", "registration_date"):
        cursor.execute("UPDATE users SET created_at = COALESCE(created_at, registration_date, CURRENT_TIMESTAMP);")
    else:
        cursor.execute("UPDATE users SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP);")
    cursor.execute("UPDATE users SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP);")

    for column in ("last_login_at", "created_at", "updated_at"):
        data_type = (_column_data_type(cursor, "users", column) or "").lower()
        if data_type == "timestamp without time zone":
            if column == "last_login_at":
                cursor.execute(
                    "ALTER TABLE users ALTER COLUMN last_login_at TYPE TIMESTAMPTZ "
                    "USING last_login_at AT TIME ZONE 'UTC';"
                )
            elif column == "created_at":
                cursor.execute(
                    "ALTER TABLE users ALTER COLUMN created_at TYPE TIMESTAMPTZ "
                    "USING created_at AT TIME ZONE 'UTC';"
                )
            else:
                cursor.execute(
                    "ALTER TABLE users ALTER COLUMN updated_at TYPE TIMESTAMPTZ "
                    "USING updated_at AT TIME ZONE 'UTC';"
                )
        elif data_type != "timestamp with time zone":
            raise RuntimeError(f"Unexpected users.{column} type: {data_type!r}")

    if _has_column(cursor, "users", "name"):
        cursor.execute(
            """
            UPDATE users
            SET username = COALESCE(
                NULLIF(username, ''),
                NULLIF(left(lower(regexp_replace(name, '[^a-zA-Z0-9_]+', '_', 'g')), 50), ''),
                left(split_part(lower(email), '@', 1), 50)
            )
            WHERE username IS NULL OR username = '';
            """
        )
    else:
        cursor.execute(
            """
            UPDATE users
            SET username = COALESCE(
                NULLIF(username, ''),
                left(split_part(lower(email), '@', 1), 50)
            )
            WHERE username IS NULL OR username = '';
            """
        )

    cursor.execute(
        """
        WITH ranked AS (
            SELECT id, username,
                   ROW_NUMBER() OVER (PARTITION BY username ORDER BY id) AS rn
            FROM users
        )
        UPDATE users u
        SET username = ranked.username || '_' || u.id
        FROM ranked
        WHERE u.id = ranked.id AND ranked.rn > 1;
        """
    )

    if _has_column(cursor, "users", "password"):
        cursor.execute("SELECT id, password FROM users WHERE (password_hash IS NULL OR password_hash = '') AND password IS NOT NULL;")
        rows = cursor.fetchall()
        for row in rows:
            legacy_password = row["password"] or ""
            if legacy_password:
                cursor.execute(
                    "UPDATE users SET password_hash = %(hash)s WHERE id = %(id)s;",
                    {"id": row["id"], "hash": hash_password(legacy_password)},
                )

    cursor.execute(
        "UPDATE users SET password_hash = COALESCE(password_hash, %(fallback)s) WHERE password_hash IS NULL OR password_hash = '';",
        {"fallback": hash_password(os.urandom(24).hex())},
    )

    cursor.execute("ALTER TABLE users ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE users ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE users ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE users ALTER COLUMN updated_at SET NOT NULL;")
    cursor.execute("ALTER TABLE users ALTER COLUMN username SET NOT NULL;")
    cursor.execute("ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL;")

    cursor.execute(
        """
        SELECT lower(btrim(email)) AS normalized_email
        FROM users
        GROUP BY lower(btrim(email))
        HAVING count(*) > 1
        LIMIT 1;
        """
    )
    if cursor.fetchone():
        raise RuntimeError("Duplicate users.email values after normalization")

    cursor.execute(
        """
        SELECT lower(btrim(username)) AS normalized_username
        FROM users
        GROUP BY lower(btrim(username))
        HAVING count(*) > 1
        LIMIT 1;
        """
    )
    if cursor.fetchone():
        raise RuntimeError("Duplicate users.username values after normalization")

    cursor.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_mail_key;")
    cursor.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key;")
    cursor.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;")

    cursor.execute("DROP INDEX IF EXISTS idx_users_email_unique;")
    cursor.execute("DROP INDEX IF EXISTS uq_users_email;")
    cursor.execute("DROP INDEX IF EXISTS uq_users_username;")

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_normalized
            ON users (lower(btrim(email)));
        """
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_normalized
            ON users (lower(btrim(username)));
        """
    )

    if _has_column(cursor, "users", "password"):
        cursor.execute("ALTER TABLE users DROP COLUMN password;")


def _ensure_default_user(cursor):
    if not DEFAULT_USER_PASSWORD:
        return

    cursor.execute("SELECT id FROM users WHERE email = %(email)s;", {"email": DEFAULT_USER_EMAIL})
    row = cursor.fetchone()
    if row:
        return

    # §7.3: exceeding the column limit is rejected, not truncated. Here the input
    # is configuration, not an HTTP request: there is no one to return a 422 to,
    # so startup fails with an explicit message instead of creating the account
    # with a name different from the configured one.
    username = sanitize_text(DEFAULT_USER_USERNAME) or "default_user"
    if len(username) > USER_USERNAME_MAX_LENGTH:
        raise ValueError(
            f"DEFAULT_USER_USERNAME exceeds {USER_USERNAME_MAX_LENGTH} characters "
            f"(users.username is VARCHAR({USER_USERNAME_MAX_LENGTH}))"
        )
    if len(DEFAULT_USER_EMAIL or "") > USER_EMAIL_MAX_LENGTH:
        raise ValueError(
            f"DEFAULT_USER_EMAIL exceeds {USER_EMAIL_MAX_LENGTH} characters "
            f"(users.email is VARCHAR({USER_EMAIL_MAX_LENGTH}))"
        )

    cursor.execute(
        """
        INSERT INTO users (email, username, password_hash, is_active, created_at, updated_at)
        VALUES (%(email)s, %(username)s, %(password_hash)s, TRUE, NOW(), NOW());
        """,
        {
            "email": DEFAULT_USER_EMAIL,
            "username": username,
            "password_hash": hash_password(DEFAULT_USER_PASSWORD),
        },
    )


def _remove_legacy_user_columns(cursor):
    """Remove user columns superseded by the canonical fields."""
    cursor.execute("ALTER TABLE users DROP COLUMN IF EXISTS name;")
    cursor.execute("ALTER TABLE users DROP COLUMN IF EXISTS registration_date;")


def _remove_legacy_user_sessions(cursor):
    """Remove the unused session table superseded by auth_sessions."""
    cursor.execute("DROP TABLE IF EXISTS user_sessions;")


def _remove_legacy_user_hidden_catalog(cursor):
    """Remove the unused per-user catalog hiding table."""
    cursor.execute("DROP TABLE IF EXISTS user_hidden_catalog;")


def _ensure_auth_sessions_schema(cursor):
    """Convert legacy auth session timestamps to timezone-aware values."""
    for column in ("created_at", "last_seen_at", "expires_at", "revoked_at"):
        data_type = (_column_data_type(cursor, "auth_sessions", column) or "").lower()
        if data_type == "timestamp without time zone":
            if column == "created_at":
                cursor.execute(
                    "ALTER TABLE auth_sessions ALTER COLUMN created_at TYPE TIMESTAMPTZ "
                    "USING created_at AT TIME ZONE 'UTC';"
                )
            elif column == "last_seen_at":
                cursor.execute(
                    "ALTER TABLE auth_sessions ALTER COLUMN last_seen_at TYPE TIMESTAMPTZ "
                    "USING last_seen_at AT TIME ZONE 'UTC';"
                )
            elif column == "expires_at":
                cursor.execute(
                    "ALTER TABLE auth_sessions ALTER COLUMN expires_at TYPE TIMESTAMPTZ "
                    "USING expires_at AT TIME ZONE 'UTC';"
                )
            else:
                cursor.execute(
                    "ALTER TABLE auth_sessions ALTER COLUMN revoked_at TYPE TIMESTAMPTZ "
                    "USING revoked_at AT TIME ZONE 'UTC';"
                )
        elif data_type != "timestamp with time zone":
            raise RuntimeError(f"Unexpected auth_sessions.{column} type: {data_type!r}")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_revoked_at ON auth_sessions(revoked_at);")
    cursor.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'auth_sessions'::regclass
                  AND conname = 'auth_sessions_user_id_fkey'
            ) AND NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'auth_sessions'::regclass
                  AND conname = 'fk_auth_sessions_user_id_users'
            ) THEN
                ALTER TABLE auth_sessions
                RENAME CONSTRAINT auth_sessions_user_id_fkey TO fk_auth_sessions_user_id_users;
            END IF;

            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'auth_sessions'::regclass
                  AND conname = 'auth_sessions_session_token_hash_key'
            ) AND NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'auth_sessions'::regclass
                  AND conname = 'uq_auth_sessions_session_token_hash'
            ) THEN
                ALTER TABLE auth_sessions
                RENAME CONSTRAINT auth_sessions_session_token_hash_key TO uq_auth_sessions_session_token_hash;
            END IF;
        END $$;
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'auth_sessions'::regclass
                  AND conname = 'ck_auth_sessions_expiry_after_creation'
            ) THEN
                ALTER TABLE auth_sessions
                ADD CONSTRAINT ck_auth_sessions_expiry_after_creation
                CHECK (expires_at > created_at);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'auth_sessions'::regclass
                  AND conname = 'ck_auth_sessions_last_seen_after_creation'
            ) THEN
                ALTER TABLE auth_sessions
                ADD CONSTRAINT ck_auth_sessions_last_seen_after_creation
                CHECK (last_seen_at >= created_at);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'auth_sessions'::regclass
                  AND conname = 'ck_auth_sessions_revoked_after_creation'
            ) THEN
                ALTER TABLE auth_sessions
                ADD CONSTRAINT ck_auth_sessions_revoked_after_creation
                CHECK (revoked_at IS NULL OR revoked_at >= created_at);
            END IF;
        END $$;
        """
    )


def _ensure_auth_rate_limits_schema(cursor):
    """Convert legacy rate-limit timestamps to timezone-aware values and
    add the integrity constraints missing from earlier deployments."""
    for column in ("first_attempt_at", "blocked_until"):
        data_type = (_column_data_type(cursor, "auth_rate_limits", column) or "").lower()
        if data_type == "timestamp without time zone":
            cursor.execute(
                sql.SQL(
                    "ALTER TABLE auth_rate_limits ALTER COLUMN {column} TYPE TIMESTAMPTZ "
                    "USING {column} AT TIME ZONE 'UTC';"
                ).format(column=sql.Identifier(column))
            )
        elif data_type != "timestamp with time zone":
            raise RuntimeError(f"Unexpected auth_rate_limits.{column} type: {data_type!r}")

    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'auth_rate_limits'::regclass
                  AND conname = 'ck_auth_rate_limits_attempts_non_negative'
            ) THEN
                ALTER TABLE auth_rate_limits
                ADD CONSTRAINT ck_auth_rate_limits_attempts_non_negative
                CHECK (attempts >= 0);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'auth_rate_limits'::regclass
                  AND conname = 'ck_auth_rate_limits_blocked_after_first'
            ) THEN
                ALTER TABLE auth_rate_limits
                ADD CONSTRAINT ck_auth_rate_limits_blocked_after_first
                CHECK (blocked_until IS NULL OR blocked_until >= first_attempt_at);
            END IF;
        END $$;
        """
    )
