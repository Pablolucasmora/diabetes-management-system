"""Bootstrap of the foods: catalog, manual_intake, recipes, favorites, publication, tags, brands and the search indexes."""

import logging
import re
from psycopg import sql
from DayBetes_food.database.queries.crud import fuzzy_compact_sql
from DayBetes_food.database.schema import (
    catalog_check_constraints,
    manual_intake_check_constraints,
    recipe_check_constraints,
    tags_check_constraints,
)
from DayBetes_food.domain.catalog import CATALOG_BARCODE_MAX_LENGTH, CATALOG_BARCODE_MIN_LENGTH
from DayBetes_food.domain.search_text import search_text_sql
from DayBetes_food.domain.constants import FoodCategory, AmountMethod, MacrosSource, SystemTag
from DayBetes_food.domain.recipe import RECIPE_MEAL_TYPES
from DayBetes_food.domain.tag import SYSTEM_TAG_COLORS
from DayBetes_food.database.bootstrap.helpers import (
    _check_lacks_values,
    _column_data_type,
    _column_default,
    _column_is_nullable,
    _constraint_exists,
    _create_index_once,
    _create_unique_index_once,
    _has_column,
    _index_exists,
    _replace_boolean_with_list,
)

logger = logging.getLogger(__name__)


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
    # ---- 0. Prefill reference and search text (§11.7, measurement §12.1) ----
    # First: the canonical CHECKs of step 6c use these columns.
    if not _has_column(cursor, "catalog", "prefill_source"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN prefill_source VARCHAR(20);")
    if not _has_column(cursor, "catalog", "prefill_source_id"):
        cursor.execute("ALTER TABLE catalog ADD COLUMN prefill_source_id VARCHAR(64);")
    if not _has_column(cursor, "catalog", "search_name"):
        cursor.execute(
            f"ALTER TABLE catalog ADD COLUMN search_name TEXT "
            f"GENERATED ALWAYS AS ({search_text_sql('name')}) STORED;"
        )

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

    # ---- 5b. Declared confidence (decision 2026-10-09) and U1/U2 (2026-11-12) ----
    # Existing rows start as NULL ("no data"): nothing is inferred. The yes/no
    # macros_quality and default_strictly_weighed became closed lists (study §6.3).
    _replace_boolean_with_list(cursor, "catalog", "macros_quality", "macros_source", MacrosSource.LABEL.value)
    _replace_boolean_with_list(
        cursor, "catalog", "default_strictly_weighed", "default_amount_method", AmountMethod.KITCHEN_SCALE.value
    )
    for column, definition in (
        ("macros_confidence", "INTEGER"),
        # What the serving is (study §6.3, decision 2026-11-21); NULL = not said.
        ("serving_method", "VARCHAR(50)"),
    ):
        if not _has_column(cursor, "catalog", column):
            cursor.execute(
                sql.SQL("ALTER TABLE catalog ADD COLUMN {} {};").format(
                    sql.Identifier(column), sql.SQL(definition)
                )
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


_MANUAL_INTAKE_LEGACY_CHECKS = (
    "chk_manual_amount_g_valid",
    "chk_manual_calories_100g_valid",
    "chk_manual_carbs_100g_valid",
    "chk_manual_sugars_100g_valid",
    "chk_manual_fats_100g_valid",
    "chk_manual_saturated_100g_valid",
    "chk_manual_proteins_100g_valid",
    "chk_manual_fiber_100g_valid",
    "chk_manual_caffeine_valid",
    "chk_manual_alcohol_valid",
    "chk_manual_saturated_le_fats",
    "manual_intake_glycemic_index_check",
    "manual_intake_ig_confidence_check",
)

_MANUAL_INTAKE_CONSTRAINT_RENAMES = {
    "manual_intake_pkey": "pk_manual_intake",
    "manual_intake_created_by_fkey": "fk_manual_intake_created_by_users",
    "manual_intake_origin_root_id_fkey": "fk_manual_intake_origin_root_id_manual_intake",
}

# Exact definition of the legacy 1-5 scale (measurement_conventions.md §6.10).
_MANUAL_INTAKE_LEGACY_IG_SCALE = "CHECK (((ig_confidence >= 1) AND (ig_confidence <= 5)))"


def _manual_intake_constraint_definition(cursor, name: str) -> str | None:
    cursor.execute(
        """
        SELECT pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = 'manual_intake'::regclass AND conname = %(name)s;
        """,
        {"name": name},
    )
    row = cursor.fetchone()
    return (row.get("definition") or "").strip() if row else None


def _manual_intake_count(cursor, condition: str) -> int:
    """count(*) of manual_intake rows matching a constant condition written in
    this module (never request data, §11.9)."""
    cursor.execute(
        sql.SQL("SELECT count(*) AS total FROM manual_intake WHERE {};").format(sql.SQL(condition))
    )
    return cursor.fetchone()["total"]


def _ensure_manual_intake_schema(cursor):
    """manual_intake: canonical schema rebuilt from the enums and the limits (§12.1).

    Idempotent (§12.2) and fails on anything unexpected instead of correcting it
    (§12.5, §12.7). Closes findings 4, 6, 9, 12, 13, 14 and 15 of
    audit/audits/audit_manual_intake.md, plus the new scope of the 2026-10-09
    decisions (code_conventions.md §11.2.3). The TIMESTAMPTZ migration is a
    separate step (_ensure_manual_intake_timestamptz, §10.5).
    """
    # ---- 0. Basic columns of old installs ----
    for column in ("deleted_at", "created_at", "updated_at"):
        if not _has_column(cursor, "manual_intake", column):
            cursor.execute(
                sql.SQL("ALTER TABLE manual_intake ADD COLUMN {} TIMESTAMPTZ;").format(
                    sql.Identifier(column)
                )
            )
    # Legacy rows have no reliable creation time; the migration timestamp is only a backfill marker.
    cursor.execute(
        """
        UPDATE manual_intake
        SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP),
            updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)
        WHERE created_at IS NULL OR updated_at IS NULL;
        """
    )
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN updated_at SET NOT NULL;")
    if _has_column(cursor, "manual_intake", "slug"):
        cursor.execute("ALTER TABLE manual_intake DROP COLUMN slug;")

    # ---- 1. Safeguards before dropping anything (§12.2) ----
    legacy_gi = _manual_intake_constraint_definition(cursor, "manual_intake_glycemic_index_check")
    if legacy_gi is not None:
        literals = set(re.findall(r"'([^']+)'", legacy_gi))
        if literals != {"high", "medium", "low"}:
            raise RuntimeError(
                f"manual_intake_glycemic_index_check has unexpected values: {sorted(literals)}"
            )
    legacy_ig = _manual_intake_constraint_definition(cursor, "manual_intake_ig_confidence_check")
    legacy_ig_scale = legacy_ig is not None
    if legacy_ig_scale and legacy_ig.removesuffix(" NOT VALID") != _MANUAL_INTAKE_LEGACY_IG_SCALE:
        raise RuntimeError(f"Unexpected definition for manual_intake_ig_confidence_check: {legacy_ig!r}")

    # ---- 2. amount_g -> default_portion (H9, decision 2026-10-09) ----
    has_old = _has_column(cursor, "manual_intake", "amount_g")
    has_new = _has_column(cursor, "manual_intake", "default_portion")
    if has_old and has_new:
        raise RuntimeError("manual_intake has both amount_g and default_portion: half-applied migration")
    if has_old:
        if _manual_intake_count(cursor, "amount_g > 3000"):
            raise RuntimeError(
                "manual_intake.amount_g has rows above 3000 g; they do not fit the shared "
                "default_portion range (code_conventions.md 12.7)."
            )
        cursor.execute("ALTER TABLE manual_intake RENAME COLUMN amount_g TO default_portion;")
        cursor.execute("ALTER TABLE manual_intake ALTER COLUMN default_portion DROP NOT NULL;")
    elif not has_new:
        cursor.execute("ALTER TABLE manual_intake ADD COLUMN default_portion REAL;")

    # ---- 3. Drop the inherited CHECKs by their exact name ----
    for legacy_name in _MANUAL_INTAKE_LEGACY_CHECKS:
        cursor.execute(
            sql.SQL("ALTER TABLE manual_intake DROP CONSTRAINT IF EXISTS {};").format(
                sql.Identifier(legacy_name)
            )
        )

    # ---- 4. New columns and the ig_confidence scale (H15, decision 2026-10-09) ----
    for column, definition in (
        # Existing rows are reusable dishes: FALSE is a technical backfill.
        ("is_quick_add", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("macros_confidence", "INTEGER"),
    ):
        if not _has_column(cursor, "manual_intake", column):
            cursor.execute(
                sql.SQL("ALTER TABLE manual_intake ADD COLUMN {} {};").format(
                    sql.Identifier(column), sql.SQL(definition)
                )
            )
    # default_macros_quality -> macros_quality: the quality is the dish's data,
    # read live by portions (decision 2026-10-09, measurement §6.11).
    has_old_quality = _has_column(cursor, "manual_intake", "default_macros_quality")
    has_new_quality = _has_column(cursor, "manual_intake", "macros_quality")
    if has_old_quality and has_new_quality:
        raise RuntimeError(
            "manual_intake has both default_macros_quality and macros_quality: half-applied migration"
        )
    if has_old_quality:
        cursor.execute("ALTER TABLE manual_intake RENAME COLUMN default_macros_quality TO macros_quality;")
    # U1/U2 (study §6.3, 2026-11-12): both yes/no columns became closed lists.
    # A dish's published macros come from its menu or website: TRUE -> official.
    _replace_boolean_with_list(
        cursor, "manual_intake", "macros_quality", "macros_source", MacrosSource.OFFICIAL.value
    )
    _replace_boolean_with_list(
        cursor, "manual_intake", "default_strictly_weighed", "default_amount_method",
        AmountMethod.KITCHEN_SCALE.value,
    )
    # What the serving is (study §6.3, decision 2026-11-21); NULL = not said.
    cursor.execute("ALTER TABLE manual_intake ADD COLUMN IF NOT EXISTS serving_method VARCHAR(50);")
    if legacy_ig_scale:
        # Approved data correction (measurement §6.10, §12.7). It only runs while
        # the legacy CHECK existed, dropped in step 3 of this same transaction,
        # so an already migrated value is never converted twice.
        cursor.execute(
            """
            UPDATE manual_intake
            SET ig_confidence = CASE WHEN ig_confidence IN (1, 2) THEN 0
                                     WHEN ig_confidence = 3 THEN 1
                                     WHEN ig_confidence IN (4, 5) THEN 2 END
            WHERE ig_confidence IS NOT NULL;
            """
        )
        logger.info("manual_intake.ig_confidence: %s rows moved to the 0-2 scale", cursor.rowcount)

    # ---- 5. Nullability (H14, decision 2026-10-09), blocking pre-checks ----
    if _manual_intake_count(cursor, "created_by IS NULL"):
        raise RuntimeError(
            "manual_intake has rows without created_by; created_by cannot be NOT NULL "
            "(code_conventions.md 11.2.3, 12.7)."
        )
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN created_by SET NOT NULL;")
    if _manual_intake_count(cursor, "carbs_100g IS NULL"):
        raise RuntimeError(
            "manual_intake has rows without carbs_100g; carbs_100g cannot be NOT NULL "
            "(code_conventions.md 11.2.3, 12.7)."
        )
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN carbs_100g SET NOT NULL;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN subtype DROP NOT NULL;")

    # ---- 6. Canonical CHECKs, validated (H6, H13, H15) ----
    # Without NOT VALID: a row that breaks a rule aborts the bootstrap with the
    # CHECK name (§12.5).
    for name, expression in manual_intake_check_constraints().items():
        cursor.execute(
            sql.SQL("ALTER TABLE manual_intake DROP CONSTRAINT IF EXISTS {};").format(sql.Identifier(name))
        )
        cursor.execute(
            sql.SQL("ALTER TABLE manual_intake ADD CONSTRAINT {} CHECK ({});").format(
                sql.Identifier(name), sql.SQL(expression)
            )
        )

    # ---- 7. Inherited UNIQUE constraints (replaced by the partial indexes) ----
    cursor.execute(
        """
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = 'manual_intake'::regclass AND contype = 'u';
        """
    )
    for row in cursor.fetchall() or []:
        definition = (row.get("definition") or "").strip()
        if definition in ("UNIQUE (created_by, name)", "UNIQUE (created_by, name, origin)"):
            cursor.execute(
                sql.SQL("ALTER TABLE manual_intake DROP CONSTRAINT {};").format(
                    sql.Identifier(row["conname"])
                )
            )

    # ---- 8. Canonical names and final safeguard (§11.6, §12.2) ----
    for old_name, new_name in _MANUAL_INTAKE_CONSTRAINT_RENAMES.items():
        if _constraint_exists(cursor, "manual_intake", old_name) and not _constraint_exists(
            cursor, "manual_intake", new_name
        ):
            cursor.execute(
                sql.SQL("ALTER TABLE manual_intake RENAME CONSTRAINT {} TO {};").format(
                    sql.Identifier(old_name), sql.Identifier(new_name)
                )
            )
    cursor.execute(
        """
        SELECT conname, confdeltype
        FROM pg_constraint
        WHERE conrelid = 'manual_intake'::regclass AND contype = 'f';
        """
    )
    delete_rules = {row["conname"]: row["confdeltype"] for row in cursor.fetchall() or []}
    for name, expected_rule in (
        ("fk_manual_intake_created_by_users", "c"),  # CASCADE
        ("fk_manual_intake_origin_root_id_manual_intake", "n"),  # SET NULL
    ):
        if delete_rules.get(name) != expected_rule:
            raise RuntimeError(
                f"{name} has delete rule {delete_rules.get(name)!r}, expected {expected_rule!r}"
            )
    canonical = {
        "pk_manual_intake",
        "fk_manual_intake_created_by_users",
        "fk_manual_intake_origin_root_id_manual_intake",
    } | set(manual_intake_check_constraints())
    cursor.execute(
        """
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'manual_intake'::regclass
          AND contype IN ('p', 'f', 'c', 'u');
        """
    )
    unexpected = sorted(
        row["conname"] for row in cursor.fetchall() or [] if row["conname"] not in canonical
    )
    if unexpected:
        raise RuntimeError(
            f"manual_intake has constraints outside the canonical set: {unexpected}. "
            "Add them to manual_intake_check_constraints() or remove them explicitly (§12.1)."
        )

    # ---- 9. Partial unique indexes (H4, §6.1, §11.4.1, §11.5) ----
    # lower(name) without btrim: ck_manual_intake_name_normalized and
    # ck_manual_intake_origin_normalized guarantee the stored value already is
    # normalize_food_text's output, so index, CHECK and Python share one
    # normalization. A NULL origin counts as '' (decision 2026-10-09). Quick adds
    # stay outside both: ck_manual_intake_quick_add_not_published keeps them out
    # of the published one.
    for index_name in (
        "uq_manual_created_name_origin_norm",
        "uq_manual_intake_personal_name_origin",
        "uq_manual_intake_published_name_origin",
    ):
        cursor.execute(sql.SQL("DROP INDEX IF EXISTS {};").format(sql.Identifier(index_name)))
    cursor.execute(
        "CREATE UNIQUE INDEX uq_manual_intake_personal_name_origin "
        "ON manual_intake (created_by, lower(name), lower(COALESCE(origin, ''))) "
        "WHERE deleted_at IS NULL AND NOT is_published AND NOT is_quick_add;"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX uq_manual_intake_published_name_origin "
        "ON manual_intake (lower(name), lower(COALESCE(origin, ''))) "
        "WHERE deleted_at IS NULL AND is_published;"
    )

    # ---- 10. Auxiliary indexes (H17, §11.7) ----
    # Overlaps idx_manual_intake_created_by (_ensure_food_filter_indexes).
    cursor.execute("DROP INDEX IF EXISTS idx_manual_active_created_by;")


def _ensure_manual_intake_timestamptz(cursor):
    """manual_intake temporal columns -> TIMESTAMPTZ (H13, §10.4, §10.5). Same
    steps as step 1 of _ensure_catalog_schema; kept apart from the functional
    changes. Values are read as UTC (session timezone Etc/UTC)."""
    for column in ("created_at", "updated_at", "deleted_at"):
        data_type = (_column_data_type(cursor, "manual_intake", column) or "").lower()
        if data_type == "timestamp without time zone":
            if column in ("created_at", "updated_at"):
                cursor.execute(
                    sql.SQL("ALTER TABLE manual_intake ALTER COLUMN {} DROP DEFAULT;").format(
                        sql.Identifier(column)
                    )
                )
            cursor.execute(
                sql.SQL(
                    "ALTER TABLE manual_intake ALTER COLUMN {} TYPE TIMESTAMPTZ "
                    "USING {} AT TIME ZONE 'UTC';"
                ).format(sql.Identifier(column), sql.Identifier(column))
            )
        elif data_type != "timestamp with time zone":
            raise RuntimeError(f"Unexpected manual_intake.{column} type: {data_type!r}")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN created_at SET NOT NULL;")
    cursor.execute("ALTER TABLE manual_intake ALTER COLUMN updated_at SET NOT NULL;")


_USER_FAVORITES_CONSTRAINT_RENAMES = {
    "user_favorites_pkey": "pk_user_favorites",
    "user_favorites_user_id_fkey": "fk_user_favorites_user_id_users",
    "user_favorites_catalog_id_fkey": "fk_user_favorites_catalog_id_catalog",
    "user_favorites_manual_intake_id_fkey": "fk_user_favorites_manual_intake_id_manual_intake",
    "user_favorites_recipe_id_fkey": "fk_user_favorites_recipe_id_recipe",
    "user_favorites_check": "ck_user_favorites_one_entry",
}
# Current name of each per-food unique index -> the name it had before.
_USER_FAVORITES_UNIQUE_INDEXES = {
    "catalog_id": "uq_user_favorites_catalog",
    "manual_intake_id": "uq_user_favorites_manual",
    "recipe_id": "uq_user_favorites_recipe",
}


def _ensure_user_favorites_schema(cursor):
    """What DBSchema.user_favorites cannot do on a table that already exists.

    Every step checks first, so an up-to-date database takes no lock on the
    table (§12.2). created_at of the existing rows is the migration date, a
    technical backfill (§12.7).
    """
    if not _has_column(cursor, "user_favorites", "created_at"):
        cursor.execute(
            "ALTER TABLE user_favorites ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;"
        )
    for old_name, new_name in _USER_FAVORITES_CONSTRAINT_RENAMES.items():
        if _constraint_exists(cursor, "user_favorites", old_name) and not _constraint_exists(
            cursor, "user_favorites", new_name
        ):
            cursor.execute(
                sql.SQL("ALTER TABLE user_favorites RENAME CONSTRAINT {} TO {};").format(
                    sql.Identifier(old_name), sql.Identifier(new_name)
                )
            )
    for column, old_name in _USER_FAVORITES_UNIQUE_INDEXES.items():
        name = f"uq_user_favorites_user_id_{column}"
        if _index_exists(cursor, name):
            continue
        if _index_exists(cursor, old_name):
            cursor.execute(
                sql.SQL("ALTER INDEX {} RENAME TO {};").format(sql.Identifier(old_name), sql.Identifier(name))
            )
        else:
            cursor.execute(
                sql.SQL("CREATE UNIQUE INDEX {} ON user_favorites (user_id, {}) WHERE {} IS NOT NULL;").format(
                    sql.Identifier(name), sql.Identifier(column), sql.Identifier(column)
                )
            )
    cursor.execute("DROP INDEX IF EXISTS idx_catalog_favorite;")
    cursor.execute("DROP INDEX IF EXISTS idx_manual_favorite;")
    cursor.execute("DROP INDEX IF EXISTS idx_recipe_favorite;")
    # Checked first: DROP COLUMN IF EXISTS takes an exclusive lock even with nothing to do (§12.2).
    for table in ("catalog", "manual_intake", "recipe"):
        if _has_column(cursor, table, "favorite"):
            cursor.execute(sql.SQL("ALTER TABLE {} DROP COLUMN favorite;").format(sql.Identifier(table)))

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
        # Checked first: an ALTER takes an exclusive lock even with nothing to change (§12.2).
        cursor.execute(
            "SELECT column_default, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %(table)s AND column_name = 'is_published';",
            {"table": table},
        )
        published = cursor.fetchone()
        if published["column_default"] != "false" or published["is_nullable"] == "YES":
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
    if (
        _index_exists(cursor, "idx_manual_origin_root")
        and not _index_exists(cursor, "idx_manual_intake_origin_root_id")
    ):
        cursor.execute("ALTER INDEX idx_manual_origin_root RENAME TO idx_manual_intake_origin_root_id;")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_manual_intake_origin_root_id ON manual_intake (origin_root_id);"
    )
    if _index_exists(cursor, "idx_recipe_origin_root") and not _index_exists(cursor, "idx_recipe_origin_root_id"):
        cursor.execute("ALTER INDEX idx_recipe_origin_root RENAME TO idx_recipe_origin_root_id;")
    _create_index_once(cursor, "idx_recipe_origin_root_id", "ON recipe (origin_root_id)")


# Automatic names of older installs -> canonical names (§11.6).
_RECIPE_CONSTRAINT_RENAMES = {
    "recipe_pkey": "pk_recipe",
    "recipe_users_id_fkey": "fk_recipe_users_id_users",
    "recipe_origin_root_id_fkey": "fk_recipe_origin_root_id_recipe",
}


def _stop_on_recipe_name_duplicates(cursor, group_sql: str, where_sql: str, index_name: str) -> None:
    """Existing duplicates stop the migration (§12.2, §12.7): which recipe keeps
    the name is a decision, not something to resolve here. The arguments are constants."""
    cursor.execute(
        f"SELECT {group_sql} AS owner_and_name, count(*) AS total FROM recipe r "
        f"WHERE {where_sql} GROUP BY 1 HAVING count(*) > 1;"
    )
    duplicates = cursor.fetchall() or []
    if duplicates:
        detail = ", ".join(f"{row['total']} x '{row['owner_and_name']}'" for row in duplicates)
        raise RuntimeError(f"Recipes with a repeated name block {index_name}; rename or delete them first: {detail}")


def _ensure_recipe_schema(cursor):
    """`recipe`: canonical columns, constraints and unique indexes (§11.2.4). Idempotent.

    Nothing is dropped and recreated on each start: that takes an exclusive lock on
    the table for no reason (§12.2). A change to a generated CHECK therefore needs
    its own explicit migration.
    """
    # slug existed only in the real database and no code uses it (approved
    # destructive step, §12.4).
    cursor.execute("DROP INDEX IF EXISTS idx_recipe_slug;")
    if _has_column(cursor, "recipe", "slug"):
        cursor.execute("ALTER TABLE recipe DROP COLUMN slug;")

    for column in ("created_at", "updated_at"):
        if not _has_column(cursor, "recipe", column):
            # Existing rows get the date of this migration, never an inferred one (§12.7).
            cursor.execute(
                sql.SQL("ALTER TABLE recipe ADD COLUMN {} TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;").format(
                    sql.Identifier(column)
                )
            )
    if not _has_column(cursor, "recipe", "servings"):
        cursor.execute("ALTER TABLE recipe ADD COLUMN servings INTEGER;")
    if not _has_column(cursor, "recipe", "extra_meal_types"):
        cursor.execute("ALTER TABLE recipe ADD COLUMN extra_meal_types VARCHAR(50)[] NOT NULL DEFAULT '{}';")
    if not _has_column(cursor, "recipe", "search_name"):
        cursor.execute(
            f"ALTER TABLE recipe ADD COLUMN search_name TEXT "
            f"GENERATED ALWAYS AS ({search_text_sql('name')}) STORED;"
        )
    # Fails on its own if a recipe has no owner: there is no general recipe library.
    cursor.execute(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'recipe' AND column_name = 'users_id';"
    )
    if cursor.fetchone()["is_nullable"] == "YES":
        cursor.execute("ALTER TABLE recipe ALTER COLUMN users_id SET NOT NULL;")

    for old_name, new_name in _RECIPE_CONSTRAINT_RENAMES.items():
        if _constraint_exists(cursor, "recipe", old_name) and not _constraint_exists(cursor, "recipe", new_name):
            cursor.execute(
                sql.SQL("ALTER TABLE recipe RENAME CONSTRAINT {} TO {};").format(
                    sql.Identifier(old_name), sql.Identifier(new_name)
                )
            )
    if _constraint_exists(cursor, "recipe", "recipe_meal_type_check"):
        cursor.execute("ALTER TABLE recipe DROP CONSTRAINT recipe_meal_type_check;")
    # A meal type added to the enum must reach them (§4.4).
    for name in ("ck_recipe_meal_type", "ck_recipe_extra_meal_types"):
        if _check_lacks_values(cursor, "recipe", name, [meal_type.value for meal_type in RECIPE_MEAL_TYPES]):
            cursor.execute(sql.SQL("ALTER TABLE recipe DROP CONSTRAINT {};").format(sql.Identifier(name)))
    for name, expression in recipe_check_constraints().items():
        if not _constraint_exists(cursor, "recipe", name):
            cursor.execute(
                sql.SQL("ALTER TABLE recipe ADD CONSTRAINT {} CHECK ({});").format(
                    sql.Identifier(name), sql.SQL(expression)
                )
            )

    if not _index_exists(cursor, "uq_recipe_personal_name"):
        _stop_on_recipe_name_duplicates(
            cursor, "r.users_id::text || ': ' || lower(r.name)", "NOT r.is_published", "uq_recipe_personal_name"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX uq_recipe_personal_name ON recipe (users_id, lower(name)) WHERE NOT is_published;"
        )
    if not _index_exists(cursor, "uq_recipe_published_name"):
        _stop_on_recipe_name_duplicates(cursor, "lower(r.name)", "r.is_published", "uq_recipe_published_name")
        cursor.execute("CREATE UNIQUE INDEX uq_recipe_published_name ON recipe (lower(name)) WHERE is_published;")


def _ensure_recipe_plate_schema(cursor):
    """Every recipe ingredient belongs to a plate (measurement §4.7). Idempotent.

    Technical backfill (§12.7): each recipe with ingredients gets one plate, position
    1, with a derived name, as events did in §4.6.6. A recipe without ingredients gets
    none. Rows the new unique key would reject are merged by the §4.6.4 rule first:
    amounts are summed in the oldest row, so the recipe's total does not change.
    """
    if not _has_column(cursor, "portion_detail", "recipe_plate_id"):
        cursor.execute("ALTER TABLE portion_detail ADD COLUMN recipe_plate_id INTEGER;")
    cursor.execute(
        """
        INSERT INTO recipe_plate (recipe_id, position)
        SELECT DISTINCT pd.recipe_id, 1
        FROM portion_detail pd
        WHERE pd.recipe_id IS NOT NULL
          AND pd.recipe_plate_id IS NULL
          AND NOT EXISTS (SELECT 1 FROM recipe_plate rp WHERE rp.recipe_id = pd.recipe_id);
        """
    )
    cursor.execute(
        """
        UPDATE portion_detail pd
        SET recipe_plate_id = (
            SELECT rp.id FROM recipe_plate rp WHERE rp.recipe_id = pd.recipe_id ORDER BY rp.position LIMIT 1
        )
        WHERE pd.recipe_id IS NOT NULL AND pd.recipe_plate_id IS NULL;
        """
    )
    cursor.execute(
        """
        WITH duplicates AS (
            SELECT min(id) AS keep_id, array_agg(id) AS ids, sum(amount) AS total
            FROM portion_detail
            WHERE recipe_plate_id IS NOT NULL
            GROUP BY recipe_plate_id, catalog_id, manual_intake_id, cooking, conservation, final_state, is_cooked_weight
            HAVING count(*) > 1
        ), summed AS (
            UPDATE portion_detail pd SET amount = d.total, updated_at = NOW()
            FROM duplicates d WHERE pd.id = d.keep_id
        )
        DELETE FROM portion_detail pd
        USING duplicates d
        WHERE pd.id = ANY(d.ids) AND pd.id <> d.keep_id;
        """
    )
    if not _constraint_exists(cursor, "portion_detail", "ck_portion_detail_recipe_plate_only_for_recipe"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT ck_portion_detail_recipe_plate_only_for_recipe "
            "CHECK ((recipe_id IS NULL) = (recipe_plate_id IS NULL));"
        )
    if not _constraint_exists(cursor, "portion_detail", "fk_portion_detail_recipe_plate_id_recipe_plate"):
        cursor.execute(
            "ALTER TABLE portion_detail ADD CONSTRAINT fk_portion_detail_recipe_plate_id_recipe_plate "
            "FOREIGN KEY (recipe_id, recipe_plate_id) REFERENCES recipe_plate (recipe_id, id) ON DELETE RESTRICT;"
        )
    if not _index_exists(cursor, "uq_portion_detail_recipe_plate_origin_preparation_cooked"):
        cursor.execute(
            """
            CREATE UNIQUE INDEX uq_portion_detail_recipe_plate_origin_preparation_cooked
            ON portion_detail (recipe_plate_id, catalog_id, manual_intake_id, cooking, conservation, final_state, is_cooked_weight)
            NULLS NOT DISTINCT
            WHERE recipe_plate_id IS NOT NULL;
            """
        )
# Columns searched with `_build_fuzzy_search` that have a trigram index.
_FUZZY_COMPACT_INDEXED_COLUMNS = (
    ("catalog", "name"),
    ("manual_intake", "name"),
    ("manual_intake", "origin"),
    ("food_brands", "label"),
)


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
            "CREATE INDEX IF NOT EXISTS idx_food_brands_label_trgm "
            "ON food_brands USING gin (lower(label) gin_trgm_ops);"
        )
        # Backs the search by origin (H7). Canonical name (§11.7), renamed once.
        if _index_exists(cursor, "idx_manual_origin_trgm") and not _index_exists(
            cursor, "idx_manual_intake_origin_trgm"
        ):
            cursor.execute("ALTER INDEX idx_manual_origin_trgm RENAME TO idx_manual_intake_origin_trgm;")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_manual_intake_origin_trgm "
            "ON manual_intake USING gin (lower(origin) gin_trgm_ops);"
        )
        # Collapsed form of every searched column, so the third branch of
        # `_build_fuzzy_search` is indexed too and the whole OR can use indexes
        # (§11.7). Same expression as the query: `fuzzy_compact_sql`.
        for table, column in _FUZZY_COMPACT_INDEXED_COLUMNS:
            cursor.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING gin ({} gin_trgm_ops);").format(
                    sql.Identifier(f"idx_{table}_{column}_compact_trgm"),
                    sql.Identifier(table),
                    sql.SQL(fuzzy_compact_sql(column)),
                )
            )
        cursor.execute("RELEASE SAVEPOINT trgm_setup;")
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT trgm_setup;")
        cursor.execute("RELEASE SAVEPOINT trgm_setup;")
        logger.warning("pg_trgm setup skipped: %s", exc)


def _ensure_food_filter_indexes(cursor):
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_created_by ON catalog (created_by);")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_prefill_source "
        "ON catalog (created_by, prefill_source, prefill_source_id) WHERE prefill_source IS NOT NULL;"
    )
    # idx_catalog_visibility is dropped and not recreated: no real query uses it
    # (0 scans) and the partial unique indexes cover the visibility filter.
    cursor.execute("DROP INDEX IF EXISTS idx_catalog_visibility;")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_catalog_deleted_at ON catalog (deleted_at);")
    # idx_manual_visibility is dropped and not recreated: no query uses it; the
    # partial unique indexes and the owner index cover the visibility filter.
    cursor.execute("DROP INDEX IF EXISTS idx_manual_visibility;")
    # Canonical index name (§11.7): rename the older name once, before creating.
    if _index_exists(cursor, "idx_manual_created_by") and not _index_exists(
        cursor, "idx_manual_intake_created_by"
    ):
        cursor.execute("ALTER INDEX idx_manual_created_by RENAME TO idx_manual_intake_created_by;")
    # Backs the owner filter and the cascade from users.
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_manual_intake_created_by ON manual_intake (created_by);")
    _create_index_once(cursor, "idx_recipe_users_id", "ON recipe (users_id)")
    # No query uses it: the owner index and the partial unique indexes cover the filter.
    cursor.execute("DROP INDEX IF EXISTS idx_recipe_visibility;")


def _ensure_off_product_schema(cursor):
    if not _has_column(cursor, "off_product", "name_is_store_brand"):
        cursor.execute("ALTER TABLE off_product ADD COLUMN name_is_store_brand BOOLEAN NOT NULL DEFAULT FALSE;")


def _ensure_food_search_indexes(cursor):
    # After _ensure_catalog_schema, which creates catalog.search_name on old
    # installs. Tolerated like _ensure_trgm_search: without pg_trgm the searches
    # still work, only slower.
    cursor.execute("SAVEPOINT food_search_setup;")
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_catalog_search_name_trgm "
            "ON catalog USING gin (lower(search_name) gin_trgm_ops);"
        )
        cursor.execute(
            sql.SQL("CREATE INDEX IF NOT EXISTS idx_catalog_search_name_compact_trgm ON catalog USING gin ({} gin_trgm_ops);").format(
                sql.SQL(fuzzy_compact_sql("search_name"))
            )
        )
        # recipe searches search_name since 2026-11-05 (§11.7).
        cursor.execute("DROP INDEX IF EXISTS idx_recipe_name_trgm;")
        cursor.execute("DROP INDEX IF EXISTS idx_recipe_name_compact_trgm;")
        _create_index_once(
            cursor, "idx_recipe_search_name_trgm", "ON recipe USING gin (lower(search_name) gin_trgm_ops)"
        )
        _create_index_once(
            cursor,
            "idx_recipe_search_name_compact_trgm",
            f"ON recipe USING gin ({fuzzy_compact_sql('search_name')} gin_trgm_ops)",
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_off_product_search_text_trgm "
            "ON off_product USING gin (search_text gin_trgm_ops);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_ciqual_food_search_text_trgm "
            "ON ciqual_food USING gin (search_text gin_trgm_ops);"
        )
        cursor.execute("RELEASE SAVEPOINT food_search_setup;")
    except Exception as exc:
        cursor.execute("ROLLBACK TO SAVEPOINT food_search_setup;")
        cursor.execute("RELEASE SAVEPOINT food_search_setup;")
        logger.warning("Food search indexes skipped: %s", exc)


_TAGS_CONSTRAINT_RENAMES = {"tags_pkey": "pk_tags"}
_LINKED_TAGS_CONSTRAINT_RENAMES = {
    "linked_tags_pkey": "pk_linked_tags",
    "linked_tags_tag_id_fkey": "fk_linked_tags_tag_id_tags",
    "linked_tags_catalog_id_fkey": "fk_linked_tags_catalog_id_catalog",
    "linked_tags_recipe_id_fkey": "fk_linked_tags_recipe_id_recipe",
    "linked_tags_manual_intake_id_fkey": "fk_linked_tags_manual_intake_id_manual_intake",
    "linked_tags_check": "ck_linked_tags_one_entry",
}
_LINKED_TAG_ENTRY_COLUMNS = ("catalog_id", "manual_intake_id", "recipe_id")


def _migrate_tags_to_owners(cursor):
    """One-off move from global tags to system and personal tags (§11.2.8), run
    when linked_tags.users_id is first added. Technical backfill (§12.7):

    - The old rescue tag (`rescate`, any case) becomes the system tag `rescue`;
      if it was written more than once, the others are merged into it.
    - A link takes the owner of its food: until now only the owner could tag it.
      A link whose food has no owner cannot be attributed and is dropped.
    - Every other tag goes to the owners of its links: the first one keeps the
      row, any other gets a copy with its links. A tag no food carries is dropped.
    - Tags of one owner whose names only differ in case or spacing are merged
      into the oldest, and then the names are normalized (ck_tags_name_normalized).
    """
    cursor.execute(
        "SELECT id FROM tags WHERE system_key IS NULL AND lower(btrim(name)) IN ('rescate', 'rescue') ORDER BY id;"
    )
    rescue_ids = [row["id"] for row in cursor.fetchall()]
    if rescue_ids:
        keep, others = rescue_ids[0], rescue_ids[1:]
        if others:
            cursor.execute(
                "UPDATE linked_tags SET tag_id = %(keep)s WHERE tag_id = ANY(%(others)s);",
                {"keep": keep, "others": others},
            )
            cursor.execute("DELETE FROM tags WHERE id = ANY(%(others)s);", {"others": others})
        # A system tag stores its key as its name; the interface shows its label (§11.2.8).
        cursor.execute(
            "UPDATE tags SET system_key = %(key)s, name = %(key)s WHERE id = %(id)s;",
            {"key": SystemTag.RESCUE.value, "id": keep},
        )

    cursor.execute(
        """
        UPDATE linked_tags lt SET users_id = c.created_by FROM catalog c WHERE lt.catalog_id = c.id;
        UPDATE linked_tags lt SET users_id = m.created_by FROM manual_intake m WHERE lt.manual_intake_id = m.id;
        UPDATE linked_tags lt SET users_id = r.users_id FROM recipe r WHERE lt.recipe_id = r.id;
        DELETE FROM linked_tags WHERE users_id IS NULL OR tag_id IS NULL;
        """
    )

    # Owners of each tag that has none yet, first owner first.
    cursor.execute(
        """
        SELECT DISTINCT lt.tag_id, lt.users_id
        FROM linked_tags lt
        INNER JOIN tags t ON t.id = lt.tag_id
        WHERE t.users_id IS NULL AND t.system_key IS NULL
        ORDER BY lt.tag_id, lt.users_id;
        """
    )
    owned: set[int] = set()
    for row in cursor.fetchall():
        tag_id, user_id = row["tag_id"], row["users_id"]
        if tag_id not in owned:
            owned.add(tag_id)
            cursor.execute("UPDATE tags SET users_id = %(user_id)s WHERE id = %(tag_id)s;",
                           {"user_id": user_id, "tag_id": tag_id})
            continue
        cursor.execute(
            """
            INSERT INTO tags (users_id, name, color, description)
            SELECT %(user_id)s, name, color, description FROM tags WHERE id = %(tag_id)s
            RETURNING id;
            """,
            {"user_id": user_id, "tag_id": tag_id},
        )
        copy_id = cursor.fetchone()["id"]
        cursor.execute(
            "UPDATE linked_tags SET tag_id = %(copy_id)s WHERE tag_id = %(tag_id)s AND users_id = %(user_id)s;",
            {"copy_id": copy_id, "tag_id": tag_id, "user_id": user_id},
        )
    cursor.execute("DELETE FROM tags WHERE users_id IS NULL AND system_key IS NULL;")

    # Same owner, same name once normalized and ignoring case (uq_tags_users_id_name):
    # the oldest row stays. Compared normalized, so `Alto  en fibra` and `alto en
    # fibra` meet, and merged before the names are rewritten, so the rewrite cannot
    # hit the old global unique name (tags_name_key) with two tags of one owner.
    same_name = "lower(regexp_replace(btrim({}), '\\s+', ' ', 'g'))"
    cursor.execute(
        f"""
        WITH ranked AS (
            SELECT t.id, min(t.id) OVER (PARTITION BY t.users_id, {same_name.format('t.name')}) AS keep_id
            FROM tags t WHERE t.users_id IS NOT NULL
        )
        UPDATE linked_tags lt SET tag_id = ranked.keep_id
        FROM ranked WHERE lt.tag_id = ranked.id AND ranked.id <> ranked.keep_id;

        DELETE FROM tags t
        USING tags older
        WHERE t.users_id IS NOT NULL AND older.users_id = t.users_id
          AND {same_name.format('older.name')} = {same_name.format('t.name')} AND older.id < t.id;
        """
    )
    # Normalized names (ck_tags_name_normalized), as Python always wrote them.
    cursor.execute(
        "UPDATE tags SET name = regexp_replace(btrim(name), '\\s+', ' ', 'g') "
        "WHERE name <> regexp_replace(btrim(name), '\\s+', ' ', 'g');"
    )
    # The same link twice (nothing prevented it): the oldest stays.
    for column in _LINKED_TAG_ENTRY_COLUMNS:
        cursor.execute(
            sql.SQL(
                "DELETE FROM linked_tags lt USING linked_tags older "
                "WHERE lt.{col} IS NOT NULL AND older.{col} = lt.{col} "
                "AND older.users_id = lt.users_id AND older.tag_id = lt.tag_id AND older.id < lt.id;"
            ).format(col=sql.Identifier(column))
        )


