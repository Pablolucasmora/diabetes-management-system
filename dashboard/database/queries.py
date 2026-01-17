from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
import json
from .connection import get_db_manager
import sqlite3

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
    grasas_sat_g: float = 0.0
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
class CarritoTemp:
    # Un dataclass simple para manejar los datos en la UI
    id_item: int
    id_producto: Optional[int]
    nombre_display: str
    cantidad: float
    hc: float
    gr: float
    pr: float
    fb: float
    sat: float
    az: float
    offset: int
    es_pesado_estricto: bool
    es_manual: bool
    grupo_nombre: str

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
                graduacion_pct, porcion_default_g, hidratos_g, azucares_g, grasas_g, grasas_sat_g,
                proteinas_g, fibra_g, cafeina_mg, es_gas, notas
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        valores = (
            producto.nombre, producto.marca, producto.categoria, 
            producto.nutriscore, producto.nova, producto.subtipo,
            producto.graduacion_pct, producto.porcion_default_g, producto.hidratos_g, producto.azucares_g, 
            producto.grasas_g, producto.grasas_sat_g, producto.proteinas_g, producto.fibra_g, 
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
                hc, gr, pr, fb, az, sat,
                offset, es_pesado_estricto, es_manual, grupo_nombre
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        # Asegúrate de extraer los valores correctamente del dict
        valores = (
            datos.get('id_producto'), datos.get('nombre_display'), datos.get('cantidad', None),
            datos.get('hc'), datos.get('gr'), datos.get('pr'), datos.get('fb'), datos.get('az', 0), datos.get('sat', 0),
            datos.get('offset'), int(datos.get('es_pesado_estricto', 1)), int(datos.get('es_manual', 0)), 
            datos.get('grupo_nombre', 'Comida Actual')
        )
        
        try:
            cursor = conn.cursor()
            cursor.execute(sql, valores)
            id_generado = cursor.lastrowid
            conn.commit()
            
            # Necesitamos saber qué hemos guardado exactamente para el "Redo"
            # Lo más fácil es leerlo
            item_nuevo = cursor.execute("SELECT * FROM carrito_temporal WHERE id_item=?", (id_generado,)).fetchone()
            
            AuditoriaManager.registrar(
                tabla='carrito_temporal',
                id_ref=id_generado,
                accion='INSERT',
                anterior=None,
                nuevo=dict(item_nuevo)
            )
            return True
        except Exception as e:
            print(f"Error al añadir al carrito: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def obtener_carrito():
        query = "SELECT * FROM carrito_temporal ORDER BY offset ASC NULLS LAST, fecha_agregado ASC"
        rows = db.execute_query(query)
        # Convertimos rows a lista de dicts o dataclasses
        return [dict(row) for row in rows] if rows else []

    @staticmethod
    def eliminar_item(id_item):
        conn = db._get_connection()
        cursor = conn.cursor()
        
        # 1. LEER ANTES DE BORRAR (Snapshot)
        cursor.execute("SELECT * FROM carrito_temporal WHERE id_item = ?", (id_item,))
        item = cursor.fetchone()
        
        if item:
            datos_backup = dict(item) # Convertimos a dict
            
            # 2. BORRAR
            cursor.execute("DELETE FROM carrito_temporal WHERE id_item = ?", (id_item,))
            conn.commit()
            conn.close() # Cerramos aquí para liberar antes de registrar log
            
            # 3. REGISTRAR EN AUDITORÍA
            # DELETE: anterior=datos, nuevo=None
            AuditoriaManager.registrar(
                tabla='carrito_temporal', 
                id_ref=id_item, 
                accion='DELETE', 
                anterior=datos_backup, 
                nuevo=None
            )

    @staticmethod
    def eliminar_grupo(grupo_nombre):
        sql = "DELETE FROM carrito_temporal WHERE grupo_nombre = ?"
        db.execute_query(sql, (grupo_nombre,), commit=True)

    @staticmethod
    def obtener_grupos_activos():
        """Devuelve una lista de los nombres de grupos que existen actualmente en el carrito temp."""
        # Usamos DISTINCT para que no salgan repetidos
        query = "SELECT DISTINCT grupo_nombre FROM carrito_temporal ORDER BY fecha_agregado DESC"
        rows = db.execute_query(query)
        return [row['grupo_nombre'] for row in rows] if rows else []
    
    @staticmethod
    def actualizar_cabecera_grupo(grupo_nombre, hora_str=None, tipo=None, notas=None, es_restaurante=None):
        """
        Actualiza las preferencias visuales de todo un grupo en el carrito temporal.
        Se usa para que los cambios persistan tras un F5.
        """
        conn = db._get_connection()
        if not conn: return
        
        # Construimos la query dinámicamente según lo que nos llegue
        campos = []
        valores = []
        
        if hora_str is not None:
            campos.append("hora_inicio_manual = ?")
            valores.append(hora_str)
        if tipo is not None:
            campos.append("tipo_comida_manual = ?")
            valores.append(tipo)
        if notas is not None:
            campos.append("notas_manual = ?")
            valores.append(notas)
        if es_restaurante is not None:
            campos.append("es_restaurante_manual = ?")
            valores.append(int(es_restaurante))
            
        if not campos: return

        valores.append(grupo_nombre) # Para el WHERE
        sql = f"UPDATE carrito_temporal SET {', '.join(campos)} WHERE grupo_nombre = ?"
        
        try:
            conn.execute(sql, valores)
            conn.commit()
        except Exception as e:
            print(f"Error actualizando cabecera: {e}")
        finally:
            conn.close()
    

class ComidaQueries:
    def añadir_comida(datos: dict):
        """
        Guarda la comida y sus ingredientes.
        Calcula automáticamente si el registro es 'Estricto' basándose en los HCs.
        """
        conn = db._get_connection()
        if not conn: return False

        try:
            cursor = conn.cursor()
            alimentos = datos.get('alimentos', [])
            
            total_hc = sum(item['hc'] for item in alimentos)
            if total_hc == 0: hc_pesados = 0
            
            hc_pesados = sum(item['hc'] for item in alimentos if item.get('es_pesado_estricto', True))
            
            if total_hc != 0:
                ratio = hc_pesados / total_hc
            else:
                ratio = 0
                
            # ---------------------------------------------------------
            # 1. INSERTAR CABECERA (Tabla 'comida')
            # ---------------------------------------------------------
            sql_comida = """
                INSERT INTO comida (
                    inicio, tipo_comida, notas, 
                    es_restaurante, es_pesado_estricto
                ) VALUES (?, ?, ?, ?, ?)
            """
            
            val_comida = (
                datos.get('inicio'),               # Datetime del selector
                datos.get('tipo_comida'),          # 'Desayuno', 'Cena'...
                datos.get('notas', ''),
                int(datos.get('es_restaurante', 0)), # Checkbox del UI
                ratio                    # <--- ¡CALCULADO AUTOMÁTICAMENTE!
            )
            
            cursor.execute(sql_comida, val_comida)
            id_comida_generado = cursor.lastrowid

            # ---------------------------------------------------------
            # 2. INSERTAR INGREDIENTES (Tabla 'partes_comida')
            # ---------------------------------------------------------
            sql_detalle = """
                INSERT INTO partes_comida (
                    id_comida, id_producto, nombre_real, 
                    offset_minutos, cantidad, es_pesado_detalle,
                    hidratos_totales, azucar_total, 
                    grasas_totales, grasas_saturadas_total,
                    proteinas_totales, fibra_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            for item in alimentos:
                
                valores_detalle = (
                    id_comida_generado,
                    item.get('id_producto'),          
                    item.get('nombre_display'),       
                    item.get('offset_minutos', 0),    
                    item.get('cantidad', 0),
                    int(item.get('es_pesado_estricto', 1)), # Guardamos también el detalle individual
                    
                    float(item.get('hc', 0)),
                    float(item.get('az', 0)),
                    float(item.get('gr', 0)),
                    float(item.get('sat', 0)), 
                    float(item.get('pr', 0)),
                    float(item.get('fb', 0))
                )
                cursor.execute(sql_detalle, valores_detalle)

            conn.commit()
            return True

        except sqlite3.Error as e:
            conn.rollback()
            print(f"❌ Error DB: {e}")
            return False
        finally:
            conn.close()


class AuditoriaManager:
    
    # --- 1. REGISTRAR CUALQUIER CAMBIO ---
    @staticmethod
    def registrar(tabla, id_ref, accion, anterior=None, nuevo=None):
        """
        Registra un cambio universal.
        - Para INSERT: anterior=None, nuevo={datos}
        - Para DELETE: anterior={datos}, nuevo=None
        - Para UPDATE: anterior={viejo}, nuevo={nuevo}
        """
        conn = db._get_connection()
        try:
            # Convertimos dicts a JSON string, gestionando fechas con default=str
            json_ant = json.dumps(anterior, default=str) if anterior else None
            json_nue = json.dumps(nuevo, default=str) if nuevo else None
            
            sql = """
                INSERT INTO historial_cambios (tabla_afectada, id_registro, accion, valor_anterior, valor_nuevo, estado)
                VALUES (?, ?, ?, ?, ?, 'ACTIVO')
            """
            conn.execute(sql, (tabla, id_ref, accion, json_ant, json_nue))
            conn.commit()
        except Exception as e:
            print(f"Error auditoría: {e}")
        finally:
            conn.close()

    # --- 2. DESHACER (UNDO) ---
    @staticmethod
    def deshacer(id_log):
        conn = db._get_connection()
        cursor = conn.cursor()
        
        # Leemos el log
        log = cursor.execute("SELECT * FROM historial_cambios WHERE id_log = ?", (id_log,)).fetchone()
        if not log or log['estado'] == 'DESHECHO': return False, "No se puede deshacer"

        tabla = log['tabla_afectada']
        id_ref = log['id_registro']
        accion = log['accion']
        
        # Recuperamos los datos del pasado
        data_ant = json.loads(log['valor_anterior']) if log['valor_anterior'] else {}
        
        # Obtenemos la PK (suponemos 'id_item' para carrito, 'id_comida' para comida, etc.)
        # Truco: Si todas tus tablas tienen PK autoincremental, necesitamos saber el nombre de la columna.
        pk_col = AuditoriaManager._obtener_pk_name(tabla)

        try:
            if accion == 'INSERT':
                # Si CREAMOS algo, para deshacer hay que BORRARLO
                cursor.execute(f"DELETE FROM {tabla} WHERE {pk_col} = ?", (id_ref,))
            
            elif accion == 'DELETE':
                # Si BORRAMOS algo, para deshacer hay que CREARLO de nuevo (con el mismo ID)
                cols = ", ".join(data_ant.keys())
                placeholders = ", ".join(["?" for _ in data_ant])
                vals = list(data_ant.values())
                cursor.execute(f"INSERT INTO {tabla} ({cols}) VALUES ({placeholders})", vals)
            
            elif accion == 'UPDATE':
                # Si CAMBIAMOS algo, restauramos el VALOR ANTERIOR
                set_clause = ", ".join([f"{k}=?" for k in data_ant.keys()])
                vals = list(data_ant.values())
                vals.append(id_ref)
                cursor.execute(f"UPDATE {tabla} SET {set_clause} WHERE {pk_col} = ?", vals)

            # Marcamos como DESHECHO (para poder rehacer luego)
            cursor.execute("UPDATE historial_cambios SET estado = 'DESHECHO' WHERE id_log = ?", (id_log,))
            conn.commit()
            return True, "Deshecho"
        except Exception as e:
            conn.rollback()
            return False, str(e)

    # --- 3. REHACER (REDO) ---
    @staticmethod
    def rehacer(id_log):
        conn = db._get_connection()
        cursor = conn.cursor()
        
        log = cursor.execute("SELECT * FROM historial_cambios WHERE id_log = ?", (id_log,)).fetchone()
        if not log or log['estado'] == 'ACTIVO': return False, "No se puede rehacer"

        tabla = log['tabla_afectada']
        id_ref = log['id_registro']
        accion = log['accion']
        pk_col = AuditoriaManager._obtener_pk_name(tabla)
        
        # Recuperamos los datos "nuevos" (los que pusimos originalmente)
        data_nue = json.loads(log['valor_nuevo']) if log['valor_nuevo'] else {}

        try:
            if accion == 'INSERT':
                # Rehacer un Insert -> Volver a Insertar
                cols = ", ".join(data_nue.keys())
                placeholders = ", ".join(["?" for _ in data_nue])
                vals = list(data_nue.values())
                cursor.execute(f"INSERT INTO {tabla} ({cols}) VALUES ({placeholders})", vals)

            elif accion == 'DELETE':
                # Rehacer un Delete -> Volver a Borrar
                cursor.execute(f"DELETE FROM {tabla} WHERE {pk_col} = ?", (id_ref,))
                
            elif accion == 'UPDATE':
                # Rehacer un Update -> Volver a poner el valor NUEVO
                set_clause = ", ".join([f"{k}=?" for k in data_nue.keys()])
                vals = list(data_nue.values())
                vals.append(id_ref)
                cursor.execute(f"UPDATE {tabla} SET {set_clause} WHERE {pk_col} = ?", vals)

            # Volvemos a marcar como ACTIVO
            cursor.execute("UPDATE historial_cambios SET estado = 'ACTIVO' WHERE id_log = ?", (id_log,))
            conn.commit()
            return True, "Rehecho"
        except Exception as e:
            conn.rollback()
            return False, str(e)

    @staticmethod
    def _obtener_pk_name(tabla):
        # Mapeo simple de tus tablas a sus Primary Keys
        if tabla == 'carrito_temporal': return 'id_item'
        if tabla == 'partes_comida': return 'id_detalle'
        if tabla == 'comida': return 'id_comida'
        if tabla == 'catalogo_productos': return 'id_producto'
        return 'id' # fallback