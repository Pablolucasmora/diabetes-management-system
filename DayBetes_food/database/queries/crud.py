"""
Módulo de queries centralizadas para todas las tablas de DayBetes.

Este archivo contiene funciones CRUD (Create, Read, Update, Delete) para:
- usuario
- catalogo
- ingesta_manual
- nevera
- etiquetas
- recetas
- etiquetas_vinculadas
- evento_ingesta
- porcion_detalle

Todas las funciones siguen el mismo patrón:
- Validaciones de entrada
- Ejecución de query con parámetros
- Manejo de transacciones (commit/rollback)
- Retorno de ID o resultado, o None en caso de error
"""

from typing import Optional, Any
from dataclasses import dataclass


# ============================================
# HELPERS GENÉRICOS
# ============================================

def _execute_query(conexion, query: str, params: dict = None, commit: bool = True) -> Optional[Any]:
    """Helper genérico para ejecutar queries."""
    try:
        with conexion.cursor() as cursor:
            cursor.execute(query, params or {})
            if commit:
                conexion.commit()
            return cursor.fetchone()
    except Exception as e:
        conexion.rollback()
        print(f"Error en query: {e}")
        return None


def _execute_query_many(conexion, query: str, params: dict = None, commit: bool = True) -> list:
    """Helper genérico para ejecutar queries que retornan múltiples filas."""
    try:
        with conexion.cursor() as cursor:
            cursor.execute(query, params or {})
            if commit:
                conexion.commit()
            return cursor.fetchall()
    except Exception as e:
        conexion.rollback()
        print(f"Error en query: {e}")
        return []


def _build_update_query(table: str, params: dict, where_field: str = "id") -> Optional[str]:
    """
    Construye una query UPDATE genérica y segura.
    Filtra automáticamente el campo WHERE para no actualizarlo en el SET
    y descarta los valores None para evitar sobrescribir con NULL accidentalmente.
    
    Args:
        table: Nombre de la tabla
        params: Diccionario con todos los campos y valores
        where_field: Campo para el WHERE (default: "id")
    
    Returns:
        Query SQL generada, o None si no hay campos válidos para actualizar.
    """
    # Extraemos solo las keys que no son el ID y cuyo valor no es None
    fields = [k for k, v in params.items() if k != where_field and v is not None]
    
    if not fields:
        return None
        
    set_clause = ", ".join([f"{field} = %({field})s" for field in fields])
    return f"UPDATE {table} SET {set_clause} WHERE {where_field} = %({where_field})s RETURNING {where_field};"


# ============================================
# USUARIO
# ============================================

def add_usuario(conexion, nombre: str, correo: str, clave: str) -> Optional[int]:
    """Crea un nuevo usuario."""
    query = """
        INSERT INTO usuario (nombre, correo, clave)
        VALUES (%(nombre)s, %(correo)s, %(clave)s)
        RETURNING id;
    """
    result = _execute_query(conexion, query, {"nombre": nombre, "correo": correo, "clave": clave})
    return result[0] if result else None


def get_usuario(conexion, usuario_id: int) -> Optional[dict]:
    """Obtiene un usuario por ID."""
    query = "SELECT * FROM usuario WHERE id = %(id)s;"
    return _execute_query(conexion, query, {"id": usuario_id}, commit=False)


def get_usuario_por_correo(conexion, correo: str) -> Optional[dict]:
    """Obtiene un usuario por correo."""
    query = "SELECT * FROM usuario WHERE correo = %(correo)s;"
    return _execute_query(conexion, query, {"correo": correo}, commit=False)


def get_all_usuarios(conexion) -> list:
    """Obtiene todos los usuarios."""
    query = "SELECT * FROM usuario ORDER BY fecha_registro DESC;"
    return _execute_query_many(conexion, query, commit=False)


def update_usuario(conexion, usuario_id: int, nombre: str = None, correo: str = None) -> bool:
    """Actualiza un usuario. Solo actualiza los campos proporcionados."""
    params = {"id": usuario_id, "nombre": nombre, "correo": correo}
    query = _build_update_query("usuario", params)
    
    if not query:
        return False
        
    result = _execute_query(conexion, query, params)
    return result is not None


def delete_usuario(conexion, usuario_id: int) -> bool:
    """Elimina un usuario por ID."""
    query = "DELETE FROM usuario WHERE id = %(id)s RETURNING id;"
    result = _execute_query(conexion, query, {"id": usuario_id})
    return result is not None


# ============================================
# CATALOGO
# ============================================

def add_catalogo(conexion, datos: dict) -> Optional[int]:
    """
    Añade un nuevo alimento al catálogo.
    datos: dict con los campos del alimento
    """
    query = """
        INSERT INTO catalogo (
            created_by, nombre, marca, categoria, subtipo, estado_inicial,
            nutriscore, nova, yuka, porcion_default,
            calorias_100g, hidratos_100g, azucares_100g, grasas_100g,
            saturadas_100g, proteinas_100g, fibra_100g,
            cafeina, alcohol, cod_barras, factor_cocinado, favorito
        )
        VALUES (
            %(created_by)s, %(nombre)s, %(marca)s, %(categoria)s, %(subtipo)s, %(estado_inicial)s,
            %(nutriscore)s, %(nova)s, %(yuka)s, %(porcion_default)s,
            %(calorias_100g)s, %(hidratos_100g)s, %(azucares_100g)s, %(grasas_100g)s,
            %(saturadas_100g)s, %(proteinas_100g)s, %(fibra_100g)s,
            %(cafeina)s, %(alcohol)s, %(cod_barras)s, %(factor_cocinado)s, %(favorito)s
        )
        RETURNING id;
    """
    result = _execute_query(conexion, query, datos)
    return result[0] if result else None


def get_catalogo(conexion, catalogo_id: int) -> Optional[dict]:
    """Obtiene un alimento del catálogo por ID."""
    query = "SELECT * FROM catalogo WHERE id = %(id)s;"
    return _execute_query(conexion, query, {"id": catalogo_id}, commit=False)


def get_all_catalogo(conexion, search: str = None, categoria: str = None, favorito: bool = None) -> list:
    """Obtiene todos los alimentos del catálogo con filtros opcionales."""
    conditions = []
    params = {}
    
    if search:
        conditions.append("nombre ILIKE %(search)s")
        params["search"] = f"%{search}%"
    if categoria:
        conditions.append("categoria = %(categoria)s")
        params["categoria"] = categoria
    if favorito is not None:
        conditions.append("favorito = %(favorito)s")
        params["favorito"] = favorito
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM catalogo {where_clause} ORDER BY nombre;"
    
    return _execute_query_many(conexion, query, params, commit=False)


def update_catalogo(conexion, catalogo_id: int, datos: dict) -> bool:
    """Actualiza un alimento del catálogo."""
    if not datos:
        return False
    
    params = {**datos, "id": catalogo_id}
    query = _build_update_query("catalogo", params)
    
    if not query:
        return False
        
    result = _execute_query(conexion, query, params)
    return result is not None


def update_favorito_catalogo(conexion, catalogo_id: int, favorito: bool) -> bool:
    """Actualiza el estado de favorito de un alimento."""
    query = "UPDATE catalogo SET favorito = %(favorito)s WHERE id = %(id)s RETURNING id;"
    result = _execute_query(conexion, query, {"id": catalogo_id, "favorito": favorito})
    return result is not None


def delete_catalogo(conexion, catalogo_id: int) -> bool:
    """Elimina un alimento del catálogo."""
    query = "DELETE FROM catalogo WHERE id = %(id)s RETURNING id;"
    result = _execute_query(conexion, query, {"id": catalogo_id})
    return result is not None


# ============================================
# INGESTA MANUAL
# ============================================

def add_ingesta_manual(conexion, datos: dict) -> Optional[int]:
    """Añade una nueva ingesta manual."""
    query = """
        INSERT INTO ingesta_manual (
            created_by, nombre, descripcion, subtipo, procedencia,
            cantidad_g, calorias_100g, hidratos_100g, azucares_100g,
            grasas_100g, saturadas_100g, proteinas_100g, fibra_100g,
            cafeina, alcohol, indice_glucemico, confianza_ig, favorito
        )
        VALUES (
            %(created_by)s, %(nombre)s, %(descripcion)s, %(subtipo)s, %(procedencia)s,
            %(cantidad_g)s, %(calorias_100g)s, %(hidratos_100g)s, %(azucares_100g)s,
            %(grasas_100g)s, %(saturadas_100g)s, %(proteinas_100g)s, %(fibra_100g)s,
            %(cafeina)s, %(alcohol)s, %(indice_glucemico)s, %(confianza_ig)s, %(favorito)s
        )
        RETURNING id;
    """
    result = _execute_query(conexion, query, datos)
    return result[0] if result else None


