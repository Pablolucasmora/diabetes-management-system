from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import json
from database.connection import create_connection


def registrar_log(cursor, tabla, id_ref, accion, anterior=None, nuevo=None):
    """
    Función centralizada para auditar cambios.
    """
    cursor.execute("""
        INSERT INTO historial_cambios (tabla_afectada, id_referencia, accion, valor_anterior, valor_nuevo)
        VALUES (?, ?, ?, ?, ?)
    """, (tabla, id_ref, accion, 
          json.dumps(anterior) if anterior else None, 
          json.dumps(nuevo) if nuevo else None))


@dataclass
class ProductoModel:
    id_producto: Optional[int] = None
    nombre: str = ""
    marca: str = ""
    categoria: str = "" # Si es Alimeno, Bebida, Suplemento...
    nutriscore: str = "" # A, B, C, D, E
    nova: int = 0
    subtipo: str = "" # Ej: Refresco, Tarta, Cookies...
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
    id_comida: Optional[int] = None  # FK a la tabla Comida
    
    # Si id_producto es None, significa que es una "entrada manual"
    id_producto: Optional[int] = None 
    
    # Nombre_real permite guardar el nombre específico de esa vez 
    # (ej: "Pizza de Juan" aunque el producto sea "Base de Pizza")
    nombre_real: str = "" 
    
    cantidad: float = 0.0
    offset: int = 0  # Minutos de diferencia respecto al inicio de la comida
    
    # Estos campos almacenan el resultado final (ej: 45.5g de hidratos)
    # Tanto si vienen del catálogo como si los metes a mano
    hidratos_totales: float = 0.0
    azucar_total: float = 0.0
    grasas_totales: float = 0.0
    proteinas_totales: float = 0.0
    fibra_total: float = 0.0

    es_pesado_detalle: Optional[bool] = None  # None para "usar el de la comida"

@dataclass
class ComidaModel:
    id_comida: Optional[int] = None
    inicio: datetime = field(default_factory=datetime.now)
    tipo_comida: str = "Comida"  # Desayuno, Almuerzo, Comida, Merienda, Cena, Snack, Rescate
    es_restaurante: bool = False
    tiempo_espera: int = 0  # Minutos de espera antes de comer
    es_pesado_estricto: bool = True  # Si es False, permite ajustes manuales en detalles
    notas: str = ""
    
    partes: List[ParteComidaModel] = field(default_factory=list)




class CatalogoQueries:
    @staticmethod
    def insertar_producto(producto: ProductoModel) -> int:
        """
        Recibe un objeto ProductoModel y lo guarda en la base de datos.
        Devuelve el id_producto generado por SQLite.
        """
        conn = create_connection()
        if not conn:
            return None
        
        sql = """
            INSERT INTO catalogo_productos (
                nombre, marca, categoria, nutriscore, nova, subtipo, 
                graduacion_pct, hidratos_g, azucares_g, grasas_g, 
                proteinas_g, fibra_g, cafeina_mg, es_gas, notas
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        # Mapeamos los atributos del objeto a la consulta
        valores = (
            producto.nombre, producto.marca, producto.categoria, 
            producto.nutriscore, producto.nova, producto.subtipo,
            producto.graduacion_pct, producto.hidratos_g, producto.azucares_g, 
            producto.grasas_g, producto.proteinas_g, producto.fibra_g, 
            producto.cafeina_mg, int(producto.es_gas), producto.notas
        )
        
        try:
            cursor = conn.cursor()
            cursor.execute(sql, valores)
            producto_id = cursor.lastrowid # Recuperamos el ID autogenerado

            # 2. Preparamos los datos para el log (convertimos el modelo a dict)
            datos_nuevos = producto.__dict__.copy()
            
            # 3. Registramos la acción en la tabla de auditoría
            registrar_log(
                cursor=cursor,
                tabla='catalogo_productos',
                id_ref=producto_id,
                accion='INSERT',
                nuevo=datos_nuevos
            )
            conn.commit()            
            return producto_id
        except Exception as e:
            print(f"Error al insertar producto: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    @staticmethod
    def obtener_todos_nombres_id():
        """Trae el catálogo completo (id, nombre, marca) para el buscador"""
        conn = create_connection()
        if not conn: return []
        try:
            cursor = conn.cursor()
            # Traemos todos los productos ordenados alfabéticamente
            cursor.execute("SELECT id_producto, nombre, marca FROM catalogo_productos ORDER BY nombre ASC")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def obtener_producto_por_id(id_prod: int) -> ProductoModel:
        """ Carga TODOS los datos de UN solo producto cuando ya sabemos cuál es """
        conn = create_connection()
        if not conn: return None
        
        sql = "SELECT * FROM catalogo_productos WHERE id_producto = ?"
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (id_prod,))
            row = cursor.fetchone()
            if row:
                return ProductoModel(**dict(row))
        finally:
            conn.close()