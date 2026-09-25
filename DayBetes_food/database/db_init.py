import logging
import os
import re
from psycopg import sql

from DayBetes_food.auth.models import USER_EMAIL_MAX_LENGTH, USER_USERNAME_MAX_LENGTH
from DayBetes_food.auth.security import hash_password, normalize_identifier, sanitize_text
from DayBetes_food.config import DB_RUNTIME_ROLE
from DayBetes_food.database.connection import get_migrations_connection
from DayBetes_food.database.schema import DBSchema, catalog_check_constraints
from DayBetes_food.domain.catalog import CATALOG_BARCODE_MAX_LENGTH, CATALOG_BARCODE_MIN_LENGTH
from DayBetes_food.domain.constants import (
    IntakeEventState,
    InsulinType,
    InjectionZone,
    MealType,
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodPhysicalState,
    sql_in_list,
)
from DayBetes_food.domain.nutrition import NUTRIENT_LIMITS

logger = logging.getLogger(__name__)

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


def _column_default(cursor, table: str, column: str):
    cursor.execute(
        """
        SELECT column_default
        FROM information_schema.columns
        WHERE table_name = %(table)s AND column_name = %(column)s
        LIMIT 1;
        """,
        {"table": table, "column": column},
    )
    row = cursor.fetchone()
    return row["column_default"] if row else None


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


_CATALOG_CONSTRAINT_RENAMES = {
    "catalog_pkey": "pk_catalog",
    "catalog_created_by_fkey": "fk_catalog_created_by_users",
    "catalog_origin_root_id_fkey": "fk_catalog_origin_root_id_catalog",
}

_CATALOG_LEGACY_CHECKS = (
    "catalog_category_check",
    "catalog_initial_state_check",
    "catalog_nova_check",
    "catalog_nutriscore_check",
    "catalog_yuka_check",
)