def get_ingesta_manual(conexion, ingesta_id: int) -> Optional[dict]:
    """Obtiene una ingesta manual por ID."""
    query = "SELECT * FROM ingesta_manual WHERE id = %(id)s;"
    return _execute_query(conexion, query, {"id": ingesta_id}, commit=False)


def get_all_ingesta_manual(conexion, user_id: int = None, search: str = None, favorito: bool = None) -> list:
    """Obtiene todas las ingestas manuales con filtros opcionales."""
    conditions = []
    params = {}
    
    if user_id:
        conditions.append("created_by = %(user_id)s")
        params["user_id"] = user_id
    if search:
        conditions.append("nombre ILIKE %(search)s")
        params["search"] = f"%{search}%"
    if favorito is not None:
        conditions.append("favorito = %(favorito)s")
        params["favorito"] = favorito
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM ingesta_manual {where_clause} ORDER BY nombre;"
    
    return _execute_query_many(conexion, query, params, commit=False)


def update_ingesta_manual(conexion, ingesta_id: int, datos: dict) -> bool:
    """Actualiza una ingesta manual."""
    if not datos:
        return False
    
    params = {**datos, "id": ingesta_id}
    query = _build_update_query("ingesta_manual", params)
    
    if not query:
        return False
        
    result = _execute_query(conexion, query, params)
    return result is not None


def delete_ingesta_manual(conexion, ingesta_id: int) -> bool:
    """Elimina una ingesta manual."""
    query = "DELETE FROM ingesta_manual WHERE id = %(id)s RETURNING id;"
    result = _execute_query(conexion, query, {"id": ingesta_id})
    return result is not None


# ============================================
# NEVERA
# ============================================

def add_nevera(conexion, user_id: int, nombre_tupper: str = None, es_compuesto: bool = False, peso_total: float = None) -> Optional[int]:
    """Crea un nuevo registro en la nevera."""
    query = """
        INSERT INTO nevera (user_id, nombre_tupper, es_compuesto, peso_total_tupper)
        VALUES (%(user_id)s, %(nombre_tupper)s, %(es_compuesto)s, %(peso_total)s)
        RETURNING id;
    """
    result = _execute_query(conexion, query, {
        "user_id": user_id,
        "nombre_tupper": nombre_tupper,
        "es_compuesto": es_compuesto,
        "peso_total": peso_total
    })
    return result[0] if result else None


def get_nevera(conexion, nevera_id: int) -> Optional[dict]:
    """Obtiene un registro de la nevera por ID."""
    query = "SELECT * FROM nevera WHERE id = %(id)s;"
    return _execute_query(conexion, query, {"id": nevera_id}, commit=False)


def get_all_nevera(conexion, user_id: int) -> list:
    """Obtiene todos los tuppers de la nevera de un usuario."""
    query = "SELECT * FROM nevera WHERE user_id = %(user_id)s ORDER BY fecha_entrada DESC;"
    return _execute_query_many(conexion, query, {"user_id": user_id}, commit=False)


def update_nevera(conexion, nevera_id: int, nombre_tupper: str = None, es_compuesto: bool = None, peso_total: float = None) -> bool:
    """Actualiza un registro de la nevera."""
    params = {
        "id": nevera_id, 
        "nombre_tupper": nombre_tupper, 
        "es_compuesto": es_compuesto, 
        "peso_total_tupper": peso_total
    }
    
    query = _build_update_query("nevera", params)
    
    if not query:
        return False
        
    result = _execute_query(conexion, query, params)
    return result is not None


def delete_nevera(conexion, nevera_id: int) -> bool:
    """Elimina un registro de la nevera."""
    query = "DELETE FROM nevera WHERE id = %(id)s RETURNING id;"
    result = _execute_query(conexion, query, {"id": nevera_id})
    return result is not None


