import sqlite3
from sqlite3 import Error
from .schema_DB import TABLES

class DatabaseManager:
    def __init__(self, db_path="diabetes_DB.db"):
        self.db_path = db_path

    def _get_connection(self):
        """Crea una conexión a la base de datos."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            # Habilitar claves foráneas en SQLite (importante para ON DELETE CASCADE)
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn
        except Error as e:
            print(f"Error conectando a la base de datos: {e}")
            return None

    def execute_query(self, query, params=(), commit=False, multiple=False):
        """Ejecuta una consulta SQL y devuelve los RESULTADOS, no el cursor."""
        conn = self._get_connection()
        if not conn:
            return None
        
        try:
            cursor = conn.cursor()
            if multiple:
                cursor.executemany(query, params)
            else:
                cursor.execute(query, params)
            
            # SI ES UNA CONSULTA DE LECTURA (SELECT)
            # Extraemos los datos ANTES de que se cierre la conexión
            result = None
            if not commit:
                result = cursor.fetchall()
            
            if commit:
                conn.commit()
                result = cursor.lastrowid # Devolvemos el ID si es un insert
            
            return result

        except Error as e:
            print(f"Error ejecutando query: {e}")
            return None
        finally:
            conn.close() # Ahora sí puede cerrarse tranquila

    def init_db(self, subtipos_default=None):
        """Inicializa todo el esquema de tablas."""
        queries = [
            # TABLES.SUBTIPOS,
            TABLES.PRODUCTOS,
            TABLES.COMIDA,
            TABLES.PARTES_COMIDA,
            TABLES.AUDITORIA,
            TABLES.CARRITO_TEMP
        ]

        conn = self._get_connection()
        if conn:
            try:
                cursor = conn.cursor()
                for q in queries:
                    cursor.execute(q)
                conn.commit()
                print("✅ Estructura de tablas verificada/creada.")
                
                # Opcional: Sembrar datos iniciales si la tabla está vacía
                if subtipos_default:
                    self.seed_subtypes(subtipos_default)
                    
            except Error as e:
                print(f"❌ Error inicializando tablas: {e}")
            finally:
                conn.close()

    def seed_subtypes(self, lista):
        """Inserta los 20 subtipos si la tabla está vacía."""
        res = self.execute_query("SELECT COUNT(*) FROM catalogo_subtipos")
        if res and res.fetchone()[0] == 0:
            query = "INSERT INTO catalogo_subtipos (nombre, categoria_padre) VALUES (?, ?)"
            self.execute_query(query, lista, commit=True, multiple=True)
            print(f"🌱 {len(lista)} subtipos insertados correctamente.")