def _ensure_catalog_schema(cursor):
    """catalog: canonical schema rebuilt from the enums and the limits (§12.1).

    Idempotent (§12.2). Closes findings 1, 2, 3, 12, 13, 18, 19, 23 and 26 of
    audit/audits/audit_catalog.md.
    """
    # ---- 1. Temporal columns (H18, §10.5) ----
    if not _has_column(cursor, "catalog", "created_at"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN created_at TIMESTAMPTZ;")
    if not _has_column(cursor, "catalog", "updated_at"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN updated_at TIMESTAMPTZ;")
    if not _has_column(cursor, "catalog", "deleted_at"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN deleted_at TIMESTAMPTZ;")
    cursor.execute("UPDATE catalog SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP);")
    cursor.execute("UPDATE catalog SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP);")
    for column in ("created_at", "updated_at", "deleted_at"):
        data_type = (_column_data_type(cursor, "catalog", column) or "").lower()
        if data_type == "timestamp without time zone":
            if column in ("created_at", "updated_at"):
                cursor.execute(
                    sql.SQL("ALTER TABLE catalog ALTER COLUMN {} DROP DEFAULT;").format(
                        sql.Identifier(column)
                    )
                )
            cursor.execute(
                sql.SQL(
                    "ALTER TABLE catalog ALTER COLUMN {} TYPE TIMESTAMPTZ "
                    "USING {} AT TIME ZONE 'UTC';"
                ).format(sql.Identifier(column), sql.Identifier(column))
            )
        elif data_type != "timestamp with time zone":
            raise RuntimeError(f"Unexpected catalog.{column} type: {data_type!r}")
    cursor.execute("ALTER TABLE catalog ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE catalog ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE catalog ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE catalog ALTER COLUMN updated_at SET NOT NULL;")

    # ---- 2. slug (H19, decision 2026-09-25) ----
    cursor.execute("DROP INDEX IF EXISTS idx_catalog_slug;")
    if _has_column(cursor, "catalog", "slug"):
        cursor.execute("ALTER TABLE catalog DROP COLUMN slug;")

    # ---- 3. default_portion (H19, H15) ----
    if _has_column(cursor, "catalog", "default_portion"):
        dtype = (_column_data_type(cursor, "catalog", "default_portion") or "").lower()
        if dtype != "real":
            cursor.execute(
                "ALTER TABLE catalog ALTER COLUMN default_portion TYPE REAL "
                "USING default_portion::real;"
            )
        cursor.execute("ALTER TABLE catalog ALTER COLUMN default_portion DROP DEFAULT;")

    # ---- 4. cooking_factor (H23, decision 2026-09-24), once ----
    if _has_column(cursor, "catalog", "cooking_factor"):
        if _column_default(cursor, "catalog", "cooking_factor") is not None:
            cursor.execute(
                """
                SELECT count(*) AS weighed
                FROM portion_detail pd
                JOIN catalog c ON c.id = pd.catalog_id
                WHERE pd.is_cooked_weight AND c.cooking_factor = 1.0;
                """
            )
            weighed = cursor.fetchone()["weighed"]
            if weighed:
                raise RuntimeError(
                    f"{weighed} portion_detail rows are cooked-weighed against a "
                    "catalog.cooking_factor of exactly 1.0; they cannot become NULL "
                    "(decision 2026-09-24, code_conventions.md 12.7)."
                )
            cursor.execute("UPDATE catalog SET cooking_factor = NULL WHERE cooking_factor = 1.0;")
            logger.info("catalog.cooking_factor: %s rows set to NULL", cursor.rowcount)
            cursor.execute("ALTER TABLE catalog ALTER COLUMN cooking_factor DROP DEFAULT;")

    # ---- 5. barcode (H13) ----
    barcode_re = (
        f"^[0-9]{{{CATALOG_BARCODE_MIN_LENGTH},{CATALOG_BARCODE_MAX_LENGTH}}}$"
    )
    cursor.execute(
        "SELECT count(*) AS bad FROM catalog WHERE barcode IS NOT NULL AND barcode !~ %(re)s;",
        {"re": barcode_re},
    )
    if cursor.fetchone()["bad"]:
        raise RuntimeError(
            "catalog.barcode has values outside the digits-8-to-48 format; "
            "ck_catalog_barcode_format cannot be created (code_conventions.md 12.7)."
        )
    cursor.execute(
        """
        SELECT character_maximum_length AS length
        FROM information_schema.columns
        WHERE table_name = 'catalog' AND column_name = 'barcode';
        """
    )
    barcode_row = cursor.fetchone()
    barcode_length = barcode_row["length"] if barcode_row else None
    if barcode_length != CATALOG_BARCODE_MAX_LENGTH:
        cursor.execute(
            f"ALTER TABLE catalog ALTER COLUMN barcode TYPE VARCHAR({CATALOG_BARCODE_MAX_LENGTH});"
        )

    # ---- 6. CHECKs (H1, H3, H6, H12, H13, H26) ----
    # 6a. Category safeguard before dropping: fail on divergence, never correct.
    cursor.execute(
        """
        SELECT pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = 'catalog'::regclass AND conname = 'catalog_category_check';
        """
    )
    legacy_category = cursor.fetchone()
    if legacy_category:
        definition = legacy_category.get("definition") or ""
        literals = set(re.findall(r"'([^']+)'", definition))
        expected = {member.value for member in FoodCategory}
        if literals != expected:
            raise RuntimeError(
                "catalog_category_check does not match FoodCategory: "
                f"{sorted(literals)} != {sorted(expected)}"
            )
    # 6b. Drop inherited CHECKs by their exact name.
    for legacy_name in _CATALOG_LEGACY_CHECKS:
        cursor.execute(
            sql.SQL("ALTER TABLE catalog DROP CONSTRAINT IF EXISTS {};").format(
                sql.Identifier(legacy_name)
            )
        )
    # 6c. Add the canonical CHECKs, generated from the enums and the limits.
    for name, expression in catalog_check_constraints().items():
        cursor.execute(
            sql.SQL("ALTER TABLE catalog DROP CONSTRAINT IF EXISTS {};").format(sql.Identifier(name))
        )
        cursor.execute(
            sql.SQL("ALTER TABLE catalog ADD CONSTRAINT {} CHECK ({});").format(
                sql.Identifier(name), sql.SQL(expression)
            )
        )

    # ---- 7. Canonical names (§11.6, H19) ----
    for old_name, new_name in _CATALOG_CONSTRAINT_RENAMES.items():
        if _constraint_exists(cursor, "catalog", old_name) and not _constraint_exists(
            cursor, "catalog", new_name
        ):
            cursor.execute(
                sql.SQL("ALTER TABLE catalog RENAME CONSTRAINT {} TO {};").format(
                    sql.Identifier(old_name), sql.Identifier(new_name)
                )
            )

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
            cursor.execute(
                sql.SQL("ALTER TABLE catalog DROP CONSTRAINT IF EXISTS {};").format(
                    sql.Identifier(name)
                )
            )

    # Final safeguard (§12.2, H1): any constraint outside the canonical set fails
    # the bootstrap instead of lingering as an unknown rule.
    canonical = {
        "pk_catalog",
        "fk_catalog_created_by_users",
        "fk_catalog_origin_root_id_catalog",
        "fk_catalog_brand_id_food_brands",
    } | set(catalog_check_constraints())
    cursor.execute(
        """
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'catalog'::regclass
          AND contype IN ('p', 'f', 'c', 'u');
        """
    )
    unexpected = sorted(
        row["conname"] for row in cursor.fetchall() or [] if row["conname"] not in canonical
    )
    if unexpected:
        raise RuntimeError(
            f"catalog has constraints outside the canonical set: {unexpected}. "
            "Add them to catalog_check_constraints() or remove them explicitly (§12.1)."
        )

    # ---- 8. Partial unique indexes (H2, H8, H26, §6.1) ----
    cursor.execute("DROP INDEX IF EXISTS uq_catalog_name_brand_id_norm;")
    unique_indexes = (
        "CREATE UNIQUE INDEX uq_catalog_personal_name_brand "
        "ON catalog (created_by, lower(name), COALESCE(brand_id, 0)) "
        "WHERE deleted_at IS NULL AND NOT is_published;",
        "CREATE UNIQUE INDEX uq_catalog_published_name_brand "
        "ON catalog (lower(name), COALESCE(brand_id, 0)) "
        "WHERE deleted_at IS NULL AND is_published;",
        "CREATE UNIQUE INDEX uq_catalog_personal_barcode "
        "ON catalog (created_by, barcode) "
        "WHERE deleted_at IS NULL AND NOT is_published AND barcode IS NOT NULL AND origin_root_id IS NULL;",
        "CREATE UNIQUE INDEX uq_catalog_published_barcode "
        "ON catalog (barcode) "
        "WHERE deleted_at IS NULL AND is_published AND barcode IS NOT NULL;",
    )
    for index_name in (
        "uq_catalog_personal_name_brand",
        "uq_catalog_published_name_brand",
        "uq_catalog_personal_barcode",
        "uq_catalog_published_barcode",
    ):
        cursor.execute(
            sql.SQL("DROP INDEX IF EXISTS {};").format(sql.Identifier(index_name))
        )
    for statement in unique_indexes:
        cursor.execute(statement)


def _manual_numeric_check(column: str, maximum) -> str:
    maximum_text = str(int(maximum)) if float(maximum).is_integer() else repr(float(maximum))
    return (
        f"CHECK ((({column} IS NULL) OR (({column} >= (0)::double precision) "
        f"AND ({column} <= ({maximum_text})::double precision) "
        f"AND ({column} <> 'NaN'::real) AND ({column} <> 'Infinity'::real) "
        f"AND ({column} <> '-Infinity'::real)))) NOT VALID"
    )


def _ensure_manual_numeric_constraints(cursor):
    constraints = {
        "chk_manual_amount_g_valid": "CHECK (((amount_g > (0)::double precision) AND (amount_g <= (5000)::double precision) AND (amount_g <> 'NaN'::real) AND (amount_g <> 'Infinity'::real) AND (amount_g <> '-Infinity'::real))) NOT VALID",
        "chk_manual_calories_100g_valid": _manual_numeric_check("calories_100g", NUTRIENT_LIMITS["calories_100g"].maximum),
        "chk_manual_carbs_100g_valid": _manual_numeric_check("carbs_100g", NUTRIENT_LIMITS["carbs_100g"].maximum),
        "chk_manual_sugars_100g_valid": _manual_numeric_check("sugars_100g", NUTRIENT_LIMITS["sugars_100g"].maximum),
        "chk_manual_fats_100g_valid": _manual_numeric_check("fats_100g", NUTRIENT_LIMITS["fats_100g"].maximum),
        "chk_manual_saturated_100g_valid": _manual_numeric_check("saturated_100g", NUTRIENT_LIMITS["saturated_100g"].maximum),
        "chk_manual_proteins_100g_valid": _manual_numeric_check("proteins_100g", NUTRIENT_LIMITS["proteins_100g"].maximum),
        "chk_manual_fiber_100g_valid": _manual_numeric_check("fiber_100g", NUTRIENT_LIMITS["fiber_100g"].maximum),
        "chk_manual_caffeine_valid": _manual_numeric_check("caffeine", NUTRIENT_LIMITS["caffeine"].maximum),
        "chk_manual_alcohol_valid": _manual_numeric_check("alcohol", NUTRIENT_LIMITS["alcohol"].maximum),
        "chk_manual_saturated_le_fats": "CHECK (((saturated_100g IS NULL) OR (fats_100g IS NULL) OR (saturated_100g <= fats_100g))) NOT VALID",
        # New canonical name: it is a new rule added by the catalog audit (§11.6).
        "ck_manual_intake_sugars_le_carbs": "CHECK (((sugars_100g IS NULL) OR (carbs_100g IS NULL) OR (sugars_100g <= carbs_100g))) NOT VALID",
    }

    # Blocking pre-checks: a row that violates the new ceiling or relation is a
    # data decision, not something the migration may rewrite (§12.7).
    cursor.execute("SELECT count(*) AS bad FROM manual_intake WHERE alcohol > 100;")
    if cursor.fetchone()["bad"]:
        raise RuntimeError(
            "manual_intake.alcohol has rows above 100; chk_manual_alcohol_valid "
            "cannot be created (code_conventions.md 12.7)."
        )
    cursor.execute(
        "SELECT count(*) AS bad FROM manual_intake WHERE sugars_100g > carbs_100g;"
    )
    if cursor.fetchone()["bad"]:
        raise RuntimeError(
            "manual_intake has rows with sugars_100g > carbs_100g; "
            "ck_manual_intake_sugars_le_carbs cannot be created (code_conventions.md 12.7)."
        )

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

    # The old caffeine/alcohol ceiling was 10000. Drop exactly those definitions
    # so the loop recreates them with the shared ceiling; any other different
    # definition still raises below.
    old_caffeine = _manual_numeric_check("caffeine", 10000)
    old_alcohol = _manual_numeric_check("alcohol", 10000)
    for name, old_definition in (
        ("chk_manual_caffeine_valid", old_caffeine),
        ("chk_manual_alcohol_valid", old_alcohol),
    ):
        actual = existing.get(name)
        if actual and actual in (old_definition, old_definition.removesuffix(" NOT VALID")):
            cursor.execute(
                sql.SQL("ALTER TABLE manual_intake DROP CONSTRAINT {};").format(
                    sql.Identifier(name)
                )
            )
            existing.pop(name, None)

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

_PUBLICATION_TABLES = (("catalog", "created_by"), ("manual_intake", "created_by"), ("recipe", "users_id"))


def _ensure_food_publication_schema(cursor):
    """is_private -> is_published (inverted) in the three food tables at once
    (decisions 2026-09-24 privacy and 2026-09-25 R1). Idempotent: the data step
    only runs while is_private still exists."""
    renamed_now = False
    for table, _owner in _PUBLICATION_TABLES:
        has_old = _has_column(cursor, table, "is_private")
        has_new = _has_column(cursor, table, "is_published")
        if has_old and has_new:
            raise RuntimeError(
                f"{table} has both is_private and is_published: half-applied migration"
            )
        if has_old:
            cursor.execute(
                sql.SQL("SELECT count(*) AS private_count FROM {} WHERE is_private;").format(
                    sql.Identifier(table)
                )
            )
            private_count = cursor.fetchone()["private_count"]
            cursor.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN is_published BOOLEAN;").format(
                    sql.Identifier(table)
                )
            )
            cursor.execute(
                sql.SQL("UPDATE {} SET is_published = NOT is_private;").format(
                    sql.Identifier(table)
                )
            )
            cursor.execute(
                sql.SQL(
                    "SELECT count(*) AS mismatched FROM {} WHERE is_published = is_private;"
                ).format(sql.Identifier(table))
            )
            if cursor.fetchone()["mismatched"]:
                raise RuntimeError(f"{table}: is_published is not the inverse of is_private")
            cursor.execute(
                sql.SQL("SELECT count(*) AS not_published FROM {} WHERE NOT is_published;").format(
                    sql.Identifier(table)
                )
            )
            if cursor.fetchone()["not_published"] != private_count:
                raise RuntimeError(f"{table}: private row count changed during the rename")
            cursor.execute(
                sql.SQL("ALTER TABLE {} DROP COLUMN is_private;").format(sql.Identifier(table))
            )
            renamed_now = True
        elif not has_new:
            cursor.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN is_published BOOLEAN;").format(
                    sql.Identifier(table)
                )
            )
            cursor.execute(
                sql.SQL("UPDATE {} SET is_published = FALSE WHERE is_published IS NULL;").format(
                    sql.Identifier(table)
                )
            )
        cursor.execute(
            sql.SQL("ALTER TABLE {} ALTER COLUMN is_published SET DEFAULT FALSE;").format(
                sql.Identifier(table)
            )
        )
        cursor.execute(
            sql.SQL("ALTER TABLE {} ALTER COLUMN is_published SET NOT NULL;").format(
                sql.Identifier(table)
            )
        )
    if renamed_now:
        _publish_personal_ingredients_of_published_recipes(cursor)


