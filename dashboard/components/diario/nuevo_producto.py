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
        'hidratos': 'hidratos_g', 'hc': 'hidratos_g', 'carbos': 'hidratos_g',
        'azucar': 'azucares_g', 'azucares': 'azucares_g', 'az': 'azucares_g',
        'proteinas': 'proteinas_g', 'proteina': 'proteinas_g', 'pr': 'proteinas_g', 'pro': 'proteinas_g',
        'grasas': 'grasas_g', 'grasa': 'grasas_g', 'gr': 'grasas_g',
        'saturadas': 'grasas_sat_g', 'sat': 'grasas_sat_g', 'st': 'grasas_sat_g', 'gs': 'grasas_sat_g', # <--- NUEVOS
        'fibra': 'fibra_g', 'fb': 'fibra_g'
    }
    
    valores = {
        'hidratos_g': 0.0, 'azucares_g': 0.0, 'proteinas_g': 0.0, 
        'fibra_g': 0.0, 'grasas_g': 0.0, 'grasas_sat_g': 0.0
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

    with st.expander("➕ Crear producto nuevo", expanded=False):

        # ======================================================
        # PASO 1 — MACROS (REACTIVO)
        # ======================================================
        st.info("💡 **Paso 1:** Escribe los macros y pulsa ENTER.")

        input_macros = st.text_input(
            "Macros (Escritura inteligente)",
            placeholder="Ej: 30hc, 12az, 20pr, 10 grasas...",
            key="input_smart_macros"
        )

        macros = parsear_macros(input_macros)

        if input_macros:
            partes = []
            if macros['hidratos_g'] > 0:
                partes.append(f":blue[**{macros['hidratos_g']}g HC**]")
            if macros['azucares_g'] > 0:
                partes.append(f":violet[{macros['azucares_g']}g Azúcar]")
            if macros['proteinas_g'] > 0:
                partes.append(f":green[**{macros['proteinas_g']}g Prot**]")
            if macros['grasas_g'] > 0:
                partes.append(f":orange[**{macros['grasas_g']}g Grasas**]")
            if macros['fibra_g'] > 0:
                partes.append(f":grey[{macros['fibra_g']}g Fibra]")
            if macros['grasas_sat_g'] > 0:
                partes.append(f":red[{macros['grasas_sat_g']}g Grasas Sat.]")

            if partes:
                st.markdown("✅ **Detectado:** " + " | ".join(partes))
            else:
                st.caption("⚠️ Formato no reconocido.")

        st.divider()

        # ======================================================
        # PASO 2 — CATEGORÍA (REACTIVO)
        # ======================================================
        st.write("**Paso 2:** Selecciona la categoría")

        categoria = st.selectbox(
            "Categoría*",
            ["Alimento", "Bebida", "Suplemento"],
            key="categoria_producto"
        )

        st.divider()

        # ======================================================
        # PASO 3 — FORMULARIO (NO REACTIVO)
        # ======================================================
        st.write("**Paso 3:** Completa los datos y guarda")

        with st.form("form_alta_completa", clear_on_submit=True):

            col1, col2 = st.columns(2)
            nombre = col1.text_input("Nombre*")
            marca = col2.text_input("Marca")

            subtipo = st.text_input("Subtipo (ej: Pasta, Refresco...)")

            c1, c2 = st.columns(2)
            nutriscore = c1.selectbox(
                "NutriScore",
                ["A", "B", "C", "D", "E", "Desconocido"],
                index=5
            )
            nova = c2.selectbox(
                "NOVA",
                [1, 2, 3, 4, "Desconocido"],
                index=4
            )

            # ----------------------------------------------
            # CAMPOS DINÁMICOS SEGÚN CATEGORÍA
            # ----------------------------------------------
            grad, caf, gas = None, None, False

            if categoria == "Bebida":
                b1, b2, b3 = st.columns(3)
                grad = b1.text_input("Grad. %")
                caf = b2.text_input("Cafeína (mg)")
                gas = b3.checkbox("¿Gas?", value=False)

            porcion_default_g = st.text_input("Porción por defecto (g/ml)", value="")

            notas_prod = st.text_area("Notas")

            submitted = st.form_submit_button(
                "💾 Guardar en Catálogo",
                type="primary"
            )

            if submitted:

                if not nombre:
                    st.error("❌ El nombre es obligatorio")
                    st.stop()

                try:
                    nuevo = ProductoModel(
                        nombre=nombre,
                        marca=marca if marca else None,
                        categoria=categoria,
                        subtipo=subtipo,

                        hidratos_g=macros['hidratos_g'],
                        azucares_g=macros['azucares_g'],
                        proteinas_g=macros['proteinas_g'],
                        fibra_g=macros['fibra_g'],
                        grasas_g=macros['grasas_g'],
                        grasas_sat_g=macros['grasas_sat_g'],

                        graduacion_pct=float(grad or 0),
                        cafeina_mg=float(caf or 0),
                        es_gas=gas,
                        porcion_default_g=int(porcion_default_g) if porcion_default_g else None,
                        notas=notas_prod,
                        nutriscore=nutriscore,
                        nova=nova
                    )

                    nuevo_id = dq.CatalogoQueries.insertar_producto(nuevo)

                    if nuevo_id:
                        st.success(f"✅ **{nombre}** guardado correctamente")
                        st.session_state.id_recien_creado = nuevo_id
                        st.cache_data.clear()
                        st.rerun()

                except Exception as e:
                    st.error(f"🚨 Error al guardar: {e}")

def render_custom_food_entry():
    """
    Entrada manual con:
    - Smart macros reactivos
    - Formulario estable con autoreset
    """
    with st.expander("🍽️ Entrada Manual"):
        st.info("Usa esto para comidas puntuales que no quieres guardar en el catálogo.")

        # ======================================================
        # PASO 1 — SMART MACROS (REACTIVO, FUERA DEL FORM)
        # ======================================================
        input_macros = st.text_input(
            "Macros (Smart Text):",
            placeholder="Ej: 60hc 30gr 10pr...",
            key="manual_macros"
        )

        macros = parsear_macros(input_macros)

        if input_macros:
            partes = []
            if macros['hidratos_g'] > 0:
                partes.append(f":blue[**{macros['hidratos_g']}g HC**]")
            if macros['grasas_g'] > 0:
                partes.append(f":orange[**{macros['grasas_g']}g Gr**]")
            if macros['proteinas_g'] > 0:
                partes.append(f":green[**{macros['proteinas_g']}g Pr**]")
            if macros['azucares_g'] > 0:
                partes.append(f":violet[{macros['azucares_g']}g Az]")
            if macros['fibra_g'] > 0:
                partes.append(f":grey[{macros['fibra_g']}g Fb]")
            if macros['grasas_sat_g'] > 0:
                partes.append(f":red[{macros['grasas_sat_g']}g Sat]")

            if partes:
                st.markdown("✅ " + " | ".join(partes))
            else:
                st.caption("Escribe cantidades, ej: `45hc`")

        st.divider()

        # ======================================================
        # PASO 2 — FORMULARIO (NO REACTIVO, AUTO RESET)
        # ======================================================
        with st.form("form_manual_food", clear_on_submit=True):

            nombre = st.text_input(
                "Nombre del plato / comida*",
                placeholder="Ej: Tarta de queso casera",
                key="manual_nombre"
            )

            st.write("**Opciones Extra**")
            col_off, col_check = st.columns([2, 1])

            offset = col_off.text_input(
                "Minutos espera (Offset):",
                help="Positivo: esperas antes de comer. Negativo: comes antes.",
                key="manual_offset"
            )

            pesado_estricto = col_check.checkbox(
                "Pesado Estricto",
                key="manual_pesado"
            )

            submitted = st.form_submit_button(
                "Añadir Manual al Carrito 🛒",
                use_container_width=True
            )

            if submitted:
                tiene_macros = (
                    macros['hidratos_g'] > 0 or
                    macros['grasas_g'] > 0 or
                    macros['proteinas_g'] > 0 or
                    macros['azucares_g'] > 0 or
                    macros['fibra_g'] > 0 or
                    macros['grasas_sat_g'] > 0
                )

                if not nombre or not tiene_macros:
                    st.error("Debes poner un nombre y algún valor nutricional.")
                    st.stop()

                item_manual = {
                    "nombre": f"{nombre} (Manual)",
                    "cantidad": 1,
                    "hc": macros['hidratos_g'],
                    "gr": macros['grasas_g'],
                    "pr": macros['proteinas_g'],
                    "az": macros['azucares_g'],
                    "fb": macros['fibra_g'],
                    "sat": macros['grasas_sat_g'],
                    "id_producto": None,
                    "offset": int(offset) if offset else None,
                    "es_manual": True,
                    "es_pesado_estricto": pesado_estricto,
                }
                dq.CarritoQueries.agregar_item(item_manual)
                st.success(f"Añadido: {nombre}")
                st.rerun()