# ============================================
# ETIQUETAS
# ============================================

def add_etiqueta(conexion, nombre: str, descripcion: str = None) -> Optional[int]:
    """Crea una nueva etiqueta."""
    query = """
        INSERT INTO etiquetas (nombre, descripcion)
        VALUES (%(nombre)s, %(descripcion)s)
        RETURNING id;
    """
    result = _execute_query(conexion, query, {"nombre": nombre, "descripcion": descripcion})
    return result[0] if result else None


def get_etiqueta(conexion, etiqueta_id: int) -> Optional[dict]:
    """Obtiene una etiqueta por ID."""
    query = "SELECT * FROM etiquetas WHERE id = %(id)s;"
    return _execute_query(conexion, query, {"id": etiqueta_id}, commit=False)


def get_all_etiquetas(conexion) -> list:
    """Obtiene todas las etiquetas."""
    query = "SELECT * FROM etiquetas ORDER BY nombre;"
    return _execute_query_many(conexion, query, commit=False)


def get_etiqueta_por_nombre(conexion, nombre: str) -> Optional[dict]:
    """Obtiene una etiqueta por nombre."""
    query = "SELECT * FROM etiquetas WHERE nombre = %(nombre)s;"
    return _execute_query(conexion, query, {"nombre": nombre}, commit=False)


def update_etiqueta(conexion, etiqueta_id: int, nombre: str = None, descripcion: str = None) -> bool:
    """Actualiza una etiqueta."""
    params = {"id": etiqueta_id, "nombre": nombre, "descripcion": descripcion}
    query = _build_update_query("etiquetas", params)
    
    if not query:
        return False
        
    result = _execute_query(conexion, query, params)
    return result is not None


def delete_etiqueta(conexion, etiqueta_id: int) -> bool:
    """Elimina una etiqueta."""
    query = "DELETE FROM etiquetas WHERE id = %(id)s RETURNING id;"
    result = _execute_query(conexion, query, {"id": etiqueta_id})
    return result is not None


# ============================================
# RECETAS
# ============================================

def add_receta(conexion, user_id: int, nombre: str, tipo_comida: str = None, notas: str = None, favorito: bool = False) -> Optional[int]:
    """Crea una nueva receta."""
    query = """
        INSERT INTO recetas (user_id, tipo_comida, nombre, notas, favorito)
        VALUES (%(user_id)s, %(tipo_comida)s, %(nombre)s, %(notas)s, %(favorito)s)
        RETURNING id;
    """
    result = _execute_query(conexion, query, {
        "user_id": user_id,
        "tipo_comida": tipo_comida,
        "nombre": nombre,
        "notas": notas,
        "favorito": favorito
    })
    return result[0] if result else None


def get_receta(conexion, receta_id: int) -> Optional[dict]:
    """Obtiene una receta por ID."""
    query = "SELECT * FROM recetas WHERE id = %(id)s;"
    return _execute_query(conexion, query, {"id": receta_id}, commit=False)


def get_all_recetas(conexion, user_id: int = None, tipo_comida: str = None, favorito: bool = None) -> list:
    """Obtiene todas las recetas con filtros opcionales."""
    conditions = []
    params = {}
    
    if user_id:
        conditions.append("user_id = %(user_id)s")
        params["user_id"] = user_id
    if tipo_comida:
        conditions.append("tipo_comida = %(tipo_comida)s")
        params["tipo_comida"] = tipo_comida
    if favorito is not None:
        conditions.append("favorito = %(favorito)s")
        params["favorito"] = favorito
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM recetas {where_clause} ORDER BY nombre;"
    
    return _execute_query_many(conexion, query, params, commit=False)


def update_receta(conexion, receta_id: int, nombre: str = None, tipo_comida: str = None, notas: str = None, favorito: bool = None) -> bool:
    """Actualiza una receta."""
    params = {
        "id": receta_id, 
        "nombre": nombre, 
        "tipo_comida": tipo_comida, 
        "notas": notas, 
        "favorito": favorito
    }
    
    query = _build_update_query("recetas", params)
    
    if not query:
        return False
        
    result = _execute_query(conexion, query, params)
    return result is not None


