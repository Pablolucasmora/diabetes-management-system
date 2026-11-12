"""Database schema definitions.

Uses domain constants (InsulinType, InjectionZone) to generate CHECKs
dynamically where applicable, ensuring a single source of truth.
"""

from DayBetes_food.domain.catalog import (
    CATALOG_BARCODE_MAX_LENGTH,
    CATALOG_BARCODE_MIN_LENGTH,
    CATALOG_COOKING_FACTOR_RANGE,
)
from DayBetes_food.domain.constants import (
    NOVA_MAX,
    NOVA_MIN,
    YUKA_MAX,
    YUKA_MIN,
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodPhysicalState,
    FridgeCloseReason,
    GlycemicIndex,
    IntakeEventState,
    InsulinType,
    InjectionZone,
    MealType,
    Nutriscore,
    PenCloseReason,
    PenFormat,
    PrefillSource,
    Ripeness,
    StorageLocation,
    SystemTag,
    sql_in_list,
)
from DayBetes_food.domain.search_text import search_text_sql
from DayBetes_food.domain.tag import TAG_COLOR_PATTERN
from DayBetes_food.domain.food import (
    FOOD_CONFIDENCE_MAX,
    FOOD_CONFIDENCE_MIN,
    FOOD_DEFAULT_PORTION_RANGE,
)
from DayBetes_food.domain.fridge import FRIDGE_CONTENT_WEIGHT_RANGE
from DayBetes_food.domain.insulin_pen import (
    DEFAULT_IN_USE_DAYS,
    DEFAULT_PEN_UNITS,
    IN_USE_DAYS_RANGE,
    PEN_UNITS_RANGE,
)
from DayBetes_food.domain.meal_type_schedule import AUTO_ASSIGNABLE_MEAL_TYPES
from DayBetes_food.domain.nutrition import NUTRIENT_LIMITS, NumericRange
from DayBetes_food.domain.recipe import RECIPE_MEAL_TYPES, RECIPE_SERVINGS_RANGE

_PORTION_PREPARATION_LISTS = {
    "cooking": sql_in_list(CookingMethod),
    "conservation": sql_in_list(ConservationMethod),
    "final_state": sql_in_list(FoodPhysicalState),
    "ripeness": sql_in_list(Ripeness),
}