def _publish_personal_ingredients_of_published_recipes(cursor):
    """Data correction (decision 2026-09-25, R2, §12.7): a personal catalog
    ingredient of a published recipe owned by the same user becomes published,
    exactly as the publish-recipe popup would. An ingredient owned by someone
    else stops the migration: publishing someone else's food needs another
    decision."""
    cursor.execute(
        """
        SELECT DISTINCT c.id AS catalog_id, c.created_by, r.id AS recipe_id, r.users_id
        FROM recipe r
        JOIN portion_detail pd ON pd.recipe_id = r.id
        JOIN catalog c ON c.id = pd.catalog_id
        WHERE r.is_published AND NOT c.is_published;
        """
    )
    rows = cursor.fetchall() or []
    if not rows:
        return
    foreign = [
        row for row in rows if row["created_by"] != row["users_id"]
    ]
    if foreign:
        detail = ", ".join(
            f"catalog {row['catalog_id']} (owner {row['created_by']}) in recipe "
            f"{row['recipe_id']} (owner {row['users_id']})"
            for row in foreign
        )
        raise RuntimeError(
            "Published recipes contain personal catalog ingredients owned by "
            f"another user; publishing them needs another decision: {detail}"
        )
    ids = sorted({row["catalog_id"] for row in rows})
    cursor.execute(
        "UPDATE catalog SET is_published = TRUE, updated_at = NOW() WHERE id = ANY(%(ids)s);",
        {"ids": ids},
    )
    logger.info(
        "Published %s personal catalog ingredients of published recipes: %s",
        len(ids),
        ids,
    )


