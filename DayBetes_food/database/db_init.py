import os
from psycopg import sql

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


def _remove_legacy_user_columns(cursor):
    """Remove user columns superseded by the canonical fields."""
    cursor.execute("ALTER TABLE users DROP COLUMN IF EXISTS name;")
    cursor.execute("ALTER TABLE users DROP COLUMN IF EXISTS registration_date;")


def _ensure_catalog_schema(cursor):
    if not _has_column(cursor, "catalog", "created_at"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;")
    if not _has_column(cursor, "catalog", "updated_at"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;")
    if not _has_column(cursor, "catalog", "deleted_at"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN deleted_at TIMESTAMP NULL;")
    cursor.execute("UPDATE catalog SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP);")
    cursor.execute("UPDATE catalog SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP);")
    cursor.execute("ALTER TABLE catalog ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE catalog ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE catalog ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE catalog ALTER COLUMN updated_at SET NOT NULL;")
    if not _has_column(cursor, "catalog", "default_portion"):
        return
    dtype = (_column_data_type(cursor, "catalog", "default_portion") or "").lower()
    if dtype in {"smallint", "integer", "bigint"}:
        cursor.execute(
            "ALTER TABLE catalog ALTER COLUMN default_portion TYPE DOUBLE PRECISION USING default_portion::double precision;"
        )


def _ensure_manual_numeric_constraints(cursor):
    constraints = {
        "chk_manual_amount_g_valid": "CHECK (((amount_g > (0)::double precision) AND (amount_g <= (5000)::double precision) AND (amount_g <> 'NaN'::real) AND (amount_g <> 'Infinity'::real) AND (amount_g <> '-Infinity'::real))) NOT VALID",
        "chk_manual_calories_100g_valid": "CHECK (((calories_100g IS NULL) OR ((calories_100g >= (0)::double precision) AND (calories_100g <= (900)::double precision) AND (calories_100g <> 'NaN'::real) AND (calories_100g <> 'Infinity'::real) AND (calories_100g <> '-Infinity'::real)))) NOT VALID",
        "chk_manual_carbs_100g_valid": "CHECK (((carbs_100g IS NULL) OR ((carbs_100g >= (0)::double precision) AND (carbs_100g <= (100)::double precision) AND (carbs_100g <> 'NaN'::real) AND (carbs_100g <> 'Infinity'::real) AND (carbs_100g <> '-Infinity'::real)))) NOT VALID",
        "chk_manual_sugars_100g_valid": "CHECK (((sugars_100g IS NULL) OR ((sugars_100g >= (0)::double precision) AND (sugars_100g <= (100)::double precision) AND (sugars_100g <> 'NaN'::real) AND (sugars_100g <> 'Infinity'::real) AND (sugars_100g <> '-Infinity'::real)))) NOT VALID",
        "chk_manual_fats_100g_valid": "CHECK (((fats_100g IS NULL) OR ((fats_100g >= (0)::double precision) AND (fats_100g <= (100)::double precision) AND (fats_100g <> 'NaN'::real) AND (fats_100g <> 'Infinity'::real) AND (fats_100g <> '-Infinity'::real)))) NOT VALID",
        "chk_manual_saturated_100g_valid": "CHECK (((saturated_100g IS NULL) OR ((saturated_100g >= (0)::double precision) AND (saturated_100g <= (100)::double precision) AND (saturated_100g <> 'NaN'::real) AND (saturated_100g <> 'Infinity'::real) AND (saturated_100g <> '-Infinity'::real)))) NOT VALID",
        "chk_manual_proteins_100g_valid": "CHECK (((proteins_100g IS NULL) OR ((proteins_100g >= (0)::double precision) AND (proteins_100g <= (100)::double precision) AND (proteins_100g <> 'NaN'::real) AND (proteins_100g <> 'Infinity'::real) AND (proteins_100g <> '-Infinity'::real)))) NOT VALID",
        "chk_manual_fiber_100g_valid": "CHECK (((fiber_100g IS NULL) OR ((fiber_100g >= (0)::double precision) AND (fiber_100g <= (100)::double precision) AND (fiber_100g <> 'NaN'::real) AND (fiber_100g <> 'Infinity'::real) AND (fiber_100g <> '-Infinity'::real)))) NOT VALID",
        "chk_manual_caffeine_valid": "CHECK (((caffeine IS NULL) OR ((caffeine >= (0)::double precision) AND (caffeine <= (10000)::double precision) AND (caffeine <> 'NaN'::real) AND (caffeine <> 'Infinity'::real) AND (caffeine <> '-Infinity'::real)))) NOT VALID",
        "chk_manual_alcohol_valid": "CHECK (((alcohol IS NULL) OR ((alcohol >= (0)::double precision) AND (alcohol <= (10000)::double precision) AND (alcohol <> 'NaN'::real) AND (alcohol <> 'Infinity'::real) AND (alcohol <> '-Infinity'::real)))) NOT VALID",
        "chk_manual_saturated_le_fats": "CHECK (((saturated_100g IS NULL) OR (fats_100g IS NULL) OR (saturated_100g <= fats_100g))) NOT VALID",
    }
    cursor.execute(
        """
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = 'manual_intake'::regclass
          AND conname = ANY(%(names)s);
        """,
        {"names": list(constraints)},
    )
    existing = {row["conname"]: (row.get("definition") or "").strip() for row in cursor.fetchall() or []}
    for name, expected in constraints.items():
        actual = existing.get(name)
        if actual:
            validated_expected = expected.removesuffix(" NOT VALID")
            if actual not in (expected, validated_expected):
                raise RuntimeError(f"Unexpected definition for {name}: {actual!r}")
            continue
        body = expected.removesuffix(" NOT VALID")
        cursor.execute(
            sql.SQL("ALTER TABLE manual_intake ADD CONSTRAINT {} {} NOT VALID;").format(
                sql.Identifier(name), sql.SQL(body)
            )
        )


def _ensure_manual_intake_schema(cursor):
    """Keep the live manual_intake schema aligned with its canonical definition."""
    for column, definition in (
        ("deleted_at", "TIMESTAMP NULL"),
        ("created_at", "TIMESTAMP"),
        ("updated_at", "TIMESTAMP"),
    ):
        if not _has_column(cursor, "manual_intake", column):
            cursor.execute(
                sql.SQL("ALTER TABLE manual_intake ADD COLUMN {} {};").format(
                    sql.Identifier(column), sql.SQL(definition)
                )
            )

    # Legacy rows have no reliable creation time; the migration timestamp is only a backfill marker.
    cursor.execute(
        """
        UPDATE manual_intake
        SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
            updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP);
        """
    )
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN updated_at SET NOT NULL;")
    _ensure_manual_numeric_constraints(cursor)

    if _has_column(cursor, "manual_intake", "slug"):
        cursor.execute("ALTER TABLE manual_intake DROP COLUMN slug;")

    cursor.execute(
        """
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = 'manual_intake'::regclass
          AND contype = 'u';
        """
    )
    for row in cursor.fetchall() or []:
        definition = (row.get("definition") or "").strip()
        if definition == "UNIQUE (created_by, name, origin)":
            cursor.execute(
                sql.SQL("ALTER TABLE manual_intake DROP CONSTRAINT {};").format(
                    sql.Identifier(row["conname"])
                )
            )

    expected_active_indexdef = (
        "CREATE UNIQUE INDEX uq_manual_created_name_origin_norm ON public.manual_intake "
        "USING btree (created_by, lower(TRIM(BOTH FROM name)), "
        "lower(TRIM(BOTH FROM COALESCE(origin, ''::character varying)))) "
        "WHERE (deleted_at IS NULL)"
    )
    expected_legacy_indexdef = (
        "CREATE UNIQUE INDEX uq_manual_created_name_origin_norm ON public.manual_intake "
        "USING btree (created_by, lower(TRIM(BOTH FROM name)), "
        "lower(TRIM(BOTH FROM COALESCE(origin, ''::character varying))))"
    )
    cursor.execute(
        """
        SELECT indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'manual_intake'
          AND indexname = 'uq_manual_created_name_origin_norm';
        """
    )
    index_row = cursor.fetchone()
    if index_row:
        actual_indexdef = (index_row.get("indexdef") or "").strip()
        if actual_indexdef == expected_legacy_indexdef:
            cursor.execute("DROP INDEX uq_manual_created_name_origin_norm;")
            index_row = None
        elif actual_indexdef != expected_active_indexdef:
            raise RuntimeError(
                "Unexpected definition for uq_manual_created_name_origin_norm: "
                f"{actual_indexdef!r}"
            )
    if not index_row:
        cursor.execute(
            """
            CREATE UNIQUE INDEX uq_manual_created_name_origin_norm
            ON manual_intake (
                created_by,
                lower(trim(name)),
                lower(trim(coalesce(origin, '')))
            )
            WHERE deleted_at IS NULL;
            """
        )

    cursor.execute(
        """
        SELECT indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'manual_intake'
          AND indexname = 'idx_manual_active_created_by';
        """
    )
    active_owner_index = cursor.fetchone()
    expected_owner_indexdef = (
        "CREATE INDEX idx_manual_active_created_by ON public.manual_intake USING btree (created_by) "
        "WHERE (deleted_at IS NULL)"
    )
    if active_owner_index:
        actual_owner_indexdef = (active_owner_index.get("indexdef") or "").strip()
        if actual_owner_indexdef != expected_owner_indexdef:
            raise RuntimeError(
                "Unexpected definition for idx_manual_active_created_by: "
                f"{actual_owner_indexdef!r}"
            )
    else:
        cursor.execute(
            """
            CREATE INDEX idx_manual_active_created_by
            ON manual_intake (created_by)
            WHERE deleted_at IS NULL;
            """
        )


def _ensure_user_favorites_schema(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_favorites (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            catalog_id INTEGER REFERENCES catalog(id) ON DELETE CASCADE,
            manual_intake_id INTEGER REFERENCES manual_intake(id) ON DELETE CASCADE,
            recipe_id INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
            CHECK (num_nonnulls(catalog_id, manual_intake_id, recipe_id) = 1)
        );
        """
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_favorites_catalog ON user_favorites(user_id, catalog_id) WHERE catalog_id IS NOT NULL;"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_favorites_manual ON user_favorites(user_id, manual_intake_id) WHERE manual_intake_id IS NOT NULL;"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_favorites_recipe ON user_favorites(user_id, recipe_id) WHERE recipe_id IS NOT NULL;"
    )
    cursor.execute("DROP INDEX IF EXISTS idx_catalog_favorite;")
    cursor.execute("DROP INDEX IF EXISTS idx_manual_favorite;")
    cursor.execute("DROP INDEX IF EXISTS idx_recipe_favorite;")
    cursor.execute("ALTER TABLE catalog DROP COLUMN IF EXISTS favorite;")
    cursor.execute("ALTER TABLE manual_intake DROP COLUMN IF EXISTS favorite;")
    cursor.execute("ALTER TABLE recipe DROP COLUMN IF EXISTS favorite;")

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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_visibility ON catalog (is_private, created_by);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_deleted_at ON catalog (deleted_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_created_by ON manual_intake (created_by);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_visibility ON manual_intake (is_private, created_by);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_users_id ON recipe (users_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_visibility ON recipe (is_private, users_id);")


def _ensure_tags_color_schema(cursor):
    if not _has_column(cursor, "tags", "color"):
        cursor.execute("ALTER TABLE tags ADD COLUMN color VARCHAR(64);")
    cursor.execute(
        """
        UPDATE tags
        SET color = 'hsl(' || (
            (('x' || substr(md5(lower(trim(name))), 1, 8))::bit(32)::int % 360 + 360) % 360
        ) || ' 80% 90%)'
        WHERE color IS NULL OR trim(color) = '';
        """
    )
    cursor.execute("ALTER TABLE tags ALTER COLUMN color SET DEFAULT 'hsl(0 80% 90%)';")
    cursor.execute("ALTER TABLE tags ALTER COLUMN color SET NOT NULL;")


def _ensure_food_name_origin_uniqueness(cursor):
    # Drop legacy unique constraints that only considered `name`.
    cursor.execute(
        """
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'catalog'
          AND con.contype = 'u'
          AND pg_get_constraintdef(con.oid) ILIKE 'UNIQUE (name)%';
        """
    )
    for row in cursor.fetchall() or []:
        name = row.get("conname")
        if name:
            cursor.execute(f'ALTER TABLE catalog DROP CONSTRAINT IF EXISTS "{name}";')

    cursor.execute(
        """
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'manual_intake'
          AND con.contype = 'u'
          AND pg_get_constraintdef(con.oid) ILIKE 'UNIQUE (created_by, name)%';
        """
    )
    for row in cursor.fetchall() or []:
        name = row.get("conname")
        if name:
            cursor.execute(f'ALTER TABLE manual_intake DROP CONSTRAINT IF EXISTS "{name}";')

    # Enforce normalized uniqueness (case-insensitive and space-trimmed).
    cursor.execute("SAVEPOINT food_name_origin_uniqueness;")
    try:
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_catalog_name_brand_norm
            ON catalog (lower(trim(name)), lower(trim(COALESCE(brand, ''))));
            """
        )
        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_manual_created_name_origin_norm
            ON manual_intake (created_by, lower(trim(name)), lower(trim(COALESCE(origin, ''))));
            """
        )
        cursor.execute("RELEASE SAVEPOINT food_name_origin_uniqueness;")
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT food_name_origin_uniqueness;")
        cursor.execute("RELEASE SAVEPOINT food_name_origin_uniqueness;")
        print(f"Warning: food uniqueness migration skipped: {exc}")


def _ensure_insulin_injections_schema(cursor):
    cursor.execute(
        """
        DO $$
        BEGIN
            -- Prefer direct rename when old table exists and new one does not.
            IF to_regclass('public.insulin_injections') IS NULL AND to_regclass('public.injection_zones') IS NOT NULL THEN
                ALTER TABLE injection_zones RENAME TO insulin_injections;
            ELSIF to_regclass('public.insulin_injections') IS NULL AND to_regclass('public.injection_zone') IS NOT NULL THEN
                ALTER TABLE injection_zone RENAME TO insulin_injections;
            END IF;
        END $$;
        """
    )
    cursor.execute(
        """
        ALTER TABLE intake_event
        ADD COLUMN IF NOT EXISTS injection_zone VARCHAR(50);
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_intake_event_injection_zone'
            ) THEN
                ALTER TABLE intake_event
                ADD CONSTRAINT ck_intake_event_injection_zone
                CHECK (injection_zone IN ('right_arm', 'left_arm', 'right_thigh', 'left_thigh', 'abdomen', 'right_gluteus', 'left_gluteus') OR injection_zone IS NULL);
            END IF;
        END $$;
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS insulin_injections (
            id SERIAL PRIMARY KEY,
            users_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            intake_event_id INTEGER REFERENCES intake_event(id) ON DELETE CASCADE,
            shot_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            insulin_type VARCHAR(20) CHECK (insulin_type IN ('rapid', 'basal')),
            basal_units REAL CHECK (basal_units > 0),
            injection_zone VARCHAR(50) CHECK (injection_zone IN ('right_arm', 'left_arm', 'right_thigh', 'left_thigh', 'abdomen', 'right_gluteus', 'left_gluteus'))
        );
        """
    )
    cursor.execute("ALTER TABLE insulin_injections ADD COLUMN IF NOT EXISTS intake_event_id INTEGER;")
    cursor.execute("ALTER TABLE insulin_injections ADD COLUMN IF NOT EXISTS users_id INTEGER;")
    cursor.execute("ALTER TABLE insulin_injections ADD COLUMN IF NOT EXISTS insulin_type VARCHAR(20);")
    cursor.execute("ALTER TABLE insulin_injections ADD COLUMN IF NOT EXISTS basal_units REAL;")
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_insulin_injections_intake_event'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT fk_insulin_injections_intake_event
                FOREIGN KEY (intake_event_id) REFERENCES intake_event(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_insulin_injections_users'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT fk_insulin_injections_users
                FOREIGN KEY (users_id) REFERENCES users(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_insulin_injections_insulin_type'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT ck_insulin_injections_insulin_type
                CHECK (insulin_type IN ('rapid', 'basal') OR insulin_type IS NULL);
            END IF;
        END $$;
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_insulin_injections_basal_units'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT ck_insulin_injections_basal_units
                CHECK (basal_units IS NULL OR basal_units > 0);
            END IF;
        END $$;
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_insulin_injections_intake_event_id_shot_time
        ON insulin_injections (intake_event_id, shot_time DESC, id DESC);
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_insulin_injections_users_id_shot_time
        ON insulin_injections (users_id, shot_time DESC, id DESC);
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.injection_zone') IS NOT NULL THEN
                INSERT INTO insulin_injections (id, users_id, intake_event_id, shot_time, insulin_type, basal_units, injection_zone)
                SELECT id, users_id, intake_event_id, shot_time, insulin_type, basal_units, injection_zone
                FROM injection_zone
                ON CONFLICT (id) DO NOTHING;
                PERFORM setval('insulin_injections_id_seq', COALESCE((SELECT MAX(id) FROM insulin_injections), 1), true);
                DROP TABLE injection_zone;
            END IF;
            IF to_regclass('public.injection_zones') IS NOT NULL THEN
                INSERT INTO insulin_injections (id, users_id, intake_event_id, shot_time, insulin_type, basal_units, injection_zone)
                SELECT id, users_id, intake_event_id, shot_time, insulin_type, basal_units, injection_zone
                FROM injection_zones
                ON CONFLICT (id) DO NOTHING;
                PERFORM setval('insulin_injections_id_seq', COALESCE((SELECT MAX(id) FROM insulin_injections), 1), true);
                DROP TABLE injection_zones;
            END IF;
        END $$;
        """
    )


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
            DBSchema.user_favorites,
            DBSchema.linked_tags,
            DBSchema.intake_event,
            DBSchema.insulin_injections,
            DBSchema.portion_detail,
        ]

        for table_sql in tables:
            cur.execute(table_sql)

        _ensure_trgm_search(cur)
        _ensure_tags_color_schema(cur)
        _ensure_manual_intake_schema(cur)
        _ensure_food_name_origin_uniqueness(cur)
        _drop_legacy_category_check(cur)
        _ensure_catalog_schema(cur)
        _ensure_user_favorites_schema(cur)
        _ensure_food_filter_indexes(cur)
        _ensure_privacy_schema(cur)
        _ensure_copy_origin_schema(cur)
        _ensure_users_schema(cur)
        _ensure_auth_sessions_schema(cur)
        _ensure_insulin_injections_schema(cur)
        _remove_legacy_user_sessions(cur)
        _remove_legacy_user_hidden_catalog(cur)
        _remove_legacy_user_columns(cur)
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
