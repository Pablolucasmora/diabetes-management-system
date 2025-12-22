import sqlite3
import os
from sqlite3 import Error

# Definimos la ruta de la base de datos relativa a este archivo
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'diabetes_tfg.db')

def create_connection():
    """ Crea una conexión a la base de datos SQLite y activa las claves foráneas. """
    conn = None
    try:
        # Conectamos (se crea el archivo si no existe)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        
        # IMPORTANTE: Activar el soporte de claves foráneas en cada conexión
        conn.execute("PRAGMA foreign_keys = ON;")
        
        # Configurar para que las filas se devuelvan como diccionarios (opcional, muy útil)
        conn.row_factory = sqlite3.Row
        
        return conn
    except Error as e:
        print(f"Error al conectar con SQLite: {e}")
        return None

def init_db():
    """ Crea las tablas siguiendo el esquema definido si no existen. """
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # 1. Tabla de Catálogo
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS catalogo_productos (
                id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                marca TEXT,
                categoria TEXT,
                nutriscore TEXT,
                nova INTEGER,
                subtipo TEXT,
                graduacion_pct REAL DEFAULT 0,
                hidratos_g REAL DEFAULT 0,
                azucares_g REAL DEFAULT 0,
                grasas_g REAL DEFAULT 0,
                proteinas_g REAL DEFAULT 0,
                fibra_g REAL DEFAULT 0,
                cafeina_mg REAL DEFAULT 0,
                es_gas INTEGER DEFAULT 0,
                notas TEXT
            );
            """)

            # 2. Tabla de Comidas
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS comida (
                id_comida INTEGER PRIMARY KEY AUTOINCREMENT,
                inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tipo_comida TEXT CHECK(tipo_comida IN ('Desayuno', 'Almuerzo', 'Comida', 'Merienda', 'Cena', 'Snack', 'Rescate')),
                es_restaurante INTEGER DEFAULT 0,
                tiempo_espera INTEGER DEFAULT 0,
                es_pesado_estricto INTEGER DEFAULT 1,
                notas TEXT
            );
            """)

            # 3. Tabla de Detalles (Partes de la comida)
            cursor.execute("""
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
                es_pesado_detalle INTEGER, -- 1 para sí, 0 para no, NULL para "usar el de la comida",
                FOREIGN KEY (id_comida) REFERENCES comida(id_comida) ON DELETE CASCADE,
                FOREIGN KEY (id_producto) REFERENCES catalogo_productos(id_producto)
            );
            """)

            conn.commit()
            print("Base de datos inicializada correctamente.")
        except Error as e:
            print(f"Error al crear las tablas: {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    # Si ejecutas este archivo directamente, se crea la base de datos
    init_db()