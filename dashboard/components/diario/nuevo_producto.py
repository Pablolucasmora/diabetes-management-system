import streamlit as st
import database.queries as dq
from database.queries import ProductoModel
import re


def parsear_macros(texto):
    """
    Busca patrones como '10.5g hidratos', '20 hc', '30g proteina'.
    Devuelve un diccionario con los valores normalizados.
    """
    # 1. Diccionario de sinónimos (normalización)
    # La clave es lo que buscamos, el valor es el campo de la BD
    mapa_sinonimos = {
        'hidratos': 'hidratos_g', 'hc': 'hidratos_g', 'ch': 'hidratos_g', 'carbos': 'hidratos_g',
        'azucar': 'azucares_g', 'azucares': 'azucares_g', 'az': 'azucares_g',
        'proteinas': 'proteinas_g', 'proteina': 'proteinas_g', 'pr': 'proteinas_g', 'pro': 'proteinas_g',
        'grasas': 'grasas_g', 'grasa': 'grasas_g', 'gr': 'grasas_g',
        'saturadas': 'grasas_sat_g', 'sat': 'grasas_sat_g', 'st': 'grasas_sat_g', 'gs': 'grasas_sat_g', 
        'fibra': 'fibra_g', 'fb': 'fibra_g'
    }
    
    valores = {
        'hidratos_g': 0.0, 'azucares_g': 0.0, 'proteinas_g': 0.0, 
        'fibra_g': None, 'grasas_g': 0.0, 'grasas_sat_g': 0.0
    }
    
    if not texto:
        return valores

    # 2. Expresión regular: Busca (Numero) + (espacio opcional) + (g opcional) + (Palabra)
    # Ej: "30.5g hidratos" -> Grupo 1: 30.5, Grupo 2: hidratos
    patron = r"(\d+(?:[.,]\d+)?)\s*(?:(?:g|ml)(?![a-zA-Z]))?\s*([a-zA-Z]+)"
    
    coincidencias = re.findall(patron, texto.lower())
    
    for cantidad_str, macro_raw in coincidencias:
        # Limpiamos la cantidad (cambiar coma por punto)
        try:
            cantidad = float(cantidad_str.replace(',', '.'))
            
            # Buscamos si la palabra 'macro_raw' está en nuestros sinónimos
            # Usamos coincidencia parcial: si escribes "prot", busca algo que empiece por "prot"
            campo_destino = None
            
            # Busqueda exacta primero
            if macro_raw in mapa_sinonimos:
                campo_destino = mapa_sinonimos[macro_raw]
            else:
                # Búsqueda aproximada (startswith)
                for clave, valor in mapa_sinonimos.items():
                    if clave.startswith(macro_raw):
                        campo_destino = valor
                        break
            
            if campo_destino:
                valores[campo_destino] = cantidad
                
        except ValueError:
            continue
            
    return valores

