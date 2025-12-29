from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import json
from .connection import get_db_manager

# Instancia global del manager para este archivo
db = get_db_manager()

def registrar_log(cursor, tabla, id_ref, accion, anterior=None, nuevo=None):
    """Auditoría centralizada: guarda cambios en formato JSON."""
    cursor.execute("""
        INSERT INTO historial_cambios (tabla_afectada, id_referencia, accion, valor_anterior, valor_nuevo)
        VALUES (?, ?, ?, ?, ?)
    """, (tabla, id_ref, accion, 
          json.dumps(anterior) if anterior else None, 
          json.dumps(nuevo) if nuevo else None))

# --- MODELOS DE DATOS (DATACLASSES) ---
@dataclass
class ProductoModel:
    id_producto: Optional[int] = None
    nombre: str = ""
    marca: Optional[str] = None          
    categoria: str = ""
    nutriscore: str = ""
    nova: int = 0
    subtipo: str = ""
    porcion_default_g: Optional[int] = None 
    graduacion_pct: float = 0.0
    hidratos_g: float = 0.0
    azucares_g: float = 0.0
    grasas_g: float = 0.0
    proteinas_g: float = 0.0
    fibra_g: float = 0.0
    cafeina_mg: float = 0.0
    es_gas: bool = False
    notas: str = ""

@dataclass
class ParteComidaModel:
    id_detalle: Optional[int] = None
    id_comida: Optional[int] = None
    id_producto: Optional[int] = None 
    nombre_real: str = "" 
    cantidad: float = 0.0
    offset: Optional[int] = None  
    hidratos_totales: float = 0.0
    azucar_total: float = 0.0
    grasas_totales: float = 0.0
    proteinas_totales: float = 0.0
    fibra_total: float = 0.0
    es_pesado_detalle: Optional[bool] = None

@dataclass
class ComidaModel:
    id_comida: Optional[int] = None
    inicio: datetime = field(default_factory=datetime.now)
    tipo_comida: str = "Comida"
    es_restaurante: bool = False
    tiempo_espera: int = 0
    es_pesado_estricto: bool = True
    notas: str = ""
    partes: List[ParteComidaModel] = field(default_factory=list)

@dataclass
class ItemCarrito:
    # Un dataclass simple para manejar los datos en la UI
    id_item: int
    nombre: str
    cantidad: float
    hc: float
    gr: float
    pr: float
    fb: float
    offset: int
    es_pesado: bool

# --- CONSULTAS AL CATÁLOGO ---

class CatalogoQueries:
    @staticmethod
    def insertar_producto(producto: ProductoModel) -> Optional[int]:
        """Inserta un producto con auditoría en una transacción manual para asegurar lastrowid."""
        conn = db._get_connection()
        if not conn: return None
        
        sql = """
            INSERT INTO catalogo_productos (
                nombre, marca, categoria, nutriscore, nova, subtipo, 
                graduacion_pct, porcion_default_g, hidratos_g, azucares_g, grasas_g, 
                proteinas_g, fibra_g, cafeina_mg, es_gas, notas
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        valores = (
            producto.nombre, producto.marca, producto.categoria, 
            producto.nutriscore, producto.nova, producto.subtipo,
            producto.graduacion_pct, producto.porcion_default_g, producto.hidratos_g, producto.azucares_g, 
            producto.grasas_g, producto.proteinas_g, producto.fibra_g, 
            producto.cafeina_mg, int(producto.es_gas), producto.notas
        )
        
        try:
            cursor = conn.cursor()
            cursor.execute(sql, valores)
            producto_id = cursor.lastrowid 

            registrar_log(cursor, 'catalogo_productos', producto_id, 'INSERT', nuevo=producto.__dict__)
            conn.commit()            
            return producto_id
        except Exception as e:
            conn.rollback()
            print(f"❌ Error al insertar producto: {e}")
            return None
        finally:
            conn.close()

    @staticmethod
    def obtener_todos_nombres_id():
        """Trae el catálogo resumido para buscadores (evita 'closed database' error)."""
        query = "SELECT id_producto, nombre, marca FROM catalogo_productos ORDER BY nombre ASC"
        filas = db.execute_query(query) # Devuelve lista de filas, no el cursor
        return [dict(row) for row in filas] if filas else []

    @staticmethod
    def obtener_producto_por_id(id_prod: int) -> Optional[ProductoModel]:
        """Obtiene un producto completo mapeado a su dataclass."""
        query = "SELECT * FROM catalogo_productos WHERE id_producto = ?"
        filas = db.execute_query(query, (id_prod,))
        if filas:
            datos = dict(filas[0])
            # SQLite devuelve 0/1 para booleanos, lo convertimos a bool de Python
            datos['es_gas'] = bool(datos['es_gas'])
            return ProductoModel(**datos)
        return None

class CarritoQueries:
    @staticmethod
    def agregar_item(datos: dict):
        """Recibe el diccionario que antes metías en session_state"""
        conn = db._get_connection()
        if not conn: return None
        
        sql = """
            INSERT INTO carrito_temporal (
                id_producto, nombre_display, cantidad, 
                hc, gr, pr, fb, az,
                offset, es_pesado_estricto, es_manual, fecha_agregado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        # Asegúrate de extraer los valores correctamente del dict
        valores = (
            datos.get('id_producto'), datos.get('nombre'), datos.get('cantidad'),
            datos.get('hc'), datos.get('gr'), datos.get('pr'), datos.get('fb'), datos.get('az', 0),
            datos.get('offset'), int(datos.get('es_pesado_estricto', 1)), int(datos.get('es_manual', 0))
        )
        
        try:
            cursor = conn.cursor()
            cursor.execute(sql, valores)
            conn.commit()
            return True
        except Exception as e:
            print(f"Error al añadir al carrito: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def obtener_carrito():
        query = "SELECT * FROM carrito_temporal ORDER BY fecha_agregado ASC"
        rows = db.execute_query(query)
        # Convertimos rows a lista de dicts o dataclasses
        return [dict(row) for row in rows] if rows else []

    @staticmethod
    def eliminar_item(id_item):
        db.execute_query("DELETE FROM carrito_temporal WHERE id_item = ?", (id_item,), commit=True)

    @staticmethod
    def vaciar_carrito():
        db.execute_query("DELETE FROM carrito_temporal", commit=True)