def _sql_number(value) -> str:
    """100000 -> '100000', 0.5 -> '0.5' (never '1e+05')."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def _range_check(column: str, limits: NumericRange) -> str:
    low = (
        f"{column} > {_sql_number(limits.minimum)}"
        if limits.minimum_exclusive
        else f"{column} >= {_sql_number(limits.minimum)}"
    )
    return f"{column} IS NULL OR ({low} AND {column} <= {_sql_number(limits.maximum)})"


def catalog_check_constraints() -> dict[str, str]:
    """CHECK name -> expression of `catalog`, generated from the enums and the
    limits (§4.4, §12.1). The same list feeds the CREATE TABLE and
    db_init._ensure_catalog_schema, so it lives in one place only."""
    checks = {
        "ck_catalog_category": f"category IN ({sql_in_list(FoodCategory)})",
        "ck_catalog_initial_state": (
            f"initial_state IS NULL OR initial_state IN ({sql_in_list(FoodPhysicalState)})"
        ),
        "ck_catalog_nutriscore": (
            f"nutriscore IS NULL OR nutriscore IN ({sql_in_list(Nutriscore)})"
        ),
        "ck_catalog_nova_range": f"nova IS NULL OR (nova >= {NOVA_MIN} AND nova <= {NOVA_MAX})",
        "ck_catalog_yuka_range": f"yuka IS NULL OR (yuka >= {YUKA_MIN} AND yuka <= {YUKA_MAX})",
        "ck_catalog_default_portion_range": _range_check("default_portion", FOOD_DEFAULT_PORTION_RANGE),
        "ck_catalog_cooking_factor_range": _range_check("cooking_factor", CATALOG_COOKING_FACTOR_RANGE),
        "ck_catalog_sugars_le_carbs": "sugars_100g IS NULL OR carbs_100g IS NULL OR sugars_100g <= carbs_100g",
        "ck_catalog_saturated_le_fats": "saturated_100g IS NULL OR fats_100g IS NULL OR saturated_100g <= fats_100g",
        "ck_catalog_barcode_format": (
            f"barcode IS NULL OR barcode ~ '^[0-9]{{{CATALOG_BARCODE_MIN_LENGTH},{CATALOG_BARCODE_MAX_LENGTH}}}$'"
        ),
        "ck_catalog_name_normalized": r"name <> '' AND name = regexp_replace(btrim(name), '\s+', ' ', 'g')",
        "ck_catalog_library_published": "created_by IS NOT NULL OR is_published",
        "ck_catalog_prefill_source": f"prefill_source IS NULL OR prefill_source IN ({sql_in_list(PrefillSource)})",
        "ck_catalog_prefill_reference": "(prefill_source IS NULL) = (prefill_source_id IS NULL)",
        "ck_catalog_macros_confidence_range": (
            f"macros_confidence IS NULL OR macros_confidence BETWEEN {FOOD_CONFIDENCE_MIN} AND {FOOD_CONFIDENCE_MAX}"
        ),
    }
    for field, limits in NUTRIENT_LIMITS.items():
        checks[f"ck_catalog_{field}_range"] = _range_check(field, limits)
    return checks


def manual_intake_check_constraints() -> dict[str, str]:
    """CHECK name -> expression of `manual_intake`, generated from the enums and
    the limits (§4.4, §12.1). The same list feeds the CREATE TABLE and
    db_init._ensure_manual_intake_schema. NaN/Infinity are rejected by the
    ranges (in `real`, NaN is greater than any number), as in catalog."""
    confidence = f"BETWEEN {FOOD_CONFIDENCE_MIN} AND {FOOD_CONFIDENCE_MAX}"
    checks = {
        "ck_manual_intake_glycemic_index": (
            f"glycemic_index IS NULL OR glycemic_index IN ({sql_in_list(GlycemicIndex)})"
        ),
        "ck_manual_intake_ig_confidence_range": f"ig_confidence IS NULL OR ig_confidence {confidence}",
        "ck_manual_intake_macros_confidence_range": (
            f"macros_confidence IS NULL OR macros_confidence {confidence}"
        ),
        "ck_manual_intake_ig_confidence_requires_glycemic_index": (
            "ig_confidence IS NULL OR glycemic_index IS NOT NULL"
        ),
        "ck_manual_intake_default_portion_range": _range_check("default_portion", FOOD_DEFAULT_PORTION_RANGE),
        "ck_manual_intake_sugars_le_carbs": "sugars_100g IS NULL OR carbs_100g IS NULL OR sugars_100g <= carbs_100g",
        "ck_manual_intake_saturated_le_fats": "saturated_100g IS NULL OR fats_100g IS NULL OR saturated_100g <= fats_100g",
        "ck_manual_intake_name_normalized": r"name <> '' AND name = regexp_replace(btrim(name), '\s+', ' ', 'g')",
        "ck_manual_intake_origin_normalized": (
            r"origin IS NULL OR (origin <> '' AND origin = regexp_replace(btrim(origin), '\s+', ' ', 'g'))"
        ),
        "ck_manual_intake_quick_add_not_published": "NOT (is_quick_add AND is_published)",
    }
    for field, limits in NUTRIENT_LIMITS.items():
        checks[f"ck_manual_intake_{field}_range"] = _range_check(field, limits)
    return checks


def recipe_check_constraints() -> dict[str, str]:
    """CHECK name -> expression of `recipe`, generated from the enums and the limits
    (§4.4, §12.1). The same list feeds the CREATE TABLE and db_init._ensure_recipe_schema."""
    return {
        "ck_recipe_meal_type": f"meal_type IS NULL OR meal_type IN ({sql_in_list(RECIPE_MEAL_TYPES)})",
        "ck_recipe_extra_meal_types": (
            f"extra_meal_types <@ ARRAY[{sql_in_list(RECIPE_MEAL_TYPES)}]::varchar[]"
        ),
        "ck_recipe_extra_meal_types_need_main": (
            "cardinality(extra_meal_types) = 0 "
            "OR (meal_type IS NOT NULL AND NOT meal_type = ANY(extra_meal_types))"
        ),
        "ck_recipe_name_normalized": r"name <> '' AND name = regexp_replace(btrim(name), '\s+', ' ', 'g')",
        "ck_recipe_servings": _range_check("servings", RECIPE_SERVINGS_RANGE),
    }


def fridge_check_constraints() -> dict[str, str]:
    """CHECK name -> expression of `fridge` (§4.4, §12.1). The same list feeds the
    CREATE TABLE and db_init._ensure_fridge_schema."""
    return {
        "ck_fridge_location": f"location IN ({sql_in_list(StorageLocation)})",
        "ck_fridge_name_normalized": (
            r"name IS NULL OR (name <> '' AND name = regexp_replace(btrim(name), '\s+', ' ', 'g'))"
        ),
        "ck_fridge_content_weight": _range_check("content_weight", FRIDGE_CONTENT_WEIGHT_RANGE),
        "ck_fridge_expires_after_stored": "expires_at > stored_at",
        "ck_fridge_closed_after_stored": "closed_at IS NULL OR closed_at >= stored_at",
        "ck_fridge_closed_reason": f"closed_reason IS NULL OR closed_reason IN ({sql_in_list(FridgeCloseReason)})",
        "ck_fridge_closed_reason_iff_closed": "(closed_at IS NULL) = (closed_reason IS NULL)",
    }


def tags_check_constraints() -> dict[str, str]:
    """CHECK name -> expression of `tags` (code_conventions.md §11.2.8).
    The same list feeds the CREATE TABLE and db_init._ensure_tags_schema."""
    return {
        "ck_tags_system_key": f"system_key IS NULL OR system_key IN ({sql_in_list(SystemTag)})",
        # A system tag has no owner; a personal tag has one and no key.
        "ck_tags_owner": "(users_id IS NULL) = (system_key IS NOT NULL)",
        "ck_tags_name_normalized": r"name <> '' AND name = regexp_replace(btrim(name), '\s+', ' ', 'g')",
        "ck_tags_color": f"color ~ '{TAG_COLOR_PATTERN}'",
    }


def insulin_brand_check_constraints() -> dict[str, str]:
    """CHECK name -> expression of `insulin_brand` (code §11.2.7, measurement §8.4).
    The same list feeds the CREATE TABLE and db_init._ensure_insulin_pen_schema."""
    return {
        "ck_insulin_brand_name_normalized": r"name <> '' AND name = regexp_replace(btrim(name), '\s+', ' ', 'g')",
        "ck_insulin_brand_insulin_type": f"insulin_type IN ({sql_in_list(InsulinType)})",
        "ck_insulin_brand_in_use_days": (
            f"in_use_days >= {int(IN_USE_DAYS_RANGE.minimum)} AND in_use_days <= {int(IN_USE_DAYS_RANGE.maximum)}"
        ),
        "ck_insulin_brand_pen_units": _range_check("pen_units", PEN_UNITS_RANGE),
    }


def insulin_pen_check_constraints() -> dict[str, str]:
    """CHECK name -> expression of `insulin_pen` (code §11.2.7, measurement §8.4)."""
    return {
        "ck_insulin_pen_format": f"format IN ({sql_in_list(PenFormat)})",
        "ck_insulin_pen_capacity_units": _range_check("capacity_units", PEN_UNITS_RANGE),
        "ck_insulin_pen_expires_after_opened": "expires_at > opened_at",
        "ck_insulin_pen_closed_after_opened": "closed_at IS NULL OR closed_at >= opened_at",
        "ck_insulin_pen_closed_reason": f"closed_reason IS NULL OR closed_reason IN ({sql_in_list(PenCloseReason)})",
        "ck_insulin_pen_closed_reason_iff_closed": "(closed_at IS NULL) = (closed_reason IS NULL)",
    }


class DBSchema:
    extensions = """
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    """
    
    users = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        username VARCHAR(50) NOT NULL,
        password_hash TEXT NOT NULL,
        -- Reserved on purpose: no endpoint, service or query uses it yet.
        -- It is kept ready for a future roles/permissions system (e.g.
        -- telling admin accounts apart from regular ones) without having
        -- to migrate the schema when it is needed.
        -- Do not implement authorization logic based on this column
        -- without documenting the decision first (see CLAUDE.md, missing
        -- conventions).
        category VARCHAR(255) CHECK (category IN ('admin', 'common')),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        last_login_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """
    # The unique indexes on normalized email/username do NOT go here: on a
    # legacy install (`mail` column, no `username` yet) this statement would
    # run before _ensure_users_schema migrates those columns, and the
    # CREATE INDEX would fail on a missing column. _ensure_users_schema creates
    # them (idempotent, IF NOT EXISTS) once the schema is migrated — see db_init.py.

    auth_sessions = """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        id BIGSERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        session_token_hash CHAR(64) NOT NULL,
        csrf_token_hash CHAR(64) NOT NULL,
        ip_hash CHAR(64),
        user_agent_hash CHAR(64),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMPTZ NOT NULL,
        revoked_at TIMESTAMPTZ,
        CONSTRAINT fk_auth_sessions_user_id_users
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        CONSTRAINT uq_auth_sessions_session_token_hash
            UNIQUE (session_token_hash),
        CONSTRAINT ck_auth_sessions_expiry_after_creation CHECK (expires_at > created_at),
        CONSTRAINT ck_auth_sessions_last_seen_after_creation CHECK (last_seen_at >= created_at),
        CONSTRAINT ck_auth_sessions_revoked_after_creation CHECK (revoked_at IS NULL OR revoked_at >= created_at)
    );
    CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at);
    CREATE INDEX IF NOT EXISTS idx_auth_sessions_revoked_at ON auth_sessions(revoked_at);
    """

    auth_rate_limits = """
    CREATE TABLE IF NOT EXISTS auth_rate_limits (
        key_hash CHAR(64) PRIMARY KEY,
        attempts INTEGER NOT NULL DEFAULT 0,
        first_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        blocked_until TIMESTAMPTZ,
        CONSTRAINT ck_auth_rate_limits_attempts_non_negative CHECK (attempts >= 0),
        CONSTRAINT ck_auth_rate_limits_blocked_after_first CHECK (blocked_until IS NULL OR blocked_until >= first_attempt_at)
    );
    """

    food_brands = """
    CREATE TABLE IF NOT EXISTS food_brands (
        id SERIAL PRIMARY KEY,
        code VARCHAR(255) NOT NULL,          -- normalized stable key
        label VARCHAR(255) NOT NULL,         -- visible label, exactly as the user writes it
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_by INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_food_brands_created_by_users
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
        CONSTRAINT ck_food_brands_code_normalized
            CHECK (code = regexp_replace(btrim(lower(code)), '\\s+', ' ', 'g')),
        CONSTRAINT ck_food_brands_label_not_blank
            CHECK (btrim(label) <> '')
    );
    """
    # uq_food_brands_code does NOT go here for the same reason as in `users`: on
    # a legacy install (`name` column, no `code` yet) the CREATE INDEX would
    # fail before _ensure_food_brands_schema migrates the column.
    # _ensure_food_brands_schema creates it (idempotent) after the migration.

    @classmethod
    def insulin_injections(cls):
        """Generate insulin_injections table SQL with enums as source of truth."""
        insulin_type_list = sql_in_list(InsulinType)
        injection_zone_list = sql_in_list(InjectionZone)
        return f"""
    CREATE TABLE IF NOT EXISTS insulin_injections (
        id SERIAL PRIMARY KEY,
        users_id INTEGER NOT NULL,
        intake_event_id INTEGER,
        shot_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        insulin_type VARCHAR(20) NOT NULL,
        units REAL,
        injection_zone VARCHAR(50),
        notes TEXT,
        needle_leak BOOLEAN,
        skin_pinch BOOLEAN,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        timezone_at_event TEXT NOT NULL DEFAULT 'Europe/Madrid',
        -- The pen it came from; NULL only before pens existed (measurement 8.4).
        -- Deferred NO ACTION (code 11.2.7): a used pen is closed, never deleted.
        insulin_pen_id INTEGER
            CONSTRAINT fk_insulin_injections_insulin_pen_id_insulin_pen
            REFERENCES insulin_pen(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
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

    @classmethod
    def meal_type_schedule(cls):
        """
        Generate meal_type_schedule table SQL. Per-user time slots for the
        meal_type assigned automatically to an intake_event created without
        going through the cart (decision 2026-09-11). There is only one row per
        (users_id, meal_type) when the user has customized that slot from
        /settings/meal_type_schedule; if there is no row, the default lives in
        code (domain/meal_type_schedule.py:DEFAULT_MEAL_TYPE_WINDOWS), not in
        the database, so no rows need to be seeded when a new user signs up.

        meal_type is restricted to AUTO_ASSIGNABLE_MEAL_TYPES, not to the full
        MealType enum: snack and rescue are always manual and must never be
        able to have a time slot here.
        """
        auto_meal_type_list = sql_in_list(AUTO_ASSIGNABLE_MEAL_TYPES)
        return f"""
    CREATE TABLE IF NOT EXISTS meal_type_schedule (
        id SERIAL PRIMARY KEY,
        users_id INTEGER NOT NULL
            CONSTRAINT fk_meal_type_schedule_users_id_users
            REFERENCES users(id) ON DELETE CASCADE,
        meal_type VARCHAR(50) NOT NULL
            CONSTRAINT ck_meal_type_schedule_meal_type
            CHECK (meal_type IN ({auto_meal_type_list})),
        start_time TIME NOT NULL,
        end_time TIME NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_meal_type_schedule_users_id_meal_type
            UNIQUE (users_id, meal_type),
        CONSTRAINT ck_meal_type_schedule_start_end_distinct
            CHECK (start_time <> end_time) -- a degenerate slot (start = end) would cover no hour; it is rejected on save and never allowed to persist
    );
    """


    @classmethod
    def catalog(cls):
        """Generate the catalog table SQL with enums and limits as source of truth."""
        check_lines = ",\n".join(
            f"        CONSTRAINT {name} CHECK ({expression})"
            for name, expression in catalog_check_constraints().items()
        )
        return f"""
    -- Owner: created_by. In catalog, creator = owner and there are no transfers
    -- (code_conventions.md §11.2.2). created_by IS NULL = general library: always
    -- published (ck_catalog_library_published), nobody edits, archives or versions it.
    -- Visibility: personal / published (§11.4.1), enforced in SQL.
    -- Lifecycle: archivable, irreversible (no restore_, decision 2026-09-23).
    -- Deleting a user: SET NULL -> their foods join the general library (blocked today, portion_detail H4).
    -- Concurrency: last write wins on edit (§6.7, monousuario; decision in feedback 24).
    -- Uniqueness: partial unique indexes uq_catalog_* live in db_init._ensure_catalog_schema.
    CREATE TABLE IF NOT EXISTS catalog (
        id SERIAL CONSTRAINT pk_catalog PRIMARY KEY,
        created_by INTEGER
            CONSTRAINT fk_catalog_created_by_users
            REFERENCES users(id) ON DELETE SET NULL,
        origin_root_id INTEGER
            CONSTRAINT fk_catalog_origin_root_id_catalog
            REFERENCES catalog(id) ON DELETE SET NULL,
        name VARCHAR(255) NOT NULL,
        brand_id INTEGER,
        category VARCHAR(100) NOT NULL,
        subtype VARCHAR(100) NOT NULL,
        initial_state VARCHAR(50),
        nutriscore VARCHAR(1),
        nova INTEGER,
        yuka INTEGER,
        default_portion REAL,
        calories_100g REAL,
        carbs_100g REAL,
        sugars_100g REAL,
        fats_100g REAL,
        saturated_100g REAL,
        proteins_100g REAL,
        fiber_100g REAL,
        caffeine REAL,
        alcohol REAL,
        barcode VARCHAR(48),
        cooking_factor REAL,
        macros_quality BOOLEAN, -- the food's data, read live by portions (measurement §6.11)
        default_strictly_weighed BOOLEAN, -- copied to each new portion (measurement §6.11)
        macros_confidence INTEGER, -- declared 0-2 (measurement §6.10)
        prefill_source VARCHAR(20), -- where the form's first values came from; the saved values are the user's (measurement §12.1)
        prefill_source_id VARCHAR(64),
        search_name TEXT GENERATED ALWAYS AS ({search_text_sql("name")}) STORED, -- what the search compares with (§11.7)
        is_published BOOLEAN NOT NULL DEFAULT FALSE,
        deleted_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_catalog_brand_id_food_brands
            FOREIGN KEY (brand_id) REFERENCES food_brands(id) ON DELETE SET NULL,
{check_lines}
    );
    """

    @classmethod
    def manual_intake(cls):
        """Generate the manual_intake table SQL with enums and limits as source of truth."""
        check_lines = ",\n".join(
            f"        CONSTRAINT {name} CHECK ({expression})"
            for name, expression in manual_intake_check_constraints().items()
        )
        return f"""
    -- Dishes prepared by someone (a place or a person), even when their macros
    -- are known (code_conventions.md §11.2.3).
    -- Owner: created_by, NOT NULL. Creator = owner, no transfers, no general
    -- library of dishes (§11.2.3).
    -- Two kinds of row: reusable dish (is_quick_add = FALSE) and quick add
    -- (is_quick_add = TRUE: never listed, never published, outside the unique indexes).
    -- Visibility: personal / published (§11.4.1), enforced in SQL.
    -- Lifecycle: archivable, irreversible (no restore_), same contract as catalog.
    -- Deleting a user: CASCADE (blocked today by portion_detail RESTRICT, decision 2026-09-22).
    -- Concurrency: last write wins on edit (§6.7, §6.10, §11.2.3).
    -- Uniqueness: partial unique indexes uq_manual_intake_* live in db_init._ensure_manual_intake_schema.
    CREATE TABLE IF NOT EXISTS manual_intake (
        id SERIAL CONSTRAINT pk_manual_intake PRIMARY KEY,
        created_by INTEGER NOT NULL
            CONSTRAINT fk_manual_intake_created_by_users
            REFERENCES users(id) ON DELETE CASCADE,
        origin_root_id INTEGER
            CONSTRAINT fk_manual_intake_origin_root_id_manual_intake
            REFERENCES manual_intake(id) ON DELETE SET NULL,
        name VARCHAR(255) NOT NULL, -- stored normalized (domain/food.normalize_food_text)
        description TEXT, -- domain limit 500 (MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH, §7.3); also the quick-add notes
        subtype VARCHAR(100), -- optional (decision 2026-10-09)
        origin VARCHAR(255), -- who or where made it; free text, stored normalized; part of the duplicate concept
        default_portion REAL, -- serving in g; NULL = no serving (measurement §5.3)
        calories_100g REAL,
        carbs_100g REAL NOT NULL, -- 0 is valid; "unknown" is not (§11.2.3)
        sugars_100g REAL,
        fats_100g REAL,
        saturated_100g REAL,
        proteins_100g REAL,
        fiber_100g REAL,
        caffeine REAL, -- mg/100 g
        alcohol REAL, -- g/100 g
        glycemic_index VARCHAR(20), -- declared absorption speed (measurement §5.5)
        ig_confidence INTEGER, -- declared 0-2 (measurement §6.10)
        macros_confidence INTEGER, -- declared 0-2 (measurement §6.10)
        macros_quality BOOLEAN, -- the dish's data, read live by portions (measurement §6.11)
        default_strictly_weighed BOOLEAN, -- copied to each new portion (measurement §6.11)
        is_quick_add BOOLEAN NOT NULL DEFAULT FALSE,
        is_published BOOLEAN NOT NULL DEFAULT FALSE,
        deleted_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
{check_lines}
    );
    """

    @classmethod
    def ciqual_food(cls):
        """Local copy of Ciqual (measurement_conventions.md §12.3)."""
        return f"""
    -- Reference data with no owner, read-only for the app (db_init revokes its
    -- writes). Each load replaces the whole table (scripts/ciqual/load_ciqual.sh).
    CREATE TABLE IF NOT EXISTS ciqual_food (
        code INTEGER CONSTRAINT pk_ciqual_food PRIMARY KEY,
        name_es VARCHAR(255) NOT NULL,
        name_en VARCHAR(255) NOT NULL,
        name_fr VARCHAR(255) NOT NULL,
        category_hint VARCHAR(255),
        subtype VARCHAR(100),
        calories_100g REAL,
        carbs_100g REAL NOT NULL,
        sugars_100g REAL,
        fats_100g REAL NOT NULL,
        saturated_100g REAL,
        proteins_100g REAL NOT NULL,
        fiber_100g REAL,
        alcohol REAL,
        carbs_confidence VARCHAR(1),
        fats_confidence VARCHAR(1),
        proteins_confidence VARCHAR(1),
        value_notes VARCHAR(255), -- original "traces" (stored as 0) or "< x" (stored as x/2)
        export_date DATE NOT NULL,
        search_text TEXT GENERATED ALWAYS AS ({search_text_sql("name_es || ' ' || name_en")}) STORED
    );
    """

    @classmethod
    def off_product(cls):
        """Local copy of Open Food Facts (measurement_conventions.md §12.2)."""
        return f"""
    -- Reference data with no owner: visible to every user and read-only for the
    -- app (db_init revokes its writes). Each load replaces the whole table, in
    -- one transaction (scripts/off/load_off.sh). Filters: measurement §12.2.
    CREATE TABLE IF NOT EXISTS off_product (
        code VARCHAR({CATALOG_BARCODE_MAX_LENGTH}) CONSTRAINT pk_off_product PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        brand VARCHAR(255),
        categories TEXT,
        calories_100g REAL,
        carbs_100g REAL NOT NULL,
        sugars_100g REAL,
        fats_100g REAL NOT NULL,
        saturated_100g REAL,
        proteins_100g REAL NOT NULL,
        fiber_100g REAL,
        caffeine REAL, -- mg/100 g
        alcohol_vol REAL, -- % vol, as OFF declares it; converted on prefill
        default_portion REAL,
        nutriscore VARCHAR(1),
        nova INTEGER,
        ciqual_food_code INTEGER,
        unique_scans_n INTEGER,
        source_modified_at TIMESTAMPTZ,
        export_date DATE NOT NULL,
        name_is_store_brand BOOLEAN NOT NULL DEFAULT FALSE, -- out of the text search, still found by barcode (measurement §12.2)
        search_text TEXT GENERATED ALWAYS AS ({search_text_sql("name || ' ' || coalesce(brand, '')")}) STORED,
        CONSTRAINT ck_off_product_code_format
            CHECK (code ~ '^[0-9]{{{CATALOG_BARCODE_MIN_LENGTH},{CATALOG_BARCODE_MAX_LENGTH}}}$')
    );
    """

    @classmethod
    def insulin_brand(cls):
        """An insulin as the user uses it: name, type, days in use and units per pen.
        Hybrid by use (code_conventions.md §11.2.7): archived if a pen uses it."""
        check_lines = ",\n".join(
            f"        CONSTRAINT {name} CHECK ({expression})"
            for name, expression in insulin_brand_check_constraints().items()
        )
        return f"""
    CREATE TABLE IF NOT EXISTS insulin_brand (
        id SERIAL CONSTRAINT pk_insulin_brand PRIMARY KEY,
        users_id INTEGER NOT NULL
            CONSTRAINT fk_insulin_brand_users_id_users
            REFERENCES users(id) ON DELETE CASCADE,
        name VARCHAR(100) NOT NULL, -- stored normalized; unique per user among active brands (uq_insulin_brand_users_id_name)
        insulin_type VARCHAR(20) NOT NULL, -- InsulinType; fixed once a pen uses the brand (measurement 8.4)
        in_use_days INTEGER NOT NULL DEFAULT {DEFAULT_IN_USE_DAYS}, -- days a pen keeps once opened
        pen_units REAL NOT NULL DEFAULT {DEFAULT_PEN_UNITS:g}, -- units in a full pen
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMPTZ, -- archived: it had pens when it was deleted (§11.2.7)
{check_lines}
    );
    """

    @classmethod
    def insulin_pen(cls):
        """One insulin pen or cartridge taken out of the fridge. Hybrid by use, like
        `fridge` (code_conventions.md §11.2.7); what is left is computed live
        from its injections (measurement_conventions.md §8.4)."""
        check_lines = ",\n".join(
            f"        CONSTRAINT {name} CHECK ({expression})"
            for name, expression in insulin_pen_check_constraints().items()
        )
        return f"""
    CREATE TABLE IF NOT EXISTS insulin_pen (
        id SERIAL CONSTRAINT pk_insulin_pen PRIMARY KEY,
        users_id INTEGER NOT NULL
            CONSTRAINT fk_insulin_pen_users_id_users
            REFERENCES users(id) ON DELETE CASCADE,
        -- Deferred NO ACTION (§11.2.7): a brand used by a pen is archived, never deleted.
        insulin_brand_id INTEGER NOT NULL
            CONSTRAINT fk_insulin_pen_insulin_brand_id_insulin_brand
            REFERENCES insulin_brand(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
        format VARCHAR(20) NOT NULL, -- PenFormat
        opened_at TIMESTAMPTZ NOT NULL, -- taken out of the fridge
        expires_at TIMESTAMPTZ NOT NULL, -- opened_at + the brand's days in use; editable
        capacity_units REAL NOT NULL, -- copied from the brand; editable
        closed_at TIMESTAMPTZ, -- NULL = in use
        closed_reason VARCHAR(20), -- PenCloseReason; NULL iff open
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
{check_lines}
    );
    """

    @classmethod
    def fridge(cls):
        """A container in the fridge or the freezer. Lifecycle and contract:
        code_conventions.md §11.2.6; model: measurement_conventions.md §4.8."""
        check_lines = ",\n".join(
            f"        CONSTRAINT {name} CHECK ({expression})" for name, expression in fridge_check_constraints().items()
        )
        return f"""
    CREATE TABLE IF NOT EXISTS fridge (
        id SERIAL CONSTRAINT pk_fridge PRIMARY KEY,
        users_id INTEGER NOT NULL
            CONSTRAINT fk_fridge_users_id_users
            REFERENCES users(id) ON DELETE CASCADE,
        name VARCHAR(255), -- NULL = name derived from its ingredients (measurement 4.6.3); stored normalized
        location VARCHAR(20) NOT NULL, -- StorageLocation: where it is now; past places are in fridge_move
        stored_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, -- when it entered the fridge or the freezer
        expires_at TIMESTAMPTZ NOT NULL, -- set by the app from domain.fridge.default_expires_at; editable (4.8.2)
        content_weight REAL, -- real weight of the content in grams, weighed by the user; never derived from the portions (4.8.3)
        closed_at TIMESTAMPTZ, -- NULL = still in the fridge or the freezer (§11.2.6)
        closed_reason VARCHAR(20), -- FridgeCloseReason: emptied (can reopen) or discarded; NULL iff open
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
{check_lines}
    );
    """

    # Dependent of `fridge` (code_conventions.md §11.2.1): each row is one change of
    # place, the history the study reads to know how long a container was frozen
    # (measurement_conventions.md 4.8.4). Rows are never updated.
    fridge_move = f"""
    CREATE TABLE IF NOT EXISTS fridge_move (
        id SERIAL CONSTRAINT pk_fridge_move PRIMARY KEY,
        fridge_id INTEGER NOT NULL
            CONSTRAINT fk_fridge_move_fridge_id_fridge
            REFERENCES fridge(id) ON DELETE CASCADE,
        from_location VARCHAR(20) NOT NULL
            CONSTRAINT ck_fridge_move_from_location
            CHECK (from_location IN ({sql_in_list(StorageLocation)})),
        to_location VARCHAR(20) NOT NULL
            CONSTRAINT ck_fridge_move_to_location
            CHECK (to_location IN ({sql_in_list(StorageLocation)})),
        moved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_fridge_move_locations_differ CHECK (from_location <> to_location)
    );
    """

    @classmethod
    def tags(cls):
        """System tags (no owner, SystemTag key) and personal tags of one user
        (code_conventions.md §11.2.8). Unique indexes in db_init._ensure_tags_schema."""
        check_lines = ",\n".join(
            f"        CONSTRAINT {name} CHECK ({expression})" for name, expression in tags_check_constraints().items()
        )
        return f"""
    CREATE TABLE IF NOT EXISTS tags (
        id SERIAL CONSTRAINT pk_tags PRIMARY KEY,
        users_id INTEGER -- owner of a personal tag; NULL on a system tag
            CONSTRAINT fk_tags_users_id_users
            REFERENCES users(id) ON DELETE CASCADE,
        system_key VARCHAR(32), -- SystemTag; identifies a system tag, whose name is never shown (§11.2.8)
        name VARCHAR(100) NOT NULL, -- stored normalized; unique per owner ignoring case (uq_tags_users_id_name)
        color VARCHAR(64) NOT NULL DEFAULT 'hsl(0 80% 90%)', -- #RRGGBB or hsl(); ends in a style attribute
        description TEXT, -- unused for now (phase 2)
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
{check_lines}
    );
    """

    @classmethod
    def recipe(cls):
        """Lifecycle and contract: code_conventions.md §11.2.4."""
        check_lines = ",\n".join(
            f"        CONSTRAINT {name} CHECK ({expression})" for name, expression in recipe_check_constraints().items()
        )
        return f"""
    -- Uniqueness: partial unique indexes uq_recipe_* live in db_init._ensure_recipe_schema.
    CREATE TABLE IF NOT EXISTS recipe (
        id SERIAL CONSTRAINT pk_recipe PRIMARY KEY,
        users_id INTEGER NOT NULL
            CONSTRAINT fk_recipe_users_id_users
            REFERENCES users(id) ON DELETE CASCADE,
        origin_root_id INTEGER
            CONSTRAINT fk_recipe_origin_root_id_recipe
            REFERENCES recipe(id) ON DELETE SET NULL,
        meal_type VARCHAR(50), -- the main one: what an event created from the recipe takes; never rescue
        extra_meal_types VARCHAR(50)[] NOT NULL DEFAULT '{{}}', -- others it is also eaten as; only for search (§11.2.4)
        name VARCHAR(255) NOT NULL, -- stored normalized (domain/food.normalize_food_text)
        notes TEXT, -- free text; domain limit RECIPE_NOTES_MAX_LENGTH (§7.3)
        servings INTEGER, -- NULL = the recipe is added whole (measurement §4.7)
        is_published BOOLEAN NOT NULL DEFAULT FALSE, -- no interface writes it until phase 2 (§11.4.1)
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        search_name TEXT GENERATED ALWAYS AS ({search_text_sql("name")}) STORED,
{check_lines}
    );
    """

    # Dependent of its user and its food (code_conventions.md §11.2.5): a favorite
    # means nothing without either, so all the foreign keys cascade, and nothing
    # clinical reads this table. Rows are never updated: only created_at. The
    # unique indexes are in _ensure_user_favorites_schema, which checks first:
    # CREATE INDEX IF NOT EXISTS locks the table on every start (§12.2).
    user_favorites = """
    CREATE TABLE IF NOT EXISTS user_favorites (
        id BIGSERIAL CONSTRAINT pk_user_favorites PRIMARY KEY,
        user_id INTEGER NOT NULL
            CONSTRAINT fk_user_favorites_user_id_users REFERENCES users(id) ON DELETE CASCADE,
        catalog_id INTEGER
            CONSTRAINT fk_user_favorites_catalog_id_catalog REFERENCES catalog(id) ON DELETE CASCADE,
        manual_intake_id INTEGER
            CONSTRAINT fk_user_favorites_manual_intake_id_manual_intake REFERENCES manual_intake(id) ON DELETE CASCADE,
        recipe_id INTEGER
            CONSTRAINT fk_user_favorites_recipe_id_recipe REFERENCES recipe(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_user_favorites_one_entry CHECK (num_nonnulls(catalog_id, manual_intake_id, recipe_id) = 1)
    );
    """

    # Dependent of its user, its tag and its food (code_conventions.md §11.2.8): one
    # user put one tag on one food, dish or recipe. Private: nobody else reads it.
    # Unique indexes in db_init._ensure_tags_schema.
    linked_tags = """
    CREATE TABLE IF NOT EXISTS linked_tags (
        id SERIAL CONSTRAINT pk_linked_tags PRIMARY KEY,
        users_id INTEGER NOT NULL
            CONSTRAINT fk_linked_tags_users_id_users REFERENCES users(id) ON DELETE CASCADE,
        tag_id INTEGER NOT NULL
            CONSTRAINT fk_linked_tags_tag_id_tags REFERENCES tags(id) ON DELETE CASCADE,
        catalog_id INTEGER
            CONSTRAINT fk_linked_tags_catalog_id_catalog REFERENCES catalog(id) ON DELETE CASCADE,
        recipe_id INTEGER
            CONSTRAINT fk_linked_tags_recipe_id_recipe REFERENCES recipe(id) ON DELETE CASCADE,
        manual_intake_id INTEGER
            CONSTRAINT fk_linked_tags_manual_intake_id_manual_intake REFERENCES manual_intake(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_linked_tags_one_entry CHECK (num_nonnulls(catalog_id, recipe_id, manual_intake_id) = 1)
    );
    """

    @classmethod
    def intake_event(cls):
        """Generate intake_event table SQL with enums as source of truth."""
        state_list = sql_in_list(IntakeEventState)
        meal_type_list = sql_in_list(MealType)
        injection_zone_list = sql_in_list(InjectionZone)
        return f"""
    CREATE TABLE IF NOT EXISTS intake_event (
        id SERIAL PRIMARY KEY,
        users_id INTEGER NOT NULL
            CONSTRAINT fk_intake_event_users_id_users
            REFERENCES users(id) ON DELETE CASCADE,

        state VARCHAR(20) NOT NULL
            CONSTRAINT ck_intake_event_state
            CHECK (state IN ({state_list})), -- Determines whether this meal is in the cart (planned) or has been definitively consumed
        meal_type VARCHAR(50)
            CONSTRAINT ck_intake_event_meal_type
            CHECK (meal_type IS NULL OR meal_type IN ({meal_type_list})), -- Should be modifiable while still in the cart, in case it was added late or needs correction
        name VARCHAR(255), -- Name for this meal event, useful when there are multiple carts and the user wants to label each one. Editable at any time.

        meal_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, -- Defaults to the moment it is added, but should be easy to change within the cart
        timezone_at_event TEXT NOT NULL DEFAULT 'Europe/Madrid', -- IANA key of the zone in which the user entered meal_time
        eating_out BOOLEAN DEFAULT FALSE, -- Whether the user is eating out. Adjustable in the cart.
        insulin_dose BOOLEAN DEFAULT TRUE, -- Whether this meal requires an insulin dose. Adjustable in the cart.
        injection_zone VARCHAR(50)
            CONSTRAINT ck_intake_event_injection_zone
            CHECK (injection_zone IS NULL OR injection_zone IN ({injection_zone_list})), -- Temporary selection while the meal is still in the cart; definitive log goes to insulin_injections table when meal is confirmed
        insulin_pen_id INTEGER
            CONSTRAINT fk_intake_event_insulin_pen_id_insulin_pen
            REFERENCES insulin_pen(id) ON DELETE SET NULL, -- Draft like injection_zone: the pen of the bolus, copied to the injection on confirm (measurement 8.4)
        insulin_units REAL
            CONSTRAINT ck_intake_event_insulin_units
            CHECK (insulin_units IS NULL OR (insulin_units > 0 AND (insulin_units * 2) = floor(insulin_units * 2))), -- Draft dose of the bolus in U, same rule as insulin_injections.units (measurement 8.1)

        ingested_amount REAL
            CONSTRAINT ck_intake_event_ingested_amount
            CHECK (ingested_amount IS NULL OR (ingested_amount >= 0 AND ingested_amount <= 100000)), -- Snapshot set once at confirm: sum of amount from portion_detail (already scaled to what was actually eaten) at that instant. total_amount is never stored; it is computed live as SUM(amount) whenever needed (decision 2026-09-10). 100000 g (100 kg) is a sanity ceiling, not a clinical one (measurement_conventions.md §6.9.2, decision 2026-09-10).

        amount_confidence REAL
            CONSTRAINT ck_intake_event_amount_confidence
            CHECK (amount_confidence >= 0 AND amount_confidence <= 1), -- Weighted average based on each food's amount and whether it was strictly weighed: (amount1 * strictly_weighed1 + amount2 * strictly_weighed2) divided by the live sum of portion_detail.amount for the event (total_amount is not a column; see cart_shared.calculate_macro_summary_metrics, decision 2026-09-10)

        -- quality_confidence and the six *_coverage are not stored: they depend on
        -- the food's macros and macros_quality, so they are computed live from the
        -- portions (measurement_conventions.md §6.9.4).

        notes TEXT, -- Free-text note about the meal, edited from the cart card (input above "Confirm meal"). No physical limit: the 500-character cap is a domain rule (INTAKE_EVENT_NOTES_MAX_LENGTH in domain/intake_event.py), enforced at the boundary with 422 and never truncated (decision 2026-09-10, §7.3)
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMPTZ  -- soft delete; only used in state='consumed' (decision 2026-09-08)
    );
    """

    intake_plate = """
    CREATE TABLE IF NOT EXISTS intake_plate (
        id SERIAL CONSTRAINT pk_intake_plate PRIMARY KEY,
        intake_event_id INTEGER NOT NULL
            CONSTRAINT fk_intake_plate_intake_event_id_intake_event
            REFERENCES intake_event(id) ON DELETE CASCADE, -- A plate only exists inside its event

        name VARCHAR(255), -- NULL means the name is derived from the plate's first two ingredients (measurement_conventions.md 4.6.3); writing a name freezes it
        offset_minutes INTEGER
            CONSTRAINT ck_intake_plate_offset_minutes
            CHECK (offset_minutes IS NULL OR (offset_minutes >= -300 AND offset_minutes <= 300)), -- Template inherited by the portions added to this plate, not a clinical value; same sanity range as portion_detail.offset_minutes (measurement_conventions.md 4.5, 4.6.2)

        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """

    recipe_plate = """
    -- Plates of a recipe (measurement_conventions.md 4.7). No offset: it is born when
    -- the recipe enters an event. The position order is deferrable so two plates can
    -- exchange it in one statement.
    CREATE TABLE IF NOT EXISTS recipe_plate (
        id SERIAL CONSTRAINT pk_recipe_plate PRIMARY KEY,
        recipe_id INTEGER NOT NULL
            CONSTRAINT fk_recipe_plate_recipe_id_recipe
            REFERENCES recipe(id) ON DELETE CASCADE,
        position INTEGER NOT NULL CONSTRAINT ck_recipe_plate_position CHECK (position >= 1),
        name VARCHAR(255), -- NULL = name derived from its ingredients (4.6.3)
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_recipe_plate_recipe_id_position UNIQUE (recipe_id, position) DEFERRABLE INITIALLY IMMEDIATE,
        CONSTRAINT uq_recipe_plate_recipe_id_id UNIQUE (recipe_id, id) -- target of the composite FK of portion_detail
    );
    """

    portion_detail = f"""
    CREATE TABLE IF NOT EXISTS portion_detail (
        id SERIAL CONSTRAINT pk_portion_detail PRIMARY KEY,

        -- ARC 1: Origin
        catalog_id INTEGER
            CONSTRAINT fk_portion_detail_catalog_id_catalog
            REFERENCES catalog(id) ON DELETE RESTRICT,
        manual_intake_id INTEGER
            CONSTRAINT fk_portion_detail_manual_intake_id_manual_intake
            REFERENCES manual_intake(id) ON DELETE RESTRICT,
        CONSTRAINT ck_portion_detail_single_origin
            CHECK (num_nonnulls(catalog_id, manual_intake_id) = 1),
        
        -- ARC 2: Destination
        intake_event_id INTEGER
            CONSTRAINT fk_portion_detail_intake_event_id_intake_event
            REFERENCES intake_event(id) ON DELETE CASCADE,
        fridge_id INTEGER
            CONSTRAINT fk_portion_detail_fridge_id_fridge
            REFERENCES fridge(id) ON DELETE CASCADE,
        recipe_id INTEGER
            CONSTRAINT fk_portion_detail_recipe_id_recipe
            REFERENCES recipe(id) ON DELETE CASCADE,
        CONSTRAINT ck_portion_detail_single_destination
            CHECK (num_nonnulls(intake_event_id, fridge_id, recipe_id) = 1),
        source_fridge_id INTEGER
            CONSTRAINT fk_portion_detail_source_fridge_id_fridge
            REFERENCES fridge(id) ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED, -- The container an event portion was taken from (measurement 4.8.4). An eaten portion is clinical history, so a referenced container cannot be deleted (code §11.2.6). Deferred on purpose (code §11.8): RESTRICT, or a non-deferred NO ACTION, is checked inside each cascade, so deleting a user failed when it reached the container before the event portion that references it
        CONSTRAINT ck_portion_detail_source_fridge_only_for_event
            CHECK (source_fridge_id IS NULL OR intake_event_id IS NOT NULL),

        plate_id INTEGER
            CONSTRAINT fk_portion_detail_plate_id_intake_plate
            REFERENCES intake_plate(id) ON DELETE RESTRICT, -- Which plate (serving) of the event this portion belongs to; deleting a plate with portions is blocked on purpose (measurement_conventions.md 4.6.5)
        CONSTRAINT ck_portion_detail_plate_only_for_event
            CHECK ((intake_event_id IS NULL) = (plate_id IS NULL)), -- An event portion must have a plate; a fridge/recipe portion must not
        recipe_plate_id INTEGER, -- Which plate of the recipe; the composite FK guarantees it is of that same recipe (4.7)
        CONSTRAINT ck_portion_detail_recipe_plate_only_for_recipe
            CHECK ((recipe_id IS NULL) = (recipe_plate_id IS NULL)),
        CONSTRAINT fk_portion_detail_recipe_plate_id_recipe_plate
            FOREIGN KEY (recipe_id, recipe_plate_id) REFERENCES recipe_plate (recipe_id, id) ON DELETE RESTRICT,
        -- Uniqueness of a food inside a plate (measurement_conventions.md 4.6.4) is a PARTIAL unique
        -- index and therefore lives in db_init._ensure_portion_detail_schema, not here: a partial
        -- index cannot be declared inline in CREATE TABLE.


        amount REAL NOT NULL
            CONSTRAINT ck_portion_detail_amount_range
            CHECK (amount > 0 AND amount <= 100000), -- The only amount column of the table (decision 2026-09-18): the quantity of this food in its destination, in grams. While the event is 'planned' it is the served amount; at confirm it is overwritten once with what was actually eaten (measurement_conventions.md 4.4). The cooked amount is NOT stored: it only exists as a form field when plating. 100000 g is the same sanity ceiling as intake_event.ingested_amount (6.9.2); the lower bound is > 0 (decision 2026-09-22): an unconsumed ingredient is deleted, not set to zero. NaN/Infinity are rejected by this same CHECK.
        cooking VARCHAR(50)
            CONSTRAINT ck_portion_detail_cooking
            CHECK (cooking IS NULL OR cooking IN ({_PORTION_PREPARATION_LISTS['cooking']})), -- Cooking method, used to evaluate its effect on blood sugar levels. Default: griddle
        conservation VARCHAR(50)
            CONSTRAINT ck_portion_detail_conservation
            CHECK (conservation IS NULL OR conservation IN ({_PORTION_PREPARATION_LISTS['conservation']})), -- Storage method
        final_state VARCHAR(50)
            CONSTRAINT ck_portion_detail_final_state
            CHECK (final_state IS NULL OR final_state IN ({_PORTION_PREPARATION_LISTS['final_state']})), -- Final state, in case the state changed from the initial one
        ripeness VARCHAR(50)
            CONSTRAINT ck_portion_detail_ripeness
            CHECK (ripeness IS NULL OR ripeness IN ({_PORTION_PREPARATION_LISTS['ripeness']})), -- Ripeness of a fruit, seen by eye; meal portions of a `fruits` food only (study_conventions.md 6.3). NULL = not given
        strictly_weighed BOOLEAN, -- Whether or not the food was weighed before consumption. NULL means "no data" and is a state of its own, not FALSE (decision 2026-09-18)
        macros_quality BOOLEAN, -- UNUSED since 2026-10-09: the quality is the food's (catalog/manual_intake.macros_quality, read live, measurement §6.11). Kept with its values until versioning (portion_detail H1)
        
        is_cooked_weight BOOLEAN DEFAULT FALSE, -- If the food was weighed already cooked, catalog.cooking_factor back-calculates the raw weight ONLY inside the macro calculation; `amount` always keeps what the user weighed and is never overwritten (measurement_conventions.md 5.2, decision 2026-09-18). Only for catalog origins.
        offset_minutes INTEGER
            CONSTRAINT ck_portion_detail_offset_minutes
            CHECK (offset_minutes IS NULL OR (offset_minutes >= -300 AND offset_minutes <= 300)), -- Minutes between the event's meal_time and the moment this food is eaten. Literal value, never recalculated (measurement_conventions.md 4.5); inherited from its plate on insert (4.6.2).

        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT ck_portion_detail_offset_only_for_event
            CHECK (offset_minutes IS NULL OR intake_event_id IS NOT NULL),
        CONSTRAINT ck_portion_detail_ripeness_event
            CHECK (ripeness IS NULL OR intake_event_id IS NOT NULL)
    );
    """
