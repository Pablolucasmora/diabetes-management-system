"""Database schema definitions.

Uses domain constants (InsulinType, InjectionZone) to generate CHECKs
dynamically where applicable, ensuring a single source of truth.
"""

from DayBetes_food.domain.constants import IntakeEventState, InsulinType, InjectionZone, MealType, sql_in_list
from DayBetes_food.domain.meal_type_schedule import AUTO_ASSIGNABLE_MEAL_TYPES


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
        -- Reservada a propósito: no la usa ningún endpoint, servicio ni
        -- query todavía. Se deja preparada para un futuro sistema de
        -- roles/permisos (p.ej. distinguir cuentas admin de cuentas
        -- normales) sin tener que migrar el esquema cuando haga falta.
        -- No implementar lógica de autorización basada en esta columna
        -- sin antes documentar la decisión (ver CLAUDE.md, convenciones
        -- faltantes).
        category VARCHAR(255) CHECK (category IN ('admin', 'common')),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        last_login_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """
    # Los índices únicos sobre email/username normalizados NO van aquí: en una
    # instalación heredada (columna `mail`, sin `username` todavía) esta sentencia
    # se ejecutaría antes de que _ensure_users_schema migre esas columnas, y el
    # CREATE INDEX fallaría por columna inexistente. _ensure_users_schema los crea
    # (idempotente, IF NOT EXISTS) una vez migrado el esquema — ver db_init.py.

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
        code VARCHAR(255) NOT NULL,          -- clave estable normalizada
        label VARCHAR(255) NOT NULL,         -- etiqueta visible, tal cual la escribe el usuario
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
    # uq_food_brands_code NO va aquí por el mismo motivo que en `users`: en una
    # instalación heredada (columna `name`, sin `code` todavía) el CREATE INDEX
    # fallaría antes de que _ensure_food_brands_schema migre la columna.
    # _ensure_food_brands_schema lo crea (idempotente) tras la migración.

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
        Generate meal_type_schedule table SQL. Franjas horarias, por usuario,
        para el meal_type que se asigna automáticamente a un intake_event
        creado sin pasar por el carrito (decisión 2026-09-11). Solo existe una
        fila por (users_id, meal_type) cuando el usuario ha personalizado esa
        franja desde /settings/meal_type_schedule; si no hay fila, el default
        vive en código (domain/meal_type_schedule.py:DEFAULT_MEAL_TYPE_WINDOWS),
        no en la base, para no tener que sembrar filas al dar de alta un
        usuario nuevo.

        meal_type está restringido a AUTO_ASSIGNABLE_MEAL_TYPES, no al enum
        MealType completo: snack y rescue son siempre manuales y nunca deben
        poder tener una franja horaria aquí.
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
            CHECK (start_time <> end_time) -- una franja degenerada (start = end) no cubriría ninguna hora; se rechaza al guardar, no se permite persistirla
    );
    """


    catalog = """
    CREATE TABLE IF NOT EXISTS catalog (
        id SERIAL PRIMARY KEY,
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        origin_root_id INTEGER REFERENCES catalog(id) ON DELETE SET NULL,
        name VARCHAR(255) NOT NULL, -- Product name
        brand_id INTEGER, -- FK a food_brands; NULL = sin marca
        category VARCHAR(100) NOT NULL,
        subtype VARCHAR(100) NOT NULL, -- More specific food category (e.g. yogurt, milk, biscuit, turkey, sweet potato, avocado...). This variable will also be used in the future to estimate macros based on meals of the same subtype for which we have nutritional info.
        initial_state VARCHAR(50) CHECK (
            initial_state IN ('solid', 'mashed/creamy', 'liquid', 'gel')
        ), 
        
        nutriscore VARCHAR(1) CHECK (nutriscore IN ('A', 'B', 'C', 'D', 'E')),
        NOVA INTEGER CHECK (NOVA BETWEEN 1 AND 4),
        yuka INTEGER CHECK (yuka BETWEEN 0 AND 100),
        
        default_portion REAL DEFAULT 100, -- Default portion size for the food, which will be used as the default amount added to the cart when no other quantity is specified
        
        calories_100g REAL,
        carbs_100g REAL,
        sugars_100g REAL,
        fats_100g REAL,
        saturated_100g REAL,
        proteins_100g REAL,
        fiber_100g REAL,
        
        caffeine REAL,
        alcohol REAL,
        
        barcode VARCHAR,
        cooking_factor REAL DEFAULT 1.0, -- Cooking factor, in case it is needed at some point to calculate the real raw weight

        is_private BOOLEAN NOT NULL DEFAULT FALSE, -- True: only creator can view it
        deleted_at TIMESTAMP NULL, -- Logical deletion timestamp
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_catalog_brand_id_food_brands
            FOREIGN KEY (brand_id) REFERENCES food_brands(id) ON DELETE SET NULL
    );
    """

    manual_intake = """
    CREATE TABLE IF NOT EXISTS manual_intake ( -- Table used when consuming already-prepared dishes outside, for which we don't know the exact nutritional characteristics
        id SERIAL PRIMARY KEY,
        created_by INTEGER REFERENCES users(id) ON DELETE CASCADE,
        origin_root_id INTEGER REFERENCES manual_intake(id) ON DELETE SET NULL,
        name VARCHAR(255) NOT NULL, -- Name of this manual meal, such as "uni cafeteria cake", "grandma's stew"
        description TEXT, -- Description of the dish (optional), which will be used to more precisely determine its nutritional info if an AI is integrated
        subtype VARCHAR(100) NOT NULL, -- More specific product category, same as in catalog. This variable will also be used in the future to estimate macros based on meals of the same subtype for which we have nutritional info.
        origin VARCHAR(255), -- Where it comes from: grandma's, Burger King, Saona, Big Twins, Subway... (to allow reuse when visiting the same place again). These meals should be updatable each time the user consumes from that place in case something has changed.

        amount_g REAL NOT NULL,
        calories_100g REAL,
        carbs_100g REAL,
        sugars_100g REAL,
        fats_100g REAL,
        saturated_100g REAL,
        proteins_100g REAL,
        fiber_100g REAL,

        caffeine REAL,
        alcohol REAL,

        glycemic_index VARCHAR(20) CHECK (
            glycemic_index IN ('high', 'medium', 'low')
        ), -- Estimated glycemic index of the meal
        ig_confidence INTEGER CHECK (ig_confidence BETWEEN 1 AND 5), -- Confidence level with which the glycemic index value above was established
        is_private BOOLEAN NOT NULL DEFAULT FALSE, -- True: only creator can view it
        deleted_at TIMESTAMP NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """

    fridge = """
    CREATE TABLE IF NOT EXISTS fridge (
        id SERIAL PRIMARY KEY,
        users_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        tupper_name VARCHAR(255), -- Name given to the container, e.g. "Monday Carrillera"
        entry_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
        is_compound BOOLEAN DEFAULT FALSE, -- Whether it has more than one ingredient
        total_tupper_weight REAL -- For display purposes on the fridge page
    );
    """

    tags = """
    CREATE TABLE IF NOT EXISTS tags (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) UNIQUE NOT NULL, -- Tag name, such as "low fat", "high protein"...
        color VARCHAR(64) NOT NULL DEFAULT 'hsl(0 80% 90%)',
        description TEXT -- Description of what the tag means
    );
    """

    recipe = """
    CREATE TABLE IF NOT EXISTS recipe (
        id SERIAL PRIMARY KEY, 
        users_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        origin_root_id INTEGER REFERENCES recipe(id) ON DELETE SET NULL,
        meal_type VARCHAR(50) CHECK (
            meal_type IN (
                'breakfast', 'brunch', 'lunch',
                'afternoon_snack', 'dinner', 'snack', 'rescue'
            )
        ), -- Used to set this as the default value in intake_event, making it easier to reuse
        name VARCHAR(255) NOT NULL,
        notes TEXT,
        is_private BOOLEAN NOT NULL DEFAULT FALSE -- True: only owner can view it
    );
    """

    user_favorites = """
    CREATE TABLE IF NOT EXISTS user_favorites (
        id BIGSERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        catalog_id INTEGER REFERENCES catalog(id) ON DELETE CASCADE,
        manual_intake_id INTEGER REFERENCES manual_intake(id) ON DELETE CASCADE,
        recipe_id INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
        CHECK (num_nonnulls(catalog_id, manual_intake_id, recipe_id) = 1)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_user_favorites_catalog
        ON user_favorites(user_id, catalog_id) WHERE catalog_id IS NOT NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS uq_user_favorites_manual
        ON user_favorites(user_id, manual_intake_id) WHERE manual_intake_id IS NOT NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS uq_user_favorites_recipe
        ON user_favorites(user_id, recipe_id) WHERE recipe_id IS NOT NULL;
    """

    linked_tags = """
    CREATE TABLE IF NOT EXISTS linked_tags (
        id SERIAL PRIMARY KEY,
        tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
        
        catalog_id INTEGER REFERENCES catalog(id) ON DELETE CASCADE,
        recipe_id INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
        manual_intake_id INTEGER REFERENCES manual_intake(id) ON DELETE CASCADE,
        
        -- Postgres function to count how many of these fields are non-null.
        -- Ensures the tag is assigned to one and only one entity.
        CHECK (num_nonnulls(catalog_id, recipe_id, manual_intake_id) = 1)
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
        timezone_at_event TEXT NOT NULL DEFAULT 'Europe/Madrid', -- IANA key de la zona en que el usuario introdujo meal_time
        eating_out BOOLEAN DEFAULT FALSE, -- Whether the user is eating out. Adjustable in the cart.
        insulin_dose BOOLEAN DEFAULT TRUE, -- Whether this meal requires an insulin dose. Adjustable in the cart.
        injection_zone VARCHAR(50)
            CONSTRAINT ck_intake_event_injection_zone
            CHECK (injection_zone IS NULL OR injection_zone IN ({injection_zone_list})), -- Temporary selection while the meal is still in the cart; definitive log goes to insulin_injections table when meal is confirmed

        ingested_amount REAL
            CONSTRAINT ck_intake_event_ingested_amount
            CHECK (ingested_amount IS NULL OR (ingested_amount >= 0 AND ingested_amount <= 100000)), -- Snapshot set once at confirm: sum of plate_amount from portion_detail (already scaled to what was actually eaten) at that instant. total_amount is never stored; it is computed live as SUM(plate_amount) whenever needed (decision 2026-09-10). 100000 g (100 kg) is a sanity ceiling, not a clinical one (measurement_conventions.md §6.9.2, decision 2026-09-10).

        amount_confidence REAL
            CONSTRAINT ck_intake_event_amount_confidence
            CHECK (amount_confidence >= 0 AND amount_confidence <= 1), -- Weighted average based on each food's amount and whether it was strictly weighed: (amount1 * strictly_weighed1 + amount2 * strictly_weighed2) divided by the live sum of portion_detail.plate_amount for the event (total_amount is not a column; see cart_shared.calculate_macro_summary_metrics, decision 2026-09-10)
        quality_confidence REAL
            CONSTRAINT ck_intake_event_quality_confidence
            CHECK (quality_confidence >= 0 AND quality_confidence <= 1), -- Value between 0 and 1 indicating confidence in the nutritional information. Same calculation as amount_confidence but using each ingredient's macros_quality

        carbs_uncertainty REAL
            CONSTRAINT ck_intake_event_carbs_uncertainty
            CHECK (carbs_uncertainty >= 0 AND carbs_uncertainty <= 1), -- Automatically calculated as a weighted average of each ingredient's carbs value (which may be a value or None) by its total amount, to indicate how reliable the total macro count is (since None is not the same as 0)
        sugars_uncertainty REAL
            CONSTRAINT ck_intake_event_sugars_uncertainty
            CHECK (sugars_uncertainty >= 0 AND sugars_uncertainty <= 1), -- Same as carbs_uncertainty but for sugars
        fats_uncertainty REAL
            CONSTRAINT ck_intake_event_fats_uncertainty
            CHECK (fats_uncertainty >= 0 AND fats_uncertainty <= 1), -- Same as carbs_uncertainty but for fats
        saturated_uncertainty REAL
            CONSTRAINT ck_intake_event_saturated_uncertainty
            CHECK (saturated_uncertainty >= 0 AND saturated_uncertainty <= 1), -- Same as carbs_uncertainty but for saturated fats
        proteins_uncertainty REAL
            CONSTRAINT ck_intake_event_proteins_uncertainty
            CHECK (proteins_uncertainty >= 0 AND proteins_uncertainty <= 1), -- Same as carbs_uncertainty but for proteins
        fiber_uncertainty REAL
            CONSTRAINT ck_intake_event_fiber_uncertainty
            CHECK (fiber_uncertainty >= 0 AND fiber_uncertainty <= 1), -- Same as carbs_uncertainty but for fiber

        notes TEXT, -- Free-text note about the meal, edited from the cart card (input above "Confirm food"). No physical limit: the 500-character cap is a domain rule (INTAKE_EVENT_NOTES_MAX_LENGTH in domain/intake_event.py), enforced at the boundary with 422 and never truncated (decision 2026-09-10, §7.3)
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        deleted_at TIMESTAMPTZ  -- soft-delete; solo se usa en state='consumed' (decisión 2026-09-08)
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

    portion_detail = """
    CREATE TABLE IF NOT EXISTS portion_detail (
        id SERIAL PRIMARY KEY,

        -- ARC 1: Origin
        catalog_id INTEGER REFERENCES catalog(id) ON DELETE RESTRICT,
        manual_intake_id INTEGER REFERENCES manual_intake(id) ON DELETE RESTRICT,
        CHECK (num_nonnulls(catalog_id, manual_intake_id) = 1),
        
        -- ARC 2: Destination
        intake_event_id INTEGER REFERENCES intake_event(id) ON DELETE CASCADE,
        fridge_id INTEGER REFERENCES fridge(id) ON DELETE CASCADE,
        recipe_id INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
        CHECK (num_nonnulls(intake_event_id, fridge_id, recipe_id) = 1),

        plate_id INTEGER
            CONSTRAINT fk_portion_detail_plate_id_intake_plate
            REFERENCES intake_plate(id) ON DELETE RESTRICT, -- Which plate (serving) of the event this portion belongs to; deleting a plate with portions is blocked on purpose (measurement_conventions.md 4.6.5)
        CONSTRAINT ck_portion_detail_plate_only_for_event
            CHECK ((intake_event_id IS NULL) = (plate_id IS NULL)), -- An event portion must have a plate; a fridge/recipe portion must not
        -- Uniqueness of a food inside a plate (measurement_conventions.md 4.6.4) is a PARTIAL unique
        -- index and therefore lives in db_init._ensure_portion_detail_schema, not here: a partial
        -- index cannot be declared inline in CREATE TABLE.


        amount_g REAL NOT NULL, -- This is the cooked amount of a food item. For example, the user may cook 400g of quinoa but only plate 100g, saving the rest. This amount is then compared to plate_amount, and if greater, the difference is automatically saved to the fridge with the food's id, for easy reuse later.
        cooking VARCHAR(50), -- Cooking method, used to evaluate its effect on blood sugar levels (options: steam, boiled-al-dente, boiled-soft, fried, raw, oven, airfryer, toaster, griddle). Default: griddle
        conservation VARCHAR(50), -- Storage method: freezer, fridge, freshly-made, pre-cooked
        final_state VARCHAR(50), -- Final state among: 'solid', 'mashed/creamy', 'liquid', 'gel' — in case the state changed from the initial one
        strictly_weighed BOOLEAN, -- Whether or not the food was weighed before consumption
        macros_quality BOOLEAN, -- Whether the macros were estimated or read from the product label
        
        plate_amount REAL, -- The amount actually plated. Defaults to the same value as amount_g. While the event is 'planned', this is the served amount; at confirm it is overwritten once with the amount actually consumed (plate_amount * fraction), and stays that way for a 'consumed' event (decision 2026-09-10, measurement_conventions.md §4.4).
        is_cooked_weight BOOLEAN DEFAULT FALSE, -- If the food was weighed already cooked, the cooking_factor is used to back-calculate the raw weight and obtain accurate macros
        offset_minutes INTEGER, -- Only for intake_event. Adjusted during the planning phase (not when added to the cart), and defaults to the difference in minutes between the intake_event timestamp and the moment this food is added to the cart

        CHECK (offset_minutes IS NULL OR intake_event_id IS NOT NULL)
    );
    """
