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


def _column_data_type(cursor, table: str, column: str):
    cursor.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = %(table)s AND column_name = %(column)s
        LIMIT 1;
        """,
        {"table": table, "column": column},
    )
    row = cursor.fetchone()
    return row["data_type"] if row else None


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


def _ensure_catalog_schema(cursor):
    if not _has_column(cursor, "catalog", "default_portion"):
        return
    dtype = (_column_data_type(cursor, "catalog", "default_portion") or "").lower()
    if dtype in {"smallint", "integer", "bigint"}:
        cursor.execute(
            "ALTER TABLE catalog ALTER COLUMN default_portion TYPE DOUBLE PRECISION USING default_portion::double precision;"
        )

def _drop_legacy_category_check(cursor):
    cursor.execute(
        """
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'catalog'
          AND con.contype = 'c'
          AND pg_get_constraintdef(con.oid) ILIKE '%category%'
          AND pg_get_constraintdef(con.oid) ILIKE '%IN (%';
        """
    )
    rows = cursor.fetchall() or []
    for row in rows:
        name = row.get("conname")
        if not name:
            continue
        cursor.execute(f'ALTER TABLE catalog DROP CONSTRAINT IF EXISTS "{name}";')


def _ensure_privacy_schema(cursor):
    if not _has_column(cursor, "catalog", "is_private"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN is_private BOOLEAN DEFAULT FALSE;")
    if not _has_column(cursor, "manual_intake", "is_private"):
        cursor.execute("ALTER TABLE manual_intake ADD COLUMN is_private BOOLEAN DEFAULT FALSE;")
    if not _has_column(cursor, "recipe", "is_private"):
        cursor.execute("ALTER TABLE recipe ADD COLUMN is_private BOOLEAN DEFAULT FALSE;")

    cursor.execute("UPDATE catalog SET is_private = FALSE WHERE is_private IS NULL;")
    cursor.execute("UPDATE manual_intake SET is_private = FALSE WHERE is_private IS NULL;")
    cursor.execute("UPDATE recipe SET is_private = FALSE WHERE is_private IS NULL;")

    cursor.execute("ALTER TABLE catalog ALTER COLUMN is_private SET DEFAULT FALSE;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN is_private SET DEFAULT FALSE;")
    cursor.execute("ALTER TABLE recipe ALTER COLUMN is_private SET DEFAULT FALSE;")

    cursor.execute("ALTER TABLE catalog ALTER COLUMN is_private SET NOT NULL;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN is_private SET NOT NULL;")
    cursor.execute("ALTER TABLE recipe ALTER COLUMN is_private SET NOT NULL;")


def _ensure_copy_origin_schema(cursor):
    if not _has_column(cursor, "catalog", "origin_root_id"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN origin_root_id INTEGER REFERENCES catalog(id) ON DELETE SET NULL;")
    if not _has_column(cursor, "manual_intake", "origin_root_id"):
        cursor.execute("ALTER TABLE manual_intake ADD COLUMN origin_root_id INTEGER REFERENCES manual_intake(id) ON DELETE SET NULL;")
    if not _has_column(cursor, "recipe", "origin_root_id"):
        cursor.execute("ALTER TABLE recipe ADD COLUMN origin_root_id INTEGER REFERENCES recipe(id) ON DELETE SET NULL;")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_origin_root ON catalog (origin_root_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_origin_root ON manual_intake (origin_root_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_origin_root ON recipe (origin_root_id);")


def _ensure_trgm_search(cursor):
    # Best-effort: if extension/index creation is not permitted, keep app running.
    cursor.execute("SAVEPOINT trgm_setup;")
    try:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_catalog_name_trgm "
            "ON catalog USING gin (lower(name) gin_trgm_ops);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_manual_intake_name_trgm "
            "ON manual_intake USING gin (lower(name) gin_trgm_ops);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_recipe_name_trgm "
            "ON recipe USING gin (lower(name) gin_trgm_ops);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_catalog_brand_trgm "
            "ON catalog USING gin (lower(brand) gin_trgm_ops);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_manual_origin_trgm "
            "ON manual_intake USING gin (lower(origin) gin_trgm_ops);"
        )
        cursor.execute("RELEASE SAVEPOINT trgm_setup;")
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT trgm_setup;")
        cursor.execute("RELEASE SAVEPOINT trgm_setup;")
        print(f"Warning: pg_trgm setup skipped: {exc}")


def _ensure_food_filter_indexes(cursor):
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_created_by ON catalog (created_by);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_favorite ON catalog (favorite);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_visibility ON catalog (is_private, created_by);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_created_by ON manual_intake (created_by);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_favorite ON manual_intake (favorite);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_visibility ON manual_intake (is_private, created_by);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_users_id ON recipe (users_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_favorite ON recipe (favorite);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_visibility ON recipe (is_private, users_id);")


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    try:
        tables = [
            DBSchema.users,
            DBSchema.auth_sessions,
            DBSchema.auth_rate_limits,
            DBSchema.food_brands,
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

        _ensure_trgm_search(cur)
        _ensure_food_filter_indexes(cur)
        _drop_legacy_category_check(cur)
        _ensure_catalog_schema(cur)
        _ensure_privacy_schema(cur)
        _ensure_copy_origin_schema(cur)
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
