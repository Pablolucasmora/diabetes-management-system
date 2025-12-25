class TABLES:
    # SUBTIPOS = """
    #     CREATE TABLE IF NOT EXISTS catalogo_subtipos (
    #         id_subtipo INTEGER PRIMARY KEY AUTOINCREMENT,
    #         nombre TEXT UNIQUE NOT NULL,
    #         categoria_padre TEXT NOT NULL
    #     );
    # """

    PRODUCTOS = """
        CREATE TABLE IF NOT EXISTS catalogo_productos (
            id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            marca TEXT,
            categoria TEXT,
            nutriscore TEXT,
            nova INTEGER,
            subtipo TEXT,
            porcion_default_g REAL,
            graduacion_pct REAL DEFAULT 0,
            hidratos_g REAL DEFAULT 0,
            azucares_g REAL DEFAULT 0,
            grasas_g REAL DEFAULT 0,
            proteinas_g REAL DEFAULT 0,
            fibra_g REAL DEFAULT 0,
            cafeina_mg REAL DEFAULT 0,
            es_gas INTEGER DEFAULT 0,
            notas TEXT
            --FOREIGN KEY (id_subtipo) REFERENCES catalogo_subtipos(id_subtipo)
        );
    """

    COMIDA = """
        CREATE TABLE IF NOT EXISTS comida (
            id_comida INTEGER PRIMARY KEY AUTOINCREMENT,
            inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tipo_comida TEXT CHECK(tipo_comida IN ('Desayuno', 'Almuerzo', 'Comida', 'Merienda', 'Cena', 'Snack', 'Rescate')),
            es_restaurante INTEGER DEFAULT 0,
            tiempo_espera INTEGER DEFAULT 0,
            es_pesado_estricto INTEGER DEFAULT 1,
            notas TEXT
        );
    """

    PARTES_COMIDA = """
        CREATE TABLE IF NOT EXISTS partes_comida (
            id_detalle INTEGER PRIMARY KEY AUTOINCREMENT,
            id_comida INTEGER NOT NULL,
            id_producto INTEGER,
            nombre_real TEXT,
            offset_minutos INTEGER DEFAULT 0,
            cantidad REAL NOT NULL,
            hidratos_totales REAL,
            azucar_total REAL,
            grasas_totales REAL,
            proteinas_totales REAL,
            fibra_total REAL,
            es_pesado_detalle INTEGER, 
            FOREIGN KEY (id_comida) REFERENCES comida(id_comida) ON DELETE CASCADE,
            FOREIGN KEY (id_producto) REFERENCES catalogo_productos(id_producto)
        );
    """

    AUDITORIA = """
        CREATE TABLE IF NOT EXISTS historial_cambios (
            id_log INTEGER PRIMARY KEY AUTOINCREMENT,
            tabla_afectada TEXT NOT NULL,
            id_referencia INTEGER,
            accion TEXT NOT NULL,
            valor_anterior TEXT,
            valor_nuevo TEXT,
            fecha_accion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """