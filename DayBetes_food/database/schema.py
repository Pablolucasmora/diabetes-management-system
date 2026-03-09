class DBSchema:
    
    users = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) UNIQUE NOT NULL,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        last_login_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """

    auth_sessions = """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        id BIGSERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session_token_hash CHAR(64) UNIQUE NOT NULL,
        csrf_token_hash CHAR(64) NOT NULL,
        ip_hash CHAR(64),
        user_agent_hash CHAR(64),
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        revoked_at TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at);
    """

    auth_rate_limits = """
    CREATE TABLE IF NOT EXISTS auth_rate_limits (
        key_hash CHAR(64) PRIMARY KEY,
        attempts INTEGER NOT NULL DEFAULT 0,
        first_attempt_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        blocked_until TIMESTAMP
    );
    """

    food_brands = """
    CREATE TABLE IF NOT EXISTS food_brands (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) UNIQUE NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """


    catalog = """
    CREATE TABLE IF NOT EXISTS catalog (
        id SERIAL PRIMARY KEY,
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        origin_root_id INTEGER REFERENCES catalog(id) ON DELETE SET NULL,
        name VARCHAR(255) NOT NULL UNIQUE, -- Product name
        brand VARCHAR(255), -- Brand name
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

        favorite BOOLEAN DEFAULT FALSE, -- To mark user favorites for easier access
        is_private BOOLEAN NOT NULL DEFAULT FALSE -- True: only creator can view it
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
        favorite BOOLEAN DEFAULT FALSE, -- Same as in catalog
        is_private BOOLEAN NOT NULL DEFAULT FALSE, -- True: only creator can view it

        UNIQUE (created_by, name)
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
        favorite BOOLEAN DEFAULT FALSE,
        is_private BOOLEAN NOT NULL DEFAULT FALSE -- True: only owner can view it
    );
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

    intake_event = """
    CREATE TABLE IF NOT EXISTS intake_event (
        id SERIAL PRIMARY KEY,
        users_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        
        state VARCHAR(20) NOT NULL CHECK (
            state IN ('planned', 'consumed')
        ), -- Determines whether this meal is in the cart (planned) or has been definitively consumed
        meal_type VARCHAR(50) CHECK (
            meal_type IN (
                'breakfast', 'brunch', 'lunch',
                'afternoon_snack', 'dinner', 'snack', 'rescue'
            )
        ), -- Should be modifiable while still in the cart, in case it was added late or needs correction
        name VARCHAR(255), -- Name for this meal event, useful when there are multiple carts and the user wants to label each one. Default should be auto-generated based on time of day (e.g. "Lunch 1", "Snack 1"), with configurable time intervals in settings. Must be editable afterwards. When adding a new product, if there is more than one intake_event, the user should be asked where to add it.
        
        meal_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Defaults to the moment it is added, but should be easy to change within the cart
        eating_out BOOLEAN DEFAULT FALSE, -- Whether the user is eating out. Should default to False if most items come from catalog, recipe, or fridge; True if most or all come from manual_intake
        insulin_dose BOOLEAN DEFAULT TRUE, -- Should default to True if total carbs exceed 10g, and False otherwise, but must be adjustable in the cart
        
        total_amount REAL, -- Automatically calculated as the sum of plate_amount from all related portion_detail rows
        ingested_amount REAL, -- After eating, before confirming the meal, the user enters the total amount ingested (in grams or approximate percentage). The leftovers are then automatically calculated (total_amount - ingested_amount), and the proportional amount of each ingredient is automatically saved to the fridge for later reuse.
        
        amount_confidence REAL CHECK (amount_confidence >= 0 AND amount_confidence <= 1), -- Weighted average based on each food's amount and whether it was strictly weighed: ((amount1 * strictly_weighed1 + amount2 * strictly_weighed2) / total_amount)
        quality_confidence REAL CHECK (quality_confidence >= 0 AND quality_confidence <= 1), -- Value between 0 and 1 indicating confidence in the nutritional information. Same calculation as amount_confidence but using each ingredient's macros_quality
        
        carbs_uncertainty REAL CHECK (carbs_uncertainty >= 0 AND carbs_uncertainty <= 1), -- Automatically calculated as a weighted average of each ingredient's carbs value (which may be a value or None) by its total amount, to indicate how reliable the total macro count is (since None is not the same as 0)
        sugars_uncertainty REAL CHECK (sugars_uncertainty >= 0 AND sugars_uncertainty <= 1), -- Same as carbs_uncertainty but for sugars
        fats_uncertainty REAL CHECK (fats_uncertainty >= 0 AND fats_uncertainty <= 1), -- Same as carbs_uncertainty but for fats
        saturated_uncertainty REAL CHECK (saturated_uncertainty >= 0 AND saturated_uncertainty <= 1), -- Same as carbs_uncertainty but for saturated fats
        proteins_uncertainty REAL CHECK (proteins_uncertainty >= 0 AND proteins_uncertainty <= 1), -- Same as carbs_uncertainty but for proteins
        fiber_uncertainty REAL CHECK (fiber_uncertainty >= 0 AND fiber_uncertainty <= 1), -- Same as carbs_uncertainty but for fiber
        
        notes TEXT
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
        
        amount_g REAL NOT NULL, -- This is the cooked amount of a food item. For example, the user may cook 400g of quinoa but only plate 100g, saving the rest. This amount is then compared to plate_amount, and if greater, the difference is automatically saved to the fridge with the food's id, for easy reuse later.
        cooking VARCHAR(50), -- Cooking method, used to evaluate its effect on blood sugar levels (options: steam, boiled-al-dente, boiled-soft, fried, raw, oven, airfryer, toaster, griddle). Default: griddle
        conservation VARCHAR(50), -- Storage method: freezer, fridge, freshly-made, pre-cooked
        final_state VARCHAR(50), -- Final state among: 'solid', 'mashed/creamy', 'liquid', 'gel' — in case the state changed from the initial one
        strictly_weighed BOOLEAN, -- Whether or not the food was weighed before consumption
        macros_quality BOOLEAN, -- Whether the macros were estimated or read from the product label
        
        plate_amount REAL, -- The amount actually plated. Defaults to the same value as amount_g
        is_cooked_weight BOOLEAN DEFAULT FALSE, -- If the food was weighed already cooked, the cooking_factor is used to back-calculate the raw weight and obtain accurate macros
        offset_minutes INTEGER, -- Only for intake_event. Adjusted during the planning phase (not when added to the cart), and defaults to the difference in minutes between the intake_event timestamp and the moment this food is added to the cart

        CHECK (offset_minutes IS NULL OR intake_event_id IS NOT NULL)
    );
    """