def _ensure_tags_schema(cursor):
    """`tags` and `linked_tags` (code_conventions.md §11.2.8). Idempotent: every
    step checks first, so an up-to-date database takes no lock (§12.2)."""
    if not _has_column(cursor, "tags", "color"):
        # Installs older than the color column: a pastel hue from the name.
        cursor.execute("ALTER TABLE tags ADD COLUMN color VARCHAR(64) NOT NULL DEFAULT 'hsl(0 80% 90%)';")
    for column, definition in (
        ("users_id", "INTEGER"),
        ("system_key", "VARCHAR(32)"),
        ("created_at", "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"),
    ):
        if not _has_column(cursor, "tags", column):
            cursor.execute(
                sql.SQL("ALTER TABLE tags ADD COLUMN {} " + definition + ";").format(sql.Identifier(column))
            )
    if not _has_column(cursor, "linked_tags", "created_at"):
        cursor.execute("ALTER TABLE linked_tags ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;")
    if not _has_column(cursor, "linked_tags", "users_id"):
        cursor.execute("ALTER TABLE linked_tags ADD COLUMN users_id INTEGER;")
        _migrate_tags_to_owners(cursor)

    # The old unique name was global: two users could not have the same tag.
    if _constraint_exists(cursor, "tags", "tags_name_key"):
        cursor.execute("ALTER TABLE tags DROP CONSTRAINT tags_name_key;")
    for table, renames in (("tags", _TAGS_CONSTRAINT_RENAMES), ("linked_tags", _LINKED_TAGS_CONSTRAINT_RENAMES)):
        for old_name, new_name in renames.items():
            if _constraint_exists(cursor, table, old_name) and not _constraint_exists(cursor, table, new_name):
                cursor.execute(
                    sql.SQL("ALTER TABLE {} RENAME CONSTRAINT {} TO {};").format(
                        sql.Identifier(table), sql.Identifier(old_name), sql.Identifier(new_name)
                    )
                )
    if _index_exists(cursor, "tags_pkey"):  # a renamed PK constraint keeps its index name
        cursor.execute("ALTER INDEX tags_pkey RENAME TO pk_tags;")
    if _index_exists(cursor, "linked_tags_pkey"):
        cursor.execute("ALTER INDEX linked_tags_pkey RENAME TO pk_linked_tags;")
    for table, name, column in (("tags", "fk_tags_users_id_users", "users_id"),
                                ("linked_tags", "fk_linked_tags_users_id_users", "users_id")):
        if not _constraint_exists(cursor, table, name):
            cursor.execute(
                sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES users(id) ON DELETE CASCADE;").format(
                    sql.Identifier(table), sql.Identifier(name), sql.Identifier(column)
                )
            )
    for column in ("users_id", "tag_id"):
        if _column_is_nullable(cursor, "linked_tags", column):
            cursor.execute(
                sql.SQL("ALTER TABLE linked_tags ALTER COLUMN {} SET NOT NULL;").format(sql.Identifier(column))
            )

    if _check_lacks_values(cursor, "tags", "ck_tags_system_key", [key.value for key in SystemTag]):
        cursor.execute("ALTER TABLE tags DROP CONSTRAINT ck_tags_system_key;")
    for name, expression in tags_check_constraints().items():
        if not _constraint_exists(cursor, "tags", name):
            cursor.execute(
                sql.SQL("ALTER TABLE tags ADD CONSTRAINT {} CHECK ({});").format(
                    sql.Identifier(name), sql.SQL(expression)
                )
            )

    # One row per system tag, and one personal tag per name and owner ignoring case.
    _create_unique_index_once(cursor, "uq_tags_system_key", "ON tags (system_key) WHERE system_key IS NOT NULL")
    _create_unique_index_once(cursor, "uq_tags_users_id_name", "ON tags (users_id, lower(name)) WHERE users_id IS NOT NULL")
    # A system tag stores its key as its name: the name shown is SYSTEM_TAG_LABELS (§11.2.8).
    for key, color in SYSTEM_TAG_COLORS.items():
        cursor.execute("SELECT 1 AS ok FROM tags WHERE system_key = %(key)s;", {"key": key.value})
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO tags (system_key, name, color) VALUES (%(key)s, %(key)s, %(color)s);",
                {"key": key.value, "color": color},
            )

    # One link per user, tag and food; the food's own index serves its CASCADE and
    # its detail page, the tag's serves the CASCADE from tags.
    for column in _LINKED_TAG_ENTRY_COLUMNS:
        _create_unique_index_once(
            cursor,
            f"uq_linked_tags_users_id_tag_id_{column}",
            f"ON linked_tags (users_id, tag_id, {column}) WHERE {column} IS NOT NULL",
        )
        _create_index_once(cursor, f"idx_linked_tags_{column}", f"ON linked_tags ({column}) WHERE {column} IS NOT NULL")
    _create_index_once(cursor, "idx_linked_tags_tag_id", "ON linked_tags (tag_id)")


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