def delete_receta(conexion, receta_id: int) -> bool:
    """Elimina una receta."""
    query = "DELETE FROM recetas WHERE id = %(id)s RETURNING id;"
    result = _execute_query(conexion, query, {"id": receta_id})
    return result is not None


# ============================================
# ETIQUETAS VINCULADAS
# ============================================

def add_etiqueta_vinculada(conexion, etiqueta_id: int, entidad: str, entidad_id: int) -> Optional[int]:
    """Vincula una etiqueta a una entidad."""
    if entidad not in ("catalogo", "receta", "ingesta_manual"):
        raise ValueError("Entidad inválida. Debe ser 'catalogo', 'receta' o 'ingesta_manual'")
    
    datos = {"etiqueta_id": etiqueta_id}
    datos[f"{entidad}_id"] = entidad_id
    
    query = f"""
        INSERT INTO etiquetas_vinculadas (etiqueta_id, {entidad}_id)
        VALUES (%(etiqueta_id)s, %({entidad}_id)s)
        RETURNING id;
    """
    result = _execute_query(conexion, query, datos)
    return result[0] if result else None


def get_etiquetas_vinculadas(conexion, entidad: str, entidad_id: int) -> list:
    """Obtiene las etiquetas vinculadas a una entidad."""
    if entidad not in ("catalogo", "receta", "ingesta_manual"):
        raise ValueError("Entidad inválida")
    
    query = f"""
        SELECT e.* FROM etiquetas e
        JOIN etiquetas_vinculadas ev ON e.id = ev.etiqueta_id
        WHERE ev.{entidad}_id = %(entidad_id)s
        ORDER BY e.nombre;
    """
    return _execute_query_many(conexion, query, {"entidad_id": entidad_id}, commit=False)


def delete_etiqueta_vinculada(conexion, etiqueta_id: int, entidad: str, entidad_id: int) -> bool:
    """Elimina una vinculación de etiqueta."""
    if entidad not in ("catalogo", "receta", "ingesta_manual"):
        raise ValueError("Entidad inválida")
    
    query = f"""
        DELETE FROM etiquetas_vinculadas 
        WHERE etiqueta_id = %(etiqueta_id)s AND {entidad}_id = %(entidad_id)s
        RETURNING id;
    """
    result = _execute_query(conexion, query, {"etiqueta_id": etiqueta_id, "entidad_id": entidad_id})
    return result is not None


def delete_all_etiquetas_vinculadas(conexion, entidad: str, entidad_id: int) -> bool:
    """Elimina todas las etiquetas vinculadas a una entidad."""
    if entidad not in ("catalogo", "receta", "ingesta_manual"):
        raise ValueError("Entidad inválida")
    
    query = f"DELETE FROM etiquetas_vinculadas WHERE {entidad}_id = %(entidad_id)s RETURNING id;"
    result = _execute_query(conexion, query, {"entidad_id": entidad_id})
    return result is not None


# ============================================
# EVENTO INGESTA
# ============================================

def add_evento_ingesta(conexion, user_id: int, estado: str, tipo_comida: str = None, nombre: str = None,
                       hora_comida=None, comida_fuera: bool = False, dosis_insulina: bool = True,
                       cantidad_total: float = None, cantidad_ingerida: float = None,
                       confianza_cantidad: float = None, confianza_calidad: float = None,
                       notas: str = None, **kwargs) -> Optional[int]:
    """Crea un nuevo evento de ingesta."""

    # Campos obligatorios siempre presentes
    datos = {
        "user_id": user_id,
        "estado": estado,
        "comida_fuera": comida_fuera,
        "dosis_insulina": dosis_insulina,
    }

    # Campos opcionales: solo se añaden si tienen valor
    opcionales = {
        "tipo_comida": tipo_comida,
        "nombre": nombre,
        "hora_comida": hora_comida,
        "cantidad_total": cantidad_total,
        "cantidad_ingerida": cantidad_ingerida,
        "confianza_cantidad": confianza_cantidad,
        "confianza_calidad": confianza_calidad,
        "notas": notas,
        "incertidumbre_hidratos": kwargs.get("incertidumbre_hidratos"),
        "incertidumbre_azucares": kwargs.get("incertidumbre_azucares"),
        "incertidumbre_grasas": kwargs.get("incertidumbre_grasas"),
        "incertidumbre_saturadas": kwargs.get("incertidumbre_saturadas"),
        "incertidumbre_proteinas": kwargs.get("incertidumbre_proteinas"),
        "incertidumbre_fibra": kwargs.get("incertidumbre_fibra"),
    }

    datos.update({k: v for k, v in opcionales.items() if v is not None})

    columnas = ", ".join(datos.keys())
    valores = ", ".join(f"%({k})s" for k in datos.keys())

    query = f"""
        INSERT INTO evento_ingesta ({columnas})
        VALUES ({valores})
        RETURNING id;
    """

    result = _execute_query(conexion, query, datos)
    return result["id"] if result else None

