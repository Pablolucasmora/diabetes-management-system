# schema.py

class DBSchema:
    
    usuario = """
    CREATE TABLE IF NOT EXISTS usuario (
        id SERIAL PRIMARY KEY,
        nombre VARCHAR(255),
        correo VARCHAR(255) UNIQUE NOT NULL,
        clave TEXT NOT NULL,
        fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    catalogo = """
    CREATE TABLE IF NOT EXISTS catalogo (
        id SERIAL PRIMARY KEY,
        created_by INTEGER REFERENCES usuario(id) ON DELETE SET NULL,
        nombre VARCHAR(255) NOT NULL UNIQUE,
        marca VARCHAR(255),
        categoria VARCHAR(100) NOT NULL CHECK (categoria IN ('carne', 'pescado', 'lácteos', 'huevos', 'charcutería', 'legumbres', 'tubérculos', 'frutos secos', 'verduras', 'frutas', 'cereales', 'aceites y grasas', 'dulces', 'bebidas', 'salsas', 'condimentos', 'suplementos')),
        subtipo VARCHAR(100) NOT NULL,
        estado_inicial VARCHAR(50) CHECK (estado_inicial IN ('solido', 'triturado/cremoso', 'liquido', 'gel')),
        
        nutriscore VARCHAR(1) CHECK (nutriscore IN ('A', 'B', 'C', 'D', 'E')),
        NOVA INTEGER CHECK (NOVA BETWEEN 1 AND 4),
        yuka INTEGER CHECK (yuka BETWEEN 0 AND 100),
        
        porcion_default INTEGER DEFAULT 100,
        
        calorias_100g REAL,
        hidratos_100g REAL,
        azucares_100g REAL,
        grasas_100g REAL,
        saturadas_100g REAL,
        proteinas_100g REAL,
        fibra_100g REAL,
        
        cafeina REAL,
        alcohol REAL,
        
        cod_barras BIGINT,
        factor_cocinado REAL DEFAULT 1.0
    );
    """

    ingesta_manual = """
    CREATE TABLE IF NOT EXISTS ingesta_manual (
        id SERIAL PRIMARY KEY,
        created_by INTEGER REFERENCES usuario(id) ON DELETE CASCADE,
        nombre VARCHAR(255) NOT NULL,
        descripcion TEXT,
        subtipo VARCHAR(100) NOT NULL,
        procedencia VARCHAR(255),
        
        cantidad_g REAL NOT NULL,
        calorias_100g REAL,
        hidratos_100g REAL,
        azucares_100g REAL,
        grasas_100g REAL,
        saturadas_100g REAL,
        proteinas_100g REAL,
        fibra_100g REAL,
        
        cafeina REAL,
        alcohol REAL,
        
        indice_glucemico VARCHAR(20) CHECK (indice_glucemico IN ('alto', 'medio', 'bajo')),
        confianza_ig INTEGER CHECK (confianza_ig BETWEEN 1 AND 5),
        
        UNIQUE (created_by, nombre)
    );
    """

    nevera = """
    CREATE TABLE IF NOT EXISTS nevera (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES usuario(id) ON DELETE CASCADE,
        nombre_tupper VARCHAR(255),
        fecha_entrada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        es_compuesto BOOLEAN DEFAULT FALSE,
        peso_total_tupper REAL
    );
    """

    etiquetas = """
    CREATE TABLE IF NOT EXISTS etiquetas (
        id SERIAL PRIMARY KEY,
        nombre VARCHAR(100) UNIQUE NOT NULL,
        descripcion TEXT
    );
    """

    recetas = """
    CREATE TABLE IF NOT EXISTS recetas (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES usuario(id) ON DELETE CASCADE,
        tipo_comida VARCHAR(50) CHECK (tipo_comida IN ('desayuno', 'almuerzo', 'comida', 'merienda', 'cena', 'snack', 'rescate')),
        nombre VARCHAR(255) NOT NULL,
        notas TEXT
    );
    """

    etiquetas_vinculadas = """
    CREATE TABLE IF NOT EXISTS etiquetas_vinculadas (
        id SERIAL PRIMARY KEY,
        etiqueta_id INTEGER REFERENCES etiquetas(id) ON DELETE CASCADE,
        
        catalogo_id INTEGER REFERENCES catalogo(id) ON DELETE CASCADE,
        receta_id INTEGER REFERENCES recetas(id) ON DELETE CASCADE,
        ingesta_manual_id INTEGER REFERENCES ingesta_manual(id) ON DELETE CASCADE,
        
        -- Función de Postgres para contar cuántos de estos campos no son nulos.
        -- Garantiza que la etiqueta se asigne a una y solo una entidad.
        CHECK (num_nonnulls(catalogo_id, receta_id, ingesta_manual_id) = 1)
    );
    """

    evento_ingesta = """
    CREATE TABLE IF NOT EXISTS evento_ingesta (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES usuario(id) ON DELETE CASCADE,
        
        estado VARCHAR(20) NOT NULL CHECK (estado IN ('planificado', 'consumido')),
        tipo_comida VARCHAR(50) CHECK (tipo_comida IN ('desayuno', 'almuerzo', 'comida', 'merienda', 'cena', 'snack', 'rescate')),
        nombre VARCHAR(255),
        
        hora_comida TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        comida_fuera BOOLEAN DEFAULT FALSE,
        dosis_insulina BOOLEAN DEFAULT TRUE,
        
        cantidad_total REAL,
        cantidad_ingerida REAL,
        
        confianza_cantidad REAL CHECK (confianza_cantidad >= 0 AND confianza_cantidad <= 1),
        confianza_calidad REAL,
        
        incertidumbre_hidratos REAL CHECK (incertidumbre_hidratos >= 0 AND incertidumbre_hidratos <= 1),
        incertidumbre_azucares REAL CHECK (incertidumbre_azucares >= 0 AND incertidumbre_azucares <= 1),
        incertidumbre_grasas REAL CHECK (incertidumbre_grasas >= 0 AND incertidumbre_grasas <= 1),
        incertidumbre_saturadas REAL CHECK (incertidumbre_saturadas >= 0 AND incertidumbre_saturadas <= 1),
        incertidumbre_proteinas REAL CHECK (incertidumbre_proteinas >= 0 AND incertidumbre_proteinas <= 1),
        incertidumbre_fibra REAL CHECK (incertidumbre_fibra >= 0 AND incertidumbre_fibra <= 1),
        
        notas TEXT
    );
    """

    porcion_detalle = """
    CREATE TABLE IF NOT EXISTS porcion_detalle (
        id SERIAL PRIMARY KEY,
        
        -- ARCO 1: Origen
        catalogo_id INTEGER REFERENCES catalogo(id) ON DELETE RESTRICT,
        ingesta_manual_id INTEGER REFERENCES ingesta_manual(id) ON DELETE RESTRICT,
        CHECK (num_nonnulls(catalogo_id, ingesta_manual_id) = 1),
        
        -- ARCO 2: Destino
        evento_ingesta_id INTEGER REFERENCES evento_ingesta(id) ON DELETE CASCADE,
        nevera_id INTEGER REFERENCES nevera(id) ON DELETE CASCADE,
        receta_id INTEGER REFERENCES recetas(id) ON DELETE CASCADE,
        CHECK (num_nonnulls(evento_ingesta_id, nevera_id, receta_id) = 1),
        
        cantidad_g REAL NOT NULL,
        cocinado VARCHAR(50),
        conservacion VARCHAR(50),
        estado_final VARCHAR(50),
        pesado_estricto BOOLEAN,
        calidad_macros BOOLEAN,
        
        cantidad_plato REAL,
        es_peso_cocinado BOOLEAN DEFAULT FALSE,
        offset_minutos INTEGER

        CHECK (offset_minutos IS NULL OR evento_ingesta_id IS NOT NULL)
    );
    """