def render_nuevo_producto():
    
    # --- CALLBACK: LÓGICA DE GUARDADO ---
    def guardar_catalogo_callback():
        # 1. Recuperamos datos del estado (necesitamos las keys definidas abajo)
        macros_txt = st.session_state.get("input_smart_macros", "")
        categoria = st.session_state.get("categoria_producto", "Alimento")
        
        # Datos del formulario (usando .get por seguridad)
        nombre = st.session_state.get("cat_nombre", "")
        marca = st.session_state.get("cat_marca", "")
        subtipo = st.session_state.get("cat_subtipo", "")
        nutriscore = st.session_state.get("cat_nutriscore", "Desconocido")
        nova = st.session_state.get("cat_nova", 4)
        
        porcion_txt = st.session_state.get("cat_porcion", "")
        notas_prod = st.session_state.get("cat_notas", "")
        
        # Dinámicos (solo existirán en state si se renderizaron, sino default)
        grad_txt = st.session_state.get("cat_grad", "")
        caf_txt = st.session_state.get("cat_caf", "")
        gas = st.session_state.get("cat_gas", False)

        # 2. Parseo y validación
        macros = parsear_macros(macros_txt)
        
        if not nombre:
            st.error("❌ El nombre es obligatorio")
            return # Paramos aquí

        try:
            # Conversiones seguras
            grad_val = float(grad_txt.replace(',', '.')) if grad_txt else 0.0
            caf_val = float(caf_txt.replace(',', '.')) if caf_txt else 0.0
            porcion_val = int(porcion_txt) if porcion_txt and porcion_txt.isdigit() else None
            
            # Parche para grasas_sat (por si tu parsear_macros antiguo no lo devuelve)
            sat = macros.get('grasas_sat_g', 0.0)

            # 3. Creación del modelo
            nuevo = ProductoModel(
                nombre=nombre,
                marca=marca if marca else None,
                categoria=categoria,
                subtipo=subtipo,

                hidratos_g=macros.get('hidratos_g', 0.0),
                azucares_g=macros.get('azucares_g', 0.0),
                proteinas_g=macros.get('proteinas_g', 0.0),
                fibra_g=macros.get('fibra_g') if macros.get('fibra_g') else None,
                grasas_g=macros.get('grasas_g', 0.0),
                # ¡OJO! Asegúrate de que ProductoModel acepta este campo en tu queries.py local
                grasas_sat_g=sat, 

                graduacion_pct=grad_val,
                cafeina_mg=caf_val,
                es_gas=gas,
                porcion_default_g=porcion_val,
                notas=notas_prod,
                nutriscore=nutriscore,
                nova=nova
            )

            # 4. Insertar en BD
            nuevo_id = dq.CatalogoQueries.insertar_producto(nuevo)

            if nuevo_id:
                st.toast(f"✅ Guardado: {nombre}")
                st.session_state.id_recien_creado = nuevo_id
                
                # LIMPIEZA DEL INPUT EXTERNO (El objetivo de todo esto)
                st.session_state.input_smart_macros = ""
                st.cache_data.clear()
                # El formulario se limpiará solo gracias a clear_on_submit=True
        
        except Exception as e:
            st.error(f"🚨 Error al guardar: {e}")

    # --- UI (INTERFAZ) ---
    with st.expander("➕ Crear producto nuevo", expanded=False):

        # PASO 1 — MACROS (REACTIVO - Input externo)
        st.info("💡 **Paso 1:** Escribe los macros y pulsa ENTER.")

        input_macros = st.text_input(
            "Macros (Smart Text)",
            placeholder="Ej: 30hc, 12az, 20pr, 10 grasas...",
            key="input_smart_macros" # Key necesaria para limpiar desde callback
        )

        macros = parsear_macros(input_macros)
    
        if input_macros:
            partes = []
            if macros.get('hidratos_g', 0) > 0: partes.append(f":blue[**{macros['hidratos_g']}g HC**]")
            if macros.get('azucares_g', 0) > 0: partes.append(f":violet[{macros['azucares_g']}g Azúcar]")
            if macros.get('proteinas_g', 0) > 0: partes.append(f":green[**{macros['proteinas_g']}g Prot**]")
            if macros.get('grasas_g', 0) > 0: partes.append(f":orange[**{macros['grasas_g']}g Grasas**]")
            if macros.get('fibra_g') and macros['fibra_g'] > 0: partes.append(f":grey[{macros['fibra_g']}g Fibra]")
            if macros.get('grasas_sat_g', 0) > 0: partes.append(f":red[{macros['grasas_sat_g']}g Sat.]")

            if partes:
                st.markdown("✅ **Detectado:** " + " | ".join(partes))
            else:
                st.caption("⚠️ Formato no reconocido.")

        st.divider()

        # PASO 2 — CATEGORÍA (REACTIVO - Fuera del form para condicionales)
        st.write("**Paso 2:** Selecciona la categoría")

        categoria = st.selectbox(
            "Categoría*",
            ["Alimento", "Bebida", "Suplemento"],
            key="categoria_producto"
        )

        st.divider()

        # PASO 3 — FORMULARIO (NO REACTIVO)
        st.write("**Paso 3:** Completa los datos y guarda")

        with st.form("form_alta_completa", clear_on_submit=True):

            col1, col2 = st.columns(2)
            # AÑADIMOS KEYS A TODO PARA QUE EL CALLBACK LO LEA
            col1.text_input("Nombre*", key="cat_nombre")
            col2.text_input("Marca", key="cat_marca")

            st.text_input("Subtipo (ej: Pasta, Refresco...)", key="cat_subtipo")

            c1, c2 = st.columns(2)
            c1.selectbox("NutriScore", ["A", "B", "C", "D", "E", "Desconocido"], index=5, key="cat_nutriscore")
            c2.selectbox("NOVA", [1, 2, 3, 4, "Desconocido"], index=4, key="cat_nova")

            # CAMPOS DINÁMICOS
            if categoria == "Bebida":
                b1, b2, b3 = st.columns(3)
                b1.text_input("Grad. %", key="cat_grad")
                b2.text_input("Cafeína (mg)", key="cat_caf")
                b3.checkbox("¿Gas?", value=False, key="cat_gas")

            st.text_input("Porción por defecto (g/ml)", value="", key="cat_porcion")
            st.text_area("Notas", key="cat_notas")

            # BOTÓN DISPARA EL CALLBACK
            st.form_submit_button(
                "💾 Guardar en Catálogo",
                type="primary",
                on_click=guardar_catalogo_callback # <--- AQUÍ LA MAGIA
            )