def get_evento_ingesta(conexion, evento_id: int) -> Optional[dict]:
    """Obtiene un evento de ingesta por ID."""
    query = "SELECT * FROM evento_ingesta WHERE id = %(id)s;"
    return _execute_query(conexion, query, {"id": evento_id}, commit=False)


def get_all_evento_ingesta(conexion, user_id: int = None, estado: str = None, tipo_comida: str = None) -> list:
    """Obtiene todos los eventos de ingesta con filtros opcionales."""
    conditions = []
    params = {}
    
    if user_id:
        conditions.append("user_id = %(user_id)s")
        params["user_id"] = user_id
    if estado:
        conditions.append("estado = %(estado)s")
        params["estado"] = estado
    if tipo_comida:
        conditions.append("tipo_comida = %(tipo_comida)s")
        params["tipo_comida"] = tipo_comida
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM evento_ingesta {where_clause} ORDER BY hora_comida DESC;"
    
    return _execute_query_many(conexion, query, params, commit=False)


def get_eventos_carrito(conexion, user_id: int) -> list:
    """Obtiene los eventos en estado 'planificado' (carrito) de un usuario."""
    query = """
        SELECT * FROM evento_ingesta 
        WHERE user_id = %(user_id)s AND estado = 'planificado' 
        ORDER BY hora_comida;
    """
    return _execute_query_many(conexion, query, {"user_id": user_id}, commit=False)


def update_evento_ingesta(conexion, evento_id: int, datos: dict) -> bool:
    """Actualiza un evento de ingesta."""
    if not datos:
        return False
    
    params = {**datos, "id": evento_id}
    query = _build_update_query("evento_ingesta", params)
    
    if not query:
        return False
        
    result = _execute_query(conexion, query, params)
    return result is not None


def cambiar_estado_evento(conexion, evento_id: int, nuevo_estado: str) -> bool:
    """Cambia el estado de un evento de ingesta (planificado -> consumido)."""
    if nuevo_estado not in ("planificado", "consumido"):
        raise ValueError("Estado inválido. Debe ser 'planificado' o 'consumido'")
    
    query = "UPDATE evento_ingesta SET estado = %(estado)s WHERE id = %(id)s RETURNING id;"
    result = _execute_query(conexion, query, {"id": evento_id, "estado": nuevo_estado})
    return result is not None


def delete_evento_ingesta(conexion, evento_id: int) -> bool:
    """Elimina un evento de ingesta."""
    query = "DELETE FROM evento_ingesta WHERE id = %(id)s RETURNING id;"
    result = _execute_query(conexion, query, {"id": evento_id})
    return result is not None


# ============================================
# PORCION DETALLE
# ============================================

