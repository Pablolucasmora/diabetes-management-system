class DBSchema:
    
    users = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255),
        mail VARCHAR(255) UNIQUE NOT NULL,
        password TEXT NOT NULL,
        registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        category VARCHAR(255) CHECK (category IN ('admin', 'common'))
    );
    """

    catalog = """
    CREATE TABLE IF NOT EXISTS catalog (
        id SERIAL PRIMARY KEY,
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        name VARCHAR(255) NOT NULL UNIQUE,
        brand VARCHAR(255),
        category VARCHAR(100) NOT NULL CHECK (
            category IN (
                'meat', 'fish', 'dairy', 'eggs', 'processed_meat',
                'legumes', 'tubers', 'nuts', 'vegetables', 'fruits',
                'cereals', 'oils_and_fats', 'sweets', 'beverages',
                'sauces', 'condiments', 'supplements'
            )
        ),
        subtype VARCHAR(100) NOT NULL,
        initial_state VARCHAR(50) CHECK (
            initial_state IN ('solid', 'mashed/creamy', 'liquid', 'gel')
        ), 
        
        nutriscore VARCHAR(1) CHECK (nutriscore IN ('A', 'B', 'C', 'D', 'E')),
        NOVA INTEGER CHECK (NOVA BETWEEN 1 AND 4),
        yuka INTEGER CHECK (yuka BETWEEN 0 AND 100),
        
        default_portion INTEGER DEFAULT 100,
        
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
        cooking_factor REAL DEFAULT 1.0,

        favorite BOOLEAN DEFAULT FALSE
    );
    """

    manual_intake = """
    CREATE TABLE IF NOT EXISTS manual_intake (
        id SERIAL PRIMARY KEY,
        created_by INTEGER REFERENCES users(id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        subtype VARCHAR(100) NOT NULL,
        origin VARCHAR(255),
        
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
        ),
        ig_confidence INTEGER CHECK (ig_confidence BETWEEN 1 AND 5),
        favorite BOOLEAN DEFAULT FALSE,

        UNIQUE (created_by, name)
    );
    """

    fridge = """
    CREATE TABLE IF NOT EXISTS fridge (
        id SERIAL PRIMARY KEY,
        users_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        tupper_name VARCHAR(255),
        entry_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
        is_compound BOOLEAN DEFAULT FALSE,
        total_tupper_weight REAL
    );
    """

    tags = """
    CREATE TABLE IF NOT EXISTS tags (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) UNIQUE NOT NULL,
        description TEXT
    );
    """

    recipe = """
    CREATE TABLE IF NOT EXISTS recipe (
        id SERIAL PRIMARY KEY, 
        users_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        meal_type VARCHAR(50) CHECK (
            meal_type IN (
                'breakfast', 'brunch', 'lunch',
                'afternoon_snack', 'dinner', 'snack', 'rescue'
            )
        ),
        name VARCHAR(255) NOT NULL,
        notes TEXT,
        favorite BOOLEAN DEFAULT FALSE
    );
    """

    linked_tags = """
    CREATE TABLE IF NOT EXISTS linked_tags (
        id SERIAL PRIMARY KEY,
        tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
        
        catalog_id INTEGER REFERENCES catalog(id) ON DELETE CASCADE,
        recipe_id INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
        manual_intake_id INTEGER REFERENCES manual_intake(id) ON DELETE CASCADE,
        
        CHECK (num_nonnulls(catalog_id, recipe_id, manual_intake_id) = 1)
    );
    """

    intake_event = """
    CREATE TABLE IF NOT EXISTS intake_event (
        id SERIAL PRIMARY KEY,
        users_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        
        state VARCHAR(20) NOT NULL CHECK (
            state IN ('planned', 'consumed')
        ),
        meal_type VARCHAR(50) CHECK (
            meal_type IN (
                'breakfast', 'brunch', 'lunch',
                'afternoon_snack', 'dinner', 'snack', 'rescue'
            )
        ),
        name VARCHAR(255),
        
        meal_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        eating_out BOOLEAN DEFAULT FALSE,
        insulin_dose BOOLEAN DEFAULT TRUE,
        
        total_amount REAL,
        ingested_amount REAL,
        
        amount_confidence REAL CHECK (amount_confidence >= 0 AND amount_confidence <= 1),
        quality_confidence REAL CHECK (quality_confidence >= 0 AND quality_confidence <= 1),
        
        carbs_uncertainty REAL CHECK (carbs_uncertainty >= 0 AND carbs_uncertainty <= 1),
        sugars_uncertainty REAL CHECK (sugars_uncertainty >= 0 AND sugars_uncertainty <= 1),
        fats_uncertainty REAL CHECK (fats_uncertainty >= 0 AND fats_uncertainty <= 1),
        saturated_uncertainty REAL CHECK (saturated_uncertainty >= 0 AND saturated_uncertainty <= 1),
        proteins_uncertainty REAL CHECK (proteins_uncertainty >= 0 AND proteins_uncertainty <= 1),
        fiber_uncertainty REAL CHECK (fiber_uncertainty >= 0 AND fiber_uncertainty <= 1),
        
        notes TEXT
    );
    """

    portion_detail = """
    CREATE TABLE IF NOT EXISTS portion_detail (
        id SERIAL PRIMARY KEY,
        
        catalog_id INTEGER REFERENCES catalog(id) ON DELETE RESTRICT,
        manual_intake_id INTEGER REFERENCES manual_intake(id) ON DELETE RESTRICT,
        CHECK (num_nonnulls(catalog_id, manual_intake_id) = 1),
        
        intake_event_id INTEGER REFERENCES intake_event(id) ON DELETE CASCADE,
        fridge_id INTEGER REFERENCES fridge(id) ON DELETE CASCADE,
        recipe_id INTEGER REFERENCES recipe(id) ON DELETE CASCADE,
        CHECK (num_nonnulls(intake_event_id, fridge_id, recipe_id) = 1),
        
        amount_g REAL NOT NULL,
        cooking VARCHAR(50),
        conservation VARCHAR(50),
        final_state VARCHAR(50),
        strictly_weighed BOOLEAN,
        macros_quality BOOLEAN,
        
        plate_amount REAL,
        is_cooked_weight BOOLEAN DEFAULT FALSE,
        offset_minutes INTEGER,

        CHECK (offset_minutes IS NULL OR intake_event_id IS NOT NULL)
    );
    """