def render_custom_food_entry():
    """
    Entrada manual corregida por el Tutor:
    - Usa Callback para permitir limpiar el input 'manual_macros' (que está fuera del form).
    - Protege el acceso a claves de macros que quizás no existan (grasas_sat_g).
    """
    
    # --- CALLBACK: Lógica de guardado antes de recargar la página ---
    def guardar_manual_callback():
        # 1. Recuperar valores del estado (widgets)
        macros_txt = st.session_state.get("manual_macros", "")
        # Recuperamos el grupo: si es nuevo, usamos el input de texto; si no, el selectbox.
        grupo_select = st.session_state.get("manual_grupo_select", "")
        grupo_new = st.session_state.get("manual_grupo_new", "")
        
        # Lógica de nombre de grupo
        nombre_grupo_final = grupo_new if grupo_select == "➕ Nuevo Grupo..." else grupo_select
        
        # Resto de campos
        nombre = st.session_state.get("manual_nombre", "")
        offset = st.session_state.get("manual_offset", "")
        cantidad = st.session_state.get("aprox_cantidad", "")
        pesado_estricto = st.session_state.get("manual_pesado", False)

        # 2. Parseo y Validaciones
        macros = parsear_macros(macros_txt)
        
        # Parche para evitar KeyError si parsear_macros no devuelve 'grasas_sat_g'
        sat = macros.get('grasas_sat_g', 0.0) 

        if not nombre:
            st.error("⚠️ El nombre es obligatorio.")
            return # Detenemos callback
        if not nombre_grupo_final:
            st.error("⚠️ Debes definir un nombre para el grupo.")
            return
        if cantidad and not cantidad.isdigit():
            st.error("⚠️ La cantidad debe ser un número entero.")
            return

        # 3. Construir Objeto
        item_manual = {
            "id_producto": None,
            "nombre_display": f"{nombre} (Manual)",
            "hc": macros.get('hidratos_g', 0),
            "gr": macros.get('grasas_g', 0),
            "sat": sat,
            "pr": macros.get('proteinas_g', 0),
            "az": macros.get('azucares_g', 0),
            "fb": macros.get('fibra_g', 0),
            "cantidad": int(cantidad) if cantidad else 1, # Default 1 si no hay cantidad
            "offset": int(offset) if offset else None,
            "es_pesado_estricto": pesado_estricto,
            "es_manual": True,
            "grupo_nombre": nombre_grupo_final
        }

        # 4. Guardar (Adaptado a tu nueva lógica de DB o Session)
        try:
            # Intento usar tu nueva clase de Queries
            if hasattr(dq, 'CarritoQueries'):
                if dq.CarritoQueries.agregar_item(item_manual):
                    st.toast(f"✅ Añadido: {nombre}")
                    # LIMPIEZA CRÍTICA: Aquí sí podemos limpiar porque es un callback
                    st.session_state.manual_macros = "" 
                    st.cache_data.clear()
                    # No hace falta rerun() aquí explícito, el callback fuerza recarga natural
                else:
                    st.error("Error al guardar en BD.")
            else:
                # FALLBACK: Si no existe la clase, guardamos en sesión como antes para que no falle
                st.session_state.carrito.append(item_manual)
                st.toast(f"✅ Añadido (Sesión): {nombre}")
                st.session_state.manual_macros = ""
        except Exception as e:
            st.error(f"Error gestionando el guardado: {e}")

    # --- UI ---
    with st.expander("🍽️ Entrada Manual", expanded=False):
        st.info("Usa esto para comidas puntuales que no quieres guardar en el catálogo.")

        # ======================================================
        # ZONA REACTIVA (FUERA DEL FORM)
        # ======================================================
        
        # 1. MACROS INTELIGENTES
        # El widget se dibuja con el valor que tenga session_state (vacío si el callback lo limpió)
        input_macros = st.text_input(
            "Macros (Smart Text):",
            placeholder="Ej: 60hc 30gr 10pr...",
            key="manual_macros"
        )
        
        # Visualización Reactiva
        macros = parsear_macros(input_macros)
        if macros['fibra_g'] is None:
            macros['fibra_g'] = 0.0  # Para evitar None en la visualización
        if input_macros:
            partes = []
            if macros.get('hidratos_g', 0) > 0: partes.append(f":blue[**{macros['hidratos_g']}g HC**]")
            if macros.get('grasas_g', 0) > 0: partes.append(f":orange[**{macros['grasas_g']}g Gr**]")
            # Uso .get() para proteger el KeyError de grasas_sat_g
            if macros.get('grasas_sat_g', 0) > 0: partes.append(f":red[{macros['grasas_sat_g']}g Sat]")
            if macros.get('proteinas_g', 0) > 0: partes.append(f":green[**{macros['proteinas_g']}g Pr**]")
            if macros.get('azucares_g', 0) > 0: partes.append(f":violet[{macros['azucares_g']}g Az]")
            if macros.get('fibra_g', 0) > 0: partes.append(f":grey[{macros['fibra_g']}g Fb]")

            if partes:
                st.markdown("✅ " + " | ".join(partes))
            else:
                st.caption("Escribe cantidades...")

        st.divider()

        # 2. SELECCIÓN DE GRUPO
        c_grupo_sel, c_grupo_new = st.columns([1.5, 1.5])
        
        # PROTECCIÓN: Si no tienes CarritoQueries, ponemos lista vacía para que no rompa la UI
        grupos_existentes = []
        if hasattr(dq, 'CarritoQueries'):
            grupos_existentes = dq.CarritoQueries.obtener_grupos_activos()
        
        opcion_nuevo = "➕ Nuevo Grupo..."
        opciones = grupos_existentes + [opcion_nuevo]
        
        seleccion_grupo = c_grupo_sel.selectbox(
            "Añadir a:", 
            options=opciones, 
            key="manual_grupo_select"
        )
        
        # Reactividad del input de nombre de grupo
        if seleccion_grupo == opcion_nuevo:
            c_grupo_new.text_input(
                "Nombre nuevo grupo:", 
                value='Comida actual', 
                key="manual_grupo_new"
            )

        # ======================================================
        # ZONA FORMULARIO (DENTRO DEL FORM)
        # ======================================================
        with st.form("form_manual_food", clear_on_submit=True):
            
            st.text_input("Nombre del plato / comida*", placeholder="Ej: Tarta de queso casera", key="manual_nombre")
            
            col_off, col_check = st.columns([1, 1])
            col_off.text_input("Offset (min):", value=None, key="manual_offset")
            col_check.text_input("Cantidad aprox (g)", value=None, key="aprox_cantidad")
            
            st.checkbox("Pesado Estricto", value=False, key="manual_pesado")

            # EL BOTÓN EJECUTA EL CALLBACK
            st.form_submit_button(
                "Añadir Manual al Carrito 🛒",
                use_container_width=True,
                on_click=guardar_manual_callback  # <--- AQUÍ OCURRE LA MAGIA
            )