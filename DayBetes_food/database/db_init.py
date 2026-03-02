import os

from DayBetes_food.auth.security import hash_password, normalize_identifier, sanitize_text
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.schema import DBSchema

DEFAULT_USER_EMAIL = normalize_identifier(os.getenv("DEFAULT_USER_EMAIL", "default@daybetes.local"))
DEFAULT_USER_USERNAME = normalize_identifier(os.getenv("DEFAULT_USER_USERNAME", "default_user"))
DEFAULT_USER_PASSWORD = os.getenv("DEFAULT_USER_PASSWORD", "")


def _has_column(cursor, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %(table)s AND column_name = %(column)s;
        """,
        {"table": table, "column": column},
    )
    return cursor.fetchone() is not None


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
        cursor.execute("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP;")

    if not _has_column(cursor, "users", "created_at"):
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP;")

    if not _has_column(cursor, "users", "updated_at"):
        cursor.execute("ALTER TABLE users ADD COLUMN updated_at TIMESTAMP;")

    if _has_column(cursor, "users", "registration_date"):
        cursor.execute("UPDATE users SET created_at = COALESCE(created_at, registration_date, CURRENT_TIMESTAMP);")
    else:
        cursor.execute("UPDATE users SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP);")
    cursor.execute("UPDATE users SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP);")

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
    cursor.execute("ALTER TABLE users ALTER COLUMN username SET NOT NULL;")
    cursor.execute("ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL;")

    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username ON users (username);")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users (email);")

    if _has_column(cursor, "users", "password"):
        cursor.execute("ALTER TABLE users DROP COLUMN password;")


def _ensure_default_user(cursor):
    if not DEFAULT_USER_PASSWORD:
        return

    cursor.execute("SELECT id FROM users WHERE email = %(email)s;", {"email": DEFAULT_USER_EMAIL})
    row = cursor.fetchone()
    if row:
        return

    cursor.execute(
        """
        INSERT INTO users (email, username, password_hash, is_active, created_at, updated_at)
        VALUES (%(email)s, %(username)s, %(password_hash)s, TRUE, NOW(), NOW());
        """,
        {
            "email": DEFAULT_USER_EMAIL,
            "username": sanitize_text(DEFAULT_USER_USERNAME, 50) or "default_user",
            "password_hash": hash_password(DEFAULT_USER_PASSWORD),
        },
    )


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    try:
        tables = [
            DBSchema.users,
            DBSchema.auth_sessions,
            DBSchema.auth_rate_limits,
            DBSchema.catalog,
            DBSchema.manual_intake,
            DBSchema.fridge,
            DBSchema.tags,
            DBSchema.recipe,
            DBSchema.linked_tags,
            DBSchema.intake_event,
            DBSchema.portion_detail,
        ]

        for table_sql in tables:
            cur.execute(table_sql)

        _ensure_users_schema(cur)
        _ensure_default_user(cur)

        conn.commit()
        print("Database initialized successfully.")
    except Exception as e:
        conn.rollback()
        print(f"Error initializing database: {e}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    init_db()