def _ensure_copy_origin_schema(cursor):
    if not _has_column(cursor, "catalog", "origin_root_id"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN origin_root_id INTEGER REFERENCES catalog(id) ON DELETE SET NULL;")
    if not _has_column(cursor, "manual_intake", "origin_root_id"):
        cursor.execute("ALTER TABLE manual_intake ADD COLUMN origin_root_id INTEGER REFERENCES manual_intake(id) ON DELETE SET NULL;")
    if not _has_column(cursor, "recipe", "origin_root_id"):
        cursor.execute("ALTER TABLE recipe ADD COLUMN origin_root_id INTEGER REFERENCES recipe(id) ON DELETE SET NULL;")
    # Canonical index name (§11.7): rename the older name once, before creating.
    if (
        _index_exists(cursor, "idx_catalog_origin_root")
        and not _index_exists(cursor, "idx_catalog_origin_root_id")
    ):
        cursor.execute("ALTER INDEX idx_catalog_origin_root RENAME TO idx_catalog_origin_root_id;")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_origin_root_id ON catalog (origin_root_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_origin_root ON manual_intake (origin_root_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_origin_root ON recipe (origin_root_id);")


def _index_exists(cursor, name: str) -> bool:
    cursor.execute(
        "SELECT 1 AS ok FROM pg_indexes WHERE schemaname = 'public' AND indexname = %(name)s;",
        {"name": name},
    )
    return cursor.fetchone() is not None
def _ensure_trgm_search(cursor):
    # Tolerated on purpose: `_build_fuzzy_search` falls back to ILIKE + regexp
    # when `pg_trgm` is missing (`_pg_trgm_enabled`), so search keeps working
    # and no uniqueness depends on these indexes (§12.5, feedback 19).
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
            "CREATE INDEX IF NOT EXISTS idx_food_brands_label_trgm "
            "ON food_brands USING gin (lower(label) gin_trgm_ops);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_manual_origin_trgm "
            "ON manual_intake USING gin (lower(origin) gin_trgm_ops);"
        )
        cursor.execute("RELEASE SAVEPOINT trgm_setup;")
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT trgm_setup;")
        cursor.execute("RELEASE SAVEPOINT trgm_setup;")
        logger.warning("pg_trgm setup skipped: %s", exc)


def _ensure_food_filter_indexes(cursor):
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_created_by ON catalog (created_by);")
    # idx_catalog_visibility is dropped and not recreated: no real query uses it
    # (0 scans) and the partial unique indexes cover the visibility filter.
    cursor.execute("DROP INDEX IF EXISTS idx_catalog_visibility;")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_deleted_at ON catalog (deleted_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_created_by ON manual_intake (created_by);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_visibility ON manual_intake (is_published, created_by);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_users_id ON recipe (users_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipe_visibility ON recipe (is_published, users_id);")


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
    # manual_intake only now: its audit keeps this helper (and the tolerated
    # savepoint, §12.5) until it is rewritten. catalog's uniqueness lives in
    # _ensure_catalog_schema with partial indexes (feedback 2, H2).
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
            CREATE UNIQUE INDEX IF NOT EXISTS uq_manual_created_name_origin_norm
            ON manual_intake (created_by, lower(trim(name)), lower(trim(COALESCE(origin, ''))));
            """
        )
        cursor.execute("RELEASE SAVEPOINT food_name_origin_uniqueness;")
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT food_name_origin_uniqueness;")
        cursor.execute("RELEASE SAVEPOINT food_name_origin_uniqueness;")
        logger.warning("food uniqueness migration skipped: %s", exc)



def _ensure_food_brands_schema(cursor):
    """Migrate food_brands schema from legacy (name) to new (code, label, is_active, created_by, updated_at)."""
    
    # (A) food_brands: new shape
    if _has_column(cursor, "food_brands", "name"):
        cursor.execute("ALTER TABLE food_brands RENAME COLUMN name TO label;")
    
    cursor.execute("ALTER TABLE food_brands ADD COLUMN IF NOT EXISTS code VARCHAR(255);")
    cursor.execute("ALTER TABLE food_brands ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;")
    cursor.execute("ALTER TABLE food_brands ADD COLUMN IF NOT EXISTS created_by INTEGER;")
    cursor.execute("ALTER TABLE food_brands ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;")
    
    cursor.execute(
        """
        ALTER TABLE food_brands
            ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';
        """
    )
    
    # Populate code from label
    cursor.execute(
        r"""
        UPDATE food_brands
        SET code = regexp_replace(btrim(lower(label)), '\s+', ' ', 'g')
        WHERE code IS NULL;
        """
    )
    
    # (B) Deduplication by code
    cursor.execute(
        """
        DELETE FROM food_brands a USING food_brands b
        WHERE a.code = b.code AND a.id > b.id;
        """
    )
    
    cursor.execute("ALTER TABLE food_brands ALTER COLUMN code SET NOT NULL;")
    cursor.execute("ALTER TABLE food_brands ALTER COLUMN label SET NOT NULL;")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_food_brands_code ON food_brands (code);")
    
    # Drop legacy unique constraint on name/label if exists
    cursor.execute(
        """
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'food_brands'
          AND con.contype = 'u'
          AND pg_get_constraintdef(con.oid) ILIKE 'UNIQUE (label)%';
        """
    )
    for row in cursor.fetchall() or []:
        legacy_constraint = row.get("conname")
        if legacy_constraint:
            cursor.execute(f'ALTER TABLE food_brands DROP CONSTRAINT IF EXISTS "{legacy_constraint}";')
    
    # Add constraints if they don't exist
    cursor.execute(
        """
        SELECT con.conname
        FROM pg_constraint con
        WHERE con.conname = 'fk_food_brands_created_by_users';
        """
    )
    if not cursor.fetchone():
        cursor.execute(
            """
            ALTER TABLE food_brands
            ADD CONSTRAINT fk_food_brands_created_by_users
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;
            """
        )
    
    cursor.execute(
        """
        SELECT con.conname
        FROM pg_constraint con
        WHERE con.conname = 'ck_food_brands_code_normalized';
        """
    )
    if not cursor.fetchone():
        cursor.execute(
            r"""
            ALTER TABLE food_brands
            ADD CONSTRAINT ck_food_brands_code_normalized
                CHECK (code = regexp_replace(btrim(lower(code)), '\s+', ' ', 'g'));
            """
        )
    
    cursor.execute(
        """
        SELECT con.conname
        FROM pg_constraint con
        WHERE con.conname = 'ck_food_brands_label_not_blank';
        """
    )
    if not cursor.fetchone():
        cursor.execute(
            """
            ALTER TABLE food_brands
            ADD CONSTRAINT ck_food_brands_label_not_blank
                CHECK (btrim(label) <> '');
            """
        )
    
    # (C) catalog.brand_id
    cursor.execute("ALTER TABLE catalog ADD COLUMN IF NOT EXISTS brand_id INTEGER;")
    
    # (D)-(F) only apply while catalog.brand exists: a previous run of this same
    # bootstrap may already have migrated and dropped the column (step H), and
    # these statements are not valid over a column that no longer exists.
    if _has_column(cursor, "catalog", "brand"):
        # (D) High of brands that only exist in catalog
        cursor.execute(
            r"""
            WITH raw AS (
                SELECT regexp_replace(btrim(lower(brand)), '\s+', ' ', 'g') AS code,
                       btrim(regexp_replace(brand, '\s+', ' ', 'g'))        AS label,
                       count(*) AS uses, min(id) AS first_id
                FROM catalog
                WHERE brand IS NOT NULL AND btrim(brand) <> ''
                GROUP BY 1, 2
            ), chosen AS (
                SELECT DISTINCT ON (code) code, label
                FROM raw
                ORDER BY code, uses DESC, first_id ASC
            )
            INSERT INTO food_brands (code, label, created_at, updated_at)
            SELECT code, label, NOW(), NOW() FROM chosen
            ON CONFLICT (code) DO NOTHING;
            """
        )

        # (E) Populate the FK
        cursor.execute(
            r"""
            UPDATE catalog c
            SET brand_id = fb.id
            FROM food_brands fb
            WHERE c.brand_id IS NULL
              AND c.brand IS NOT NULL AND btrim(c.brand) <> ''
              AND fb.code = regexp_replace(btrim(lower(c.brand)), '\s+', ' ', 'g');
            """
        )

        # (F) Hard verification before destroying
        cursor.execute(
            """
            SELECT count(*) AS orphaned FROM catalog
            WHERE brand IS NOT NULL AND btrim(brand) <> '' AND brand_id IS NULL;
            """
        )
        orphaned = cursor.fetchone()["orphaned"]
        if orphaned > 0:
            raise ValueError(
                f"Migration failed: {orphaned} rows in catalog have brand text but no brand_id. "
                "This indicates a bug in the migration logic."
            )

    # (G) Integrity and indexes
    cursor.execute(
        """
        SELECT con.conname
        FROM pg_constraint con
        WHERE con.conname = 'fk_catalog_brand_id_food_brands';
        """
    )
    if not cursor.fetchone():
        cursor.execute(
            """
            ALTER TABLE catalog ADD CONSTRAINT fk_catalog_brand_id_food_brands
                FOREIGN KEY (brand_id) REFERENCES food_brands(id) ON DELETE SET NULL;
            """
        )
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_brand_id ON catalog (brand_id);")

    # Replace the old uniqueness constraint. uq_catalog_name_brand_id_norm is NOT
    # created here anymore: it is dropped and replaced by the partial indexes of
    # _ensure_catalog_schema (H2). A global non-partial index would fail as soon
    # as two personal foods of different owners share a name, and would abort
    # startup.
    cursor.execute("DROP INDEX IF EXISTS uq_catalog_name_brand_norm;")
    cursor.execute("DROP INDEX IF EXISTS idx_catalog_brand_trgm;")
    
    # (H) Destruction of the column, at last
    cursor.execute("ALTER TABLE catalog DROP COLUMN IF EXISTS brand;")


# Constraints that this bootstrap declares as canonical for insulin_injections
# (§11.6). Any CHECK or FK of the table that is not here is dropped in
# _ensure_insulin_injections_schema: the bootstrap is the only source of the
# schema (§12.1).
_CANONICAL_INJECTION_CONSTRAINTS = (
    "fk_insulin_injections_users_id_users",
    "fk_insulin_injections_intake_event_id_intake_event",
    "ck_insulin_injections_insulin_type",
    "ck_insulin_injections_injection_zone",
    "ck_insulin_injections_units_by_type",     # H5: coherence rule by type
    "ck_insulin_injections_units_step",        # H5: multiples of 0.5 U
)


# Renames of inherited constraints to the canonical names of §11.6.
# They only rename: the CHECK definition does not change.
_INTAKE_EVENT_CONSTRAINT_RENAMES = {
    "intake_event_users_id_fkey": "fk_intake_event_users_id_users",
    "intake_event_amount_confidence_check": "ck_intake_event_amount_confidence",
    "intake_event_quality_confidence_check": "ck_intake_event_quality_confidence",
    "intake_event_carbs_uncertainty_check": "ck_intake_event_carbs_uncertainty",
    "intake_event_sugars_uncertainty_check": "ck_intake_event_sugars_uncertainty",
    "intake_event_fats_uncertainty_check": "ck_intake_event_fats_uncertainty",
    "intake_event_saturated_uncertainty_check": "ck_intake_event_saturated_uncertainty",
    "intake_event_proteins_uncertainty_check": "ck_intake_event_proteins_uncertainty",
    "intake_event_fiber_uncertainty_check": "ck_intake_event_fiber_uncertainty",
}


def _constraint_exists(cursor, table: str, name: str) -> bool:
    cursor.execute(
        "SELECT 1 AS ok FROM pg_constraint "
        "WHERE conrelid = %(table)s::regclass AND conname = %(name)s;",
        {"table": f"public.{table}", "name": name},
    )
    return cursor.fetchone() is not None


def _ensure_intake_event_schema(cursor):
    """intake_event: timestamps, soft-delete, TIMESTAMPTZ, NOT NULL, constraints and index.

    Closes findings 3 (deleted_at), 4, 7, 8 and 9 of
    audit/audit_intake_event.md. Idempotent (§12.2).
    """
    state_list = sql_in_list(IntakeEventState)
    meal_type_list = sql_in_list(MealType)

    # ---- H4 / H3: audit and soft-delete columns (nullable first) ----
    cursor.execute("ALTER TABLE intake_event ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE intake_event ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE intake_event ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE intake_event ADD COLUMN IF NOT EXISTS timezone_at_event TEXT;")

    # ---- H7: meal_time TIMESTAMP naive-UTC -> TIMESTAMPTZ (§10.5) ----
    # The DEFAULT is dropped before ALTER TYPE: PostgreSQL cannot automatically
    # convert a timestamp default to timestamptz and would abort.
    data_type = (_column_data_type(cursor, "intake_event", "meal_time") or "").lower()
    if data_type == "timestamp without time zone":
        cursor.execute("ALTER TABLE intake_event ALTER COLUMN meal_time DROP DEFAULT;")
        cursor.execute(
            "ALTER TABLE intake_event "
            "ALTER COLUMN meal_time TYPE TIMESTAMPTZ USING meal_time AT TIME ZONE 'UTC';"
        )
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN meal_time SET DEFAULT CURRENT_TIMESTAMP;")

    # ---- Technical backfill of the new columns ----
    # It changes no existing data: it only fills columns that did not exist
    # before (decision 2026-09-08 about historical data).
    cursor.execute(
        "UPDATE intake_event "
        "SET created_at = COALESCE(created_at, meal_time, CURRENT_TIMESTAMP);"
    )
    cursor.execute("UPDATE intake_event SET updated_at = COALESCE(updated_at, created_at);")
    cursor.execute(
        "UPDATE intake_event SET timezone_at_event = COALESCE(timezone_at_event, 'Europe/Madrid');"
    )

    # ---- Defaults and NOT NULL ----
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN updated_at SET NOT NULL;")
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN timezone_at_event SET DEFAULT 'Europe/Madrid';")
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN timezone_at_event SET NOT NULL;")
    # deleted_at stays nullable: NULL = active (§11.3).

    # ---- H8: users_id NOT NULL ----
    # Verified on 2026-09-08: 0 rows with users_id NULL. If any appeared, this
    # ALTER would fail and abort the whole bootstrap (§12.5), which is correct.
    cursor.execute("ALTER TABLE intake_event ALTER COLUMN users_id SET NOT NULL;")

    # ---- H8: canonical names (§11.6) ----
    for old_name, new_name in _INTAKE_EVENT_CONSTRAINT_RENAMES.items():
        if _constraint_exists(cursor, "intake_event", old_name) and not _constraint_exists(
            cursor, "intake_event", new_name
        ):
            cursor.execute(
                sql.SQL("ALTER TABLE intake_event RENAME CONSTRAINT {} TO {};").format(
                    sql.Identifier(old_name), sql.Identifier(new_name)
                )
            )

    # state and meal_type are not renamed: they are regenerated from the enums (§4.4).
    cursor.execute("ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS intake_event_state_check;")
    cursor.execute("ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS ck_intake_event_state;")
    cursor.execute(
        f"ALTER TABLE intake_event ADD CONSTRAINT ck_intake_event_state "
        f"CHECK (state IN ({state_list}));"
    )
    cursor.execute("ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS intake_event_meal_type_check;")
    cursor.execute("ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS ck_intake_event_meal_type;")
    cursor.execute(
        f"ALTER TABLE intake_event ADD CONSTRAINT ck_intake_event_meal_type "
        f"CHECK (meal_type IS NULL OR meal_type IN ({meal_type_list}));"
    )

    # ---- H9: partial index for the real filter of every list (§11.7) ----
    cursor.execute("DROP INDEX IF EXISTS idx_intake_event_users_id_state_meal_time;")
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_intake_event_users_id_state_meal_time
        ON intake_event (users_id, state, meal_time DESC, id DESC)
        WHERE deleted_at IS NULL;
        """
    )

    # ---- total_amount is no longer persisted: it is computed live (decision 2026-09-10) ----
    cursor.execute("ALTER TABLE intake_event DROP COLUMN IF EXISTS total_amount;")

    # ---- H32/H35: ingested_amount with sanity limits (measurement_conventions.md
    # §6.9.2, decision 2026-09-10). Verified on 2026-09-09: 0 rows negative or out
    # of range; if any appeared, this ALTER would fail and abort the bootstrap,
    # which is correct (§12.5). ----
    cursor.execute("ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS ck_intake_event_ingested_amount;")
    cursor.execute(
        "ALTER TABLE intake_event ADD CONSTRAINT ck_intake_event_ingested_amount "
        "CHECK (ingested_amount IS NULL OR (ingested_amount >= 0 AND ingested_amount <= 100000));"
    )


def _ensure_portion_detail_schema(cursor):
    """portion_detail: evolutionary table hook (§12.1).

    It was the only large table without its own hook, so the DDL applied by hand
    to the existing database stayed out of the code (finding 16 of
    audit/audit_portion_detail.md). Idempotent (§12.2).
    """
    # ---- H16: split_group_id was hand-applied DDL that never returned to code ----
    # varchar(64), 0 rows with a value, 0 references in the code, 0 commits. The
    # plates design (decision 2026-09-19) relies on intake_plate, not here.
    cursor.execute("ALTER TABLE portion_detail DROP COLUMN IF EXISTS split_group_id;")

    # ---- T1.2: blocking pre-checks before writing the new CHECKs (decision 2026-09-22) ----
    # The amount check can only run while amount_g still exists; after T1.3 the
    # column is unreachable. Both checks abort the bootstrap instead of cleaning
    # data (§12.5, §12.7): a pre-existing row that violates the new rule is a data
    # decision, not something a migration may silently rewrite.
    if _column_data_type(cursor, "portion_detail", "amount_g") is not None:
        cursor.execute(
            """
            SELECT count(*) AS zero_rows
            FROM portion_detail
            WHERE COALESCE(plate_amount, amount_g) = 0;
            """
        )
        zero_rows = cursor.fetchone()["zero_rows"]
        if zero_rows:
            raise RuntimeError(
                f"{zero_rows} portion_detail rows have amount 0; the new "
                "ck_portion_detail_amount_range (amount > 0) cannot be created. "
                "This needs an explicit data decision (code_conventions.md 12.7)."
            )

    cursor.execute(
        """
        SELECT count(*) AS out_of_range
        FROM portion_detail
        WHERE offset_minutes IS NOT NULL
          AND (offset_minutes < -300 OR offset_minutes > 300);
        """
    )
    out_of_range = cursor.fetchone()["out_of_range"]
    if out_of_range:
        raise RuntimeError(
            f"{out_of_range} portion_detail rows have offset_minutes outside -300..300; "
            "ck_portion_detail_offset_minutes cannot be created."
        )

    # ---- Plates (servings) inside an event (decision 2026-09-19) ----
    # The column is born nullable on purpose: existing rows do not have a plate
    # yet and the CHECK that requires one is added at the end, after the data
    # migration.
    cursor.execute("ALTER TABLE portion_detail ADD COLUMN IF NOT EXISTS plate_id INTEGER;")

    if not _constraint_exists(cursor, "portion_detail", "fk_portion_detail_plate_id_intake_plate"):
        cursor.execute(
            "ALTER TABLE portion_detail "
            "ADD CONSTRAINT fk_portion_detail_plate_id_intake_plate "
            "FOREIGN KEY (plate_id) REFERENCES intake_plate(id) ON DELETE RESTRICT;"
        )

    # Migration (measurement_conventions.md §4.6.6): one plate per event having
    # portions without one, with name NULL —the name is derived from its
    # ingredients— and the smallest offset of its rows. Idempotent: it only looks
    # at event portions that do not belong to a plate yet.
    cursor.execute(
        """
        INSERT INTO intake_plate (intake_event_id, name, offset_minutes)
        SELECT pd.intake_event_id, NULL, MIN(pd.offset_minutes)
        FROM portion_detail pd
        WHERE pd.intake_event_id IS NOT NULL AND pd.plate_id IS NULL
        GROUP BY pd.intake_event_id;
        """
    )
    cursor.execute(
        """
        UPDATE portion_detail pd
        SET plate_id = ip.id
        FROM intake_plate ip
        WHERE pd.intake_event_id = ip.intake_event_id
          AND pd.plate_id IS NULL;
        """
    )

    # Migration postcondition before declaring it in the database (§12.5): a
    # single mismatched row would make the CHECK fail halfway and leave the
    # bootstrap in a worse state than the initial one.
    cursor.execute(
        """
        SELECT count(*) AS pending
        FROM portion_detail
        WHERE (intake_event_id IS NULL) <> (plate_id IS NULL);
        """
    )
    pending = cursor.fetchone()["pending"]
    if pending:
        raise RuntimeError(
            f"Incomplete plate migration: {pending} portion_detail rows without "
            "a matching pair of intake_event_id and plate_id."
        )

    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_plate_only_for_event"):
        cursor.execute(
            "ALTER TABLE portion_detail "
            "ADD CONSTRAINT ck_portion_detail_plate_only_for_event "
            "CHECK ((intake_event_id IS NULL) = (plate_id IS NULL));"
        )

    # Indexes for the two new foreign keys (§11.7): the cart reads portions by
    # plate and plates by event on every render.
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_portion_detail_plate_id ON portion_detail (plate_id);"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_intake_plate_intake_event_id "
        "ON intake_plate (intake_event_id);"
    )

    # ---- T1.4: offset_minutes range CHECK (finding 9) ----
    # Same name and rule as ck_intake_plate_offset_minutes, already present: the
    # template cannot accept values that the row would reject (measurement
    # conventions.md 4.6.2).
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_offset_minutes"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_offset_minutes "
            "CHECK (offset_minutes IS NULL OR (offset_minutes >= -300 AND offset_minutes <= 300));"
        )

    # ---- T1.5: created_at / updated_at (finding 11, decision 2026-09-22) ----
    # Technical backfill (§12.7): the event date is the closest thing to "when
    # this portion was added". Recipe portions have no source and get the
    # migration instant. No actor column (decision 2026-09-22).
    cursor.execute("ALTER TABLE portion_detail ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE portion_detail ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;")
    cursor.execute(
        """
        UPDATE portion_detail pd
        SET created_at = COALESCE(pd.created_at, ie.meal_time, ie.created_at, CURRENT_TIMESTAMP)
        FROM intake_event ie
        WHERE ie.id = pd.intake_event_id AND pd.created_at IS NULL;
        """
    )
    cursor.execute("UPDATE portion_detail SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL;")
    cursor.execute("UPDATE portion_detail SET updated_at = created_at WHERE updated_at IS NULL;")
    cursor.execute("ALTER TABLE portion_detail ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE portion_detail ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE portion_detail ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE portion_detail ALTER COLUMN updated_at SET NOT NULL;")

    # ---- T1.3: single amount column (findings 2, 14, 26; decisions 2026-09-18 and 2026-09-22) ----
    # amount = COALESCE(plate_amount, amount_g) is exactly what every read already
    # computed (portion_intake_amount, the COALESCE of scale_event_portion_amounts,
    # group_portions): it asserts nothing new about historical meals, it freezes in
    # the data what the code already did. The rename breaks any unmigrated read on
    # purpose (decision 2026-09-18), which is why T2/T3 must ship in the same cycle.
    # This must run before the duplicate consolidation below, which from now on
    # sums `amount`. Destructive migration (§12.4): the two columns are dropped in
    # the same transaction as the backfill, all or nothing.
    if _column_data_type(cursor, "portion_detail", "amount") is None:
        cursor.execute("ALTER TABLE portion_detail ADD COLUMN amount REAL;")
    if _column_data_type(cursor, "portion_detail", "amount_g") is not None:
        cursor.execute(
            "UPDATE portion_detail SET amount = COALESCE(plate_amount, amount_g) "
            "WHERE amount IS NULL;"
        )
        cursor.execute("ALTER TABLE portion_detail DROP COLUMN plate_amount;")
        cursor.execute("ALTER TABLE portion_detail DROP COLUMN amount_g;")
    cursor.execute("ALTER TABLE portion_detail ALTER COLUMN amount SET NOT NULL;")

    # ---- Uniqueness of a food inside a plate (measurement §4.6.4) ----
    # Prior consolidation of historical duplicates (§4.6.6, §12.7): the constraint
    # cannot be created over data that already violates it. Same merge rule the
    # insert will apply: amounts are summed and the rest of the fields are those
    # of the oldest row of the group.
    _DUPLICATE_PORTION_GROUPS = """
        WITH dup AS (
            SELECT
                min(id) AS keep_id,
                array_agg(id) AS ids,
                sum(amount) AS total_amount
            FROM portion_detail
            WHERE plate_id IS NOT NULL
            GROUP BY plate_id, catalog_id, manual_intake_id, cooking, conservation, final_state, is_cooked_weight
            HAVING count(*) > 1
        )
    """
    cursor.execute(
        _DUPLICATE_PORTION_GROUPS
        + """
        UPDATE portion_detail pd
        SET amount = dup.total_amount
        FROM dup
        WHERE pd.id = dup.keep_id;
        """
    )
    cursor.execute(
        _DUPLICATE_PORTION_GROUPS
        + """
        DELETE FROM portion_detail pd
        USING dup
        WHERE pd.id = ANY(dup.ids) AND pd.id <> dup.keep_id;
        """
    )

    # PARTIAL unique index, not a table constraint: plate_id is NULL in recipe
    # and fridge portions, and with NULLS NOT DISTINCT those nulls would be
    # considered equal to each other, so the same food with the same preparation
    # in two different recipes would clash as a false duplicate. Uniqueness is
    # inside the plate (§4.6.4). is_cooked_weight is part of the key since
    # 2026-09-23: the same grams weighed raw and weighed cooked are different
    # amounts of food, so they are separate rows. The old index without it is
    # dropped, otherwise it would keep rejecting that pair.
    cursor.execute("DROP INDEX IF EXISTS uq_portion_detail_plate_origin_preparation;")
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_portion_detail_plate_origin_preparation_cooked
        ON portion_detail (plate_id, catalog_id, manual_intake_id, cooking, conservation, final_state, is_cooked_weight)
        NULLS NOT DISTINCT
        WHERE plate_id IS NOT NULL;
        """
    )

    # ---- T1.3: amount range CHECK, after the consolidation above ----
    # NaN and Infinity are rejected by this same CHECK: in PostgreSQL NaN is
    # greater than any value in real, so NaN <= 100000 is false, and Infinity is
    # not finite either. No separate amount <> 'NaN'::real is needed.
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_amount_range"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_amount_range "
            "CHECK (amount > 0 AND amount <= 100000);"
        )

    # ---- T1.6: canonical constraint names (§11.6, finding 17) ----
    # The audit list predates the plates work and finding 2, so the rule is
    # derived from the live schema by reading each constraint definition instead
    # of trusting that list. Constraints whose name does not start with
    # portion_detail_ (those born with the plates work or created by T1.3/T1.4)
    # are already canonical and never enter the loop.
    _PORTION_DETAIL_CONSTRAINT_RULES = (
        ("num_nonnulls(catalog_id, manual_intake_id)", "ck_portion_detail_single_origin"),
        ("num_nonnulls(intake_event_id, fridge_id, recipe_id)", "ck_portion_detail_single_destination"),
        ("offset_minutes IS NULL", "ck_portion_detail_offset_only_for_event"),
    )
    _PORTION_DETAIL_FK_RENAMES = {
        "portion_detail_catalog_id_fkey": "fk_portion_detail_catalog_id_catalog",
        "portion_detail_manual_intake_id_fkey": "fk_portion_detail_manual_intake_id_manual_intake",
        "portion_detail_intake_event_id_fkey": "fk_portion_detail_intake_event_id_intake_event",
        "portion_detail_recipe_id_fkey": "fk_portion_detail_recipe_id_recipe",
        "portion_detail_fridge_id_fkey": "fk_portion_detail_fridge_id_fridge",
        "portion_detail_pkey": "pk_portion_detail",
    }
    cursor.execute(
        """
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = 'public.portion_detail'::regclass
          AND (conname LIKE 'portion\\_detail\\_%' ESCAPE '\\');
        """
    )
    for row in cursor.fetchall() or []:
        old_name = row["conname"]
        definition = row["definition"] or ""
        new_name = _PORTION_DETAIL_FK_RENAMES.get(old_name)
        if new_name is None:
            for needle, candidate in _PORTION_DETAIL_CONSTRAINT_RULES:
                if needle in definition:
                    new_name = candidate
                    break
        if not new_name:
            # Renaming blindly a rule that has not been identified is worse than
            # leaving it: register it and move on.
            logger.warning(
                "portion_detail: constraint %s does not match any rename rule; "
                "left as is. definition=%s",
                old_name,
                definition,
            )
            continue
        if _constraint_exists(cursor, "portion_detail", new_name):
            continue
        cursor.execute(
            sql.SQL("ALTER TABLE portion_detail RENAME CONSTRAINT {} TO {};").format(
                sql.Identifier(old_name), sql.Identifier(new_name)
            )
        )

    # ---- T1.7: FK indexes (finding 18) ----
    # The four are needed: intake_event_id filters the two list reads and is the
    # target of the event ON DELETE CASCADE; recipe_id filters recipe reads;
    # catalog_id and manual_intake_id are checked by RESTRICT on every food
    # delete, and the partial unique index does not serve them because plate_id
    # comes first.
    for column in ("intake_event_id", "recipe_id", "catalog_id", "manual_intake_id"):
        cursor.execute(
            sql.SQL("CREATE INDEX IF NOT EXISTS {} ON portion_detail ({});").format(
                sql.Identifier(f"idx_portion_detail_{column}"), sql.Identifier(column)
            )
        )
    # Redundant with uq_portion_detail_plate_origin_preparation_cooked, whose first
    # column is plate_id: same prefix, same use (§11.7). The index is created
    # earlier in this same hook and dropped here.
    cursor.execute("DROP INDEX IF EXISTS idx_portion_detail_plate_id;")

    # ---- Preparation fields as closed sets (H12, decision 2026-09-25) ----
    # Blocking pre-check (feedback 12: fail, never correct). The values come from
    # the code enums, not from a request (sql_in_list, §11.9).
    for column, enum_cls in (
        ("cooking", CookingMethod),
        ("conservation", ConservationMethod),
        ("final_state", FoodPhysicalState),
    ):
        name = f"ck_portion_detail_{column}"
        values = sql_in_list(enum_cls)
        cursor.execute(
            sql.SQL(
                "SELECT count(*) AS bad FROM portion_detail "
                "WHERE {column} IS NOT NULL AND {column} NOT IN (" + values + ");"
            ).format(column=sql.Identifier(column))
        )
        if cursor.fetchone()["bad"]:
            raise RuntimeError(
                f"portion_detail.{column} has values outside {enum_cls.__name__}; "
                f"{name} cannot be created (code_conventions.md 12.7)."
            )
        cursor.execute(
            sql.SQL("ALTER TABLE portion_detail DROP CONSTRAINT IF EXISTS {};").format(
                sql.Identifier(name)
            )
        )
        cursor.execute(
            sql.SQL(
                "ALTER TABLE portion_detail ADD CONSTRAINT {} "
                "CHECK ({column} IS NULL OR {column} IN (" + values + "));"
            ).format(sql.Identifier(name), column=sql.Identifier(column))
        )


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

    insulin_type_list = sql_in_list(InsulinType)
    injection_zone_list = sql_in_list(InjectionZone)

    cursor.execute(
        """
        ALTER TABLE intake_event
        ADD COLUMN IF NOT EXISTS injection_zone VARCHAR(50);
        """
    )
    cursor.execute(
        f"""
        ALTER TABLE intake_event DROP CONSTRAINT IF EXISTS ck_intake_event_injection_zone;
        ALTER TABLE intake_event
        ADD CONSTRAINT ck_intake_event_injection_zone
        CHECK (injection_zone IS NULL OR injection_zone IN ({injection_zone_list}));
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS insulin_injections (
            id SERIAL PRIMARY KEY,
            users_id INTEGER,
            intake_event_id INTEGER,
            shot_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            insulin_type VARCHAR(20),
            units REAL,
            injection_zone VARCHAR(50),
            notes TEXT,
            needle_leak BOOLEAN,
            skin_pinch BOOLEAN,
            created_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ,
            timezone_at_event TEXT,
            CONSTRAINT fk_insulin_injections_users_id_users
                FOREIGN KEY (users_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_insulin_injections_intake_event_id_intake_event
                FOREIGN KEY (intake_event_id) REFERENCES intake_event(id) ON DELETE SET NULL,
            CONSTRAINT ck_insulin_injections_insulin_type
                CHECK (insulin_type IN ({insulin_type_list})),
            CONSTRAINT ck_insulin_injections_units_by_type
                CHECK (
                    (insulin_type = 'basal' AND units IS NOT NULL AND units > 0)
                    OR (insulin_type = 'rapid' AND (units IS NULL OR units > 0))
                ),
            CONSTRAINT ck_insulin_injections_units_step
                CHECK (units IS NULL OR (units * 2) = floor(units * 2)),
            CONSTRAINT ck_insulin_injections_injection_zone
                CHECK (injection_zone IS NULL OR injection_zone IN ({injection_zone_list}))
        );
        """
    )

    # Merge of the legacy tables (§12.2). It runs right after CREATE TABLE and
    # before H4/H5 so that the migrated rows receive the same timestamp backfill
    # and are validated by the canonical constraints like any other row.
    # The physical name of the dose column depends on each database's history:
    # legacy table -> basal_units; table created by this bootstrap -> units.
    for legacy_table in ("injection_zone", "injection_zones"):
        cursor.execute("SELECT to_regclass(%s) AS reg;", (f"public.{legacy_table}",))
        if (cursor.fetchone() or {}).get("reg") is None:
            continue
        source_units = "basal_units" if _has_column(cursor, legacy_table, "basal_units") else "units"
        target_units = "basal_units" if _has_column(cursor, "insulin_injections", "basal_units") else "units"
        cursor.execute(
            sql.SQL(
                """
                INSERT INTO insulin_injections
                    (id, users_id, intake_event_id, shot_time, insulin_type, {target}, injection_zone)
                SELECT id, users_id, intake_event_id, shot_time, insulin_type, {source}, injection_zone
                FROM {legacy}
                ON CONFLICT (id) DO NOTHING;
                """
            ).format(
                target=sql.Identifier(target_units),
                source=sql.Identifier(source_units),
                legacy=sql.Identifier(legacy_table),
            )
        )
        cursor.execute(
            "SELECT setval('insulin_injections_id_seq', "
            "COALESCE((SELECT MAX(id) FROM insulin_injections), 1), true);"
        )
        cursor.execute(sql.SQL("DROP TABLE {};").format(sql.Identifier(legacy_table)))

    # ========== H4: TIMESTAMPTZ and audit timestamps ==========
    # 1) New columns (nullable first)
    cursor.execute("ALTER TABLE insulin_injections ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE insulin_injections ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;")
    cursor.execute("ALTER TABLE insulin_injections ADD COLUMN IF NOT EXISTS timezone_at_event TEXT;")

    # 2) Convert shot_time to TIMESTAMPTZ (only if it is still naive)
    data_type = (_column_data_type(cursor, "insulin_injections", "shot_time") or "").lower()
    if data_type == "timestamp without time zone":
        cursor.execute(
            "ALTER TABLE insulin_injections "
            "ALTER COLUMN shot_time TYPE TIMESTAMPTZ USING shot_time AT TIME ZONE 'UTC';"
        )

    # 3) Timestamp backfill
    cursor.execute("UPDATE insulin_injections SET created_at = COALESCE(created_at, shot_time, CURRENT_TIMESTAMP);")
    cursor.execute("UPDATE insulin_injections SET updated_at = COALESCE(updated_at, created_at);")
    cursor.execute("UPDATE insulin_injections SET timezone_at_event = COALESCE(timezone_at_event, 'Europe/Madrid');")

    # 4) Defaults and NOT NULL
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN updated_at SET NOT NULL;")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN timezone_at_event SET DEFAULT 'Europe/Madrid';")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN timezone_at_event SET NOT NULL;")

    # ========== H5: rename basal_units -> units, add NOT NULL ==========
    # Rename the column
    if _has_column(cursor, "insulin_injections", "basal_units") and not _has_column(cursor, "insulin_injections", "units"):
        cursor.execute("ALTER TABLE insulin_injections RENAME COLUMN basal_units TO units;")

    # NOT NULL on users_id and insulin_type
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN users_id SET NOT NULL;")
    cursor.execute("ALTER TABLE insulin_injections ALTER COLUMN insulin_type SET NOT NULL;")

    # Constraint convergence (§12.2): any CHECK or FK of the table whose name is
    # not canonical is dropped — both those inherited from
    # injection_zone/injection_zones and those auto-generated by PostgreSQL in
    # earlier clean installs (insulin_injections_*_check, *_fkey). PRIMARY KEY and
    # UNIQUE ('p', 'u') are excluded; they are handled by rename further below.
    cursor.execute(
        """
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'public.insulin_injections'::regclass
          AND contype IN ('c', 'f')
          AND conname <> ALL(%(canonical)s)
        """,
        {"canonical": list(_CANONICAL_INJECTION_CONSTRAINTS)},
    )
    for row in cursor.fetchall():
        cursor.execute(
            sql.SQL("ALTER TABLE insulin_injections DROP CONSTRAINT IF EXISTS {}").format(
                sql.Identifier(row["conname"])
            )
        )

    # Rename PK and sequence to canonical names if they exist under inherited names (§12.2)
    cursor.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'injection_zone_pkey') THEN
                ALTER TABLE insulin_injections RENAME CONSTRAINT injection_zone_pkey TO insulin_injections_pkey;
            END IF;
            IF to_regclass('public.injection_zone_id_seq') IS NOT NULL
               AND to_regclass('public.insulin_injections_id_seq') IS NULL THEN
                ALTER SEQUENCE injection_zone_id_seq RENAME TO insulin_injections_id_seq;
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
                WHERE conname = 'fk_insulin_injections_intake_event_id_intake_event'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT fk_insulin_injections_intake_event_id_intake_event
                FOREIGN KEY (intake_event_id) REFERENCES intake_event(id) ON DELETE SET NULL;
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
                WHERE conname = 'fk_insulin_injections_users_id_users'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT fk_insulin_injections_users_id_users
                FOREIGN KEY (users_id) REFERENCES users(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )
    cursor.execute(
        f"""
        ALTER TABLE insulin_injections DROP CONSTRAINT IF EXISTS ck_insulin_injections_insulin_type;
        ALTER TABLE insulin_injections
        ADD CONSTRAINT ck_insulin_injections_insulin_type
        CHECK (insulin_type IN ({insulin_type_list}));
        """
    )
    cursor.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_insulin_injections_units_by_type'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT ck_insulin_injections_units_by_type
                CHECK (
                    (insulin_type = 'basal' AND units IS NOT NULL AND units > 0)
                    OR (insulin_type = 'rapid' AND (units IS NULL OR units > 0))
                );
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
                WHERE conname = 'ck_insulin_injections_units_step'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT ck_insulin_injections_units_step
                CHECK (units IS NULL OR (units * 2) = floor(units * 2));
            END IF;
        END $$;
        """
    )
    cursor.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_insulin_injections_injection_zone'
            ) THEN
                ALTER TABLE insulin_injections
                ADD CONSTRAINT ck_insulin_injections_injection_zone
                CHECK (injection_zone IS NULL OR injection_zone IN ({injection_zone_list}));
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