def add_porcion_detalle(
    conexion,
    origen: str,
    origen_id: int,
    destino: str,
    destino_id: int,
    cantidad_g: float,
    cocinado: str = None,
    conservacion: str = None,
    estado_final: str = None,
    pesado_estricto: bool = None,
    calidad_macros: bool = None,
    cantidad_plato: float = None,
    es_peso_cocinado: bool = False,
    offset_minutos: int = None
) -> Optional[int]:
    """Añade un registro a porcion_detalle de forma centralizada."""
    if origen not in ("catalogo", "ingesta_manual"):
        raise ValueError("Origen inválido")
    if destino not in ("evento_ingesta", "receta", "nevera"):
        raise ValueError("Destino inválido")
    if cantidad_g <= 0:
        raise ValueError("cantidad_g debe ser positivo")
    if offset_minutos is not None and destino != "evento_ingesta":
        raise ValueError("offset_minutos solo para evento_ingesta")
    
    datos = {
        "cantidad_g": cantidad_g,
        "catalogo_id": origen_id if origen == "catalogo" else None,
        "ingesta_manual_id": origen_id if origen == "ingesta_manual" else None,
        "evento_ingesta_id": destino_id if destino == "evento_ingesta" else None,
        "receta_id": destino_id if destino == "receta" else None,
        "nevera_id": destino_id if destino == "nevera" else None,
        "cocinado": cocinado,
        "conservacion": conservacion,
        "estado_final": estado_final,
        "pesado_estricto": pesado_estricto,
        "calidad_macros": calidad_macros,
        "cantidad_plato": cantidad_plato,
        "es_peso_cocinado": es_peso_cocinado,
        "offset_minutos": offset_minutos
    }
    
    query = """
        INSERT INTO porcion_detalle (
            cantidad_g, catalogo_id, ingesta_manual_id,
            evento_ingesta_id, receta_id, nevera_id,
            cocinado, conservacion, estado_final,
            pesado_estricto, calidad_macros, cantidad_plato,
            es_peso_cocinado, offset_minutos
        )
        VALUES (
            %(cantidad_g)s, %(catalogo_id)s, %(ingesta_manual_id)s,
            %(evento_ingesta_id)s, %(receta_id)s, %(nevera_id)s,
            %(cocinado)s, %(conservacion)s, %(estado_final)s,
            %(pesado_estricto)s, %(calidad_macros)s, %(cantidad_plato)s,
            %(es_peso_cocinado)s, %(offset_minutos)s
        )
        RETURNING id;
    """
    
    result = _execute_query(conexion, query, datos)
    return result[0] if result else None


def get_porcion_detalle_por_evento(conexion, evento_ingesta_id: int) -> list:
    """Obtiene todas las porciones de un evento de ingesta."""
    query = """
        SELECT pd.*, c.nombre as nombre_catalogo, im.nombre as nombre_ingesta_manual
        FROM porcion_detalle pd
        LEFT JOIN catalogo c ON pd.catalogo_id = c.id
        LEFT JOIN ingesta_manual im ON pd.ingesta_manual_id = im.id
        WHERE pd.evento_ingesta_id = %(id)s
        ORDER BY pd.id;
    """
    return _execute_query_many(conexion, query, {"id": evento_ingesta_id}, commit=False)


def get_porcion_detalle_por_receta(conexion, receta_id: int) -> list:
    """Obtiene todas las porciones de una receta."""
    query = """
        SELECT pd.*, c.nombre as nombre_catalogo, im.nombre as nombre_ingesta_manual
        FROM porcion_detalle pd
        LEFT JOIN catalogo c ON pd.catalogo_id = c.id
        LEFT JOIN ingesta_manual im ON pd.ingesta_manual_id = im.id
        WHERE pd.receta_id = %(id)s
        ORDER BY pd.id;
    """
    return _execute_query_many(conexion, query, {"id": receta_id}, commit=False)


def get_porcion_detalle_por_nevera(conexion, nevera_id: int) -> list:
    """Obtiene todas las porciones de una nevera."""
    query = """
        SELECT pd.*, c.nombre as nombre_catalogo, im.nombre as nombre_ingesta_manual
        FROM porcion_detalle pd
        LEFT JOIN catalogo c ON pd.catalogo_id = c.id
        LEFT JOIN ingesta_manual im ON pd.ingesta_manual_id = im.id
        WHERE pd.nevera_id = %(id)s
        ORDER BY pd.id;
    """
    return _execute_query_many(conexion, query, {"id": nevera_id}, commit=False)


def delete_porcion_detalle(conexion, porcion_id: int) -> bool:
    """Elimina una porción detalle."""
    query = "DELETE FROM porcion_detalle WHERE id = %(id)s RETURNING id;"
    result = _execute_query(conexion, query, {"id": porcion_id})
    return result is not None