def init_db():
    conn = get_migrations_connection()
    cur = conn.cursor()
    try:
        # Transactional advisory lock (§12.5): avoids race conditions on
        # concurrent startups with DB_INIT_ON_STARTUP=true.
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (742001,))
        tables = [
            DBSchema.users,
            DBSchema.auth_sessions,
            DBSchema.auth_rate_limits,
            DBSchema.food_brands,
            DBSchema.catalog(),
            DBSchema.manual_intake,
            DBSchema.fridge,
            DBSchema.tags,
            DBSchema.recipe,
            DBSchema.user_favorites,
            DBSchema.linked_tags,
            DBSchema.intake_event(),
            DBSchema.insulin_injections(),
            DBSchema.meal_type_schedule(),
            DBSchema.intake_plate,
            DBSchema.portion_detail,
        ]

        for table_sql in tables:
            cur.execute(table_sql)

        _ensure_food_brands_schema(cur)
        _ensure_trgm_search(cur)
        _ensure_tags_color_schema(cur)
        _ensure_manual_intake_schema(cur)
        _ensure_food_name_origin_uniqueness(cur)
        _ensure_user_favorites_schema(cur)
        _ensure_copy_origin_schema(cur)
        _ensure_food_publication_schema(cur)
        _ensure_food_filter_indexes(cur)
        _ensure_catalog_schema(cur)
        _ensure_users_schema(cur)
        _ensure_auth_sessions_schema(cur)
        _ensure_auth_rate_limits_schema(cur)
        _ensure_intake_event_schema(cur)
        _ensure_insulin_injections_schema(cur)
        # After intake_event: portion_detail plates depend on it through a
        # foreign key, so their DDL cannot run earlier (§12.3).
        _ensure_portion_detail_schema(cur)
        _remove_legacy_user_sessions(cur)
        _remove_legacy_user_hidden_catalog(cur)
        _remove_legacy_user_columns(cur)
        _ensure_default_user(cur)

        # Grant DML to the runtime role (§12.6): created objects are owned by the
        # migrations identity, so the runtime would be left without permissions.
        role = sql.Identifier(DB_RUNTIME_ROLE)
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        cur.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}").format(role))
        cur.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(role))
        cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}").format(role))
        cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {}").format(role))

        conn.commit()
        logger.info("Database initialized successfully.")
    except Exception as e:
        conn.rollback()
        # Startup failure (section 12.5 of code_conventions.md): a failed
        # mandatory migration aborts startup, it does not continue as if the
        # schema were correct.
        logger.critical("Error initializing database: %s", e, exc_info=True)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    init_db()
