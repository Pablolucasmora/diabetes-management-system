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
        'fibra': 'fibra_g', 'fb': 'fibra_g'
    }
    
    valores = {
        'hidratos_g': 0.0, 'azucares_g': 0.0, 'proteinas_g': 0.0, 
        'fibra_g': 0.0, 'grasas_g': 0.0
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
    with st.expander("➕ Crear producto nuevo"):
        
        # --- ZONA INTERACTIVA (FUERA DEL FORMULARIO) ---
        # Al estar fuera, pulsar ENTER aquí recarga la página (calcula) pero NO guarda en BD.
        st.info("💡 **Paso 1:** Escribe los macros aquí y pulsa ENTER para validarlos.")
        
        input_macros = st.text_input(
            "Macros (Escritura inteligente):",
            placeholder="Ej: 30hc, 12az, 20pr, 10 grasas...",
            key="input_smart_macros" 
        )
        
        # Procesamos inmediatamente
        macros_detectados = parsear_macros(input_macros)
        
        # Feedback visual inmediato
        if input_macros:
            partes_mensaje = []
            if macros_detectados['hidratos_g'] > 0:
                partes_mensaje.append(f":blue[**{macros_detectados['hidratos_g']}g HC**]")
            if macros_detectados['azucares_g'] > 0:
                partes_mensaje.append(f":violet[{macros_detectados['azucares_g']}g Azúcar]")
            if macros_detectados['proteinas_g'] > 0:
                partes_mensaje.append(f":green[**{macros_detectados['proteinas_g']}g Prot**]")
            if macros_detectados['grasas_g'] > 0:
                partes_mensaje.append(f":orange[**{macros_detectados['grasas_g']}g Grasas**]")
            if macros_detectados['fibra_g'] > 0:
                partes_mensaje.append(f":grey[{macros_detectados['fibra_g']}g Fibra]")

            if partes_mensaje:
                st.markdown("✅ **Detectado:** " + " | ".join(partes_mensaje))
            else:
                st.caption("⚠️ No detecto cantidades. Usa: '10g hc' o '15 grasas'.")
        
        st.divider()

        # --- ZONA DE GUARDADO (DENTRO DEL FORMULARIO) ---
        # Todo lo que está aquí dentro solo se procesa al dar al botón "Guardar"
        with st.form("form_alta_completa", clear_on_submit=True):
            st.write("**Paso 2:** Completa los detalles y guarda.")
            
            categoria = st.selectbox("Categoría*", ["Alimento", "Bebida", "Suplemento"], key="new_cat")
            
            col1, col2 = st.columns(2)
            nombre = col1.text_input("Nombre*")
            marca = col2.text_input("Marca")
            subtipo = st.text_input("Subtipo (ej: Pasta, Refresco...)")

            # Valoraciones
            c_nutri, c_nova = st.columns(2)
            nutriscore = c_nutri.selectbox("NutriScore", ["A", "B", "C", "D", "E", "Desconocido"], index=5)
            nova = c_nova.selectbox("NOVA", [1, 2, 3, 4, 'Desconocido'], index=4)

            # Campos extra para Bebidas
            grad, caf, gas = 0.0, 0.0, False
            if categoria == "Bebida": # Nota: Al estar dentro del form, esto no se actualizará al instante si cambias categoría.
                # Si necesitas que 'Bebida' muestre campos dinámicos al instante, 
                # 'categoria' también debería salir fuera del form.
                st.write("**Detalles de Bebida**")
                b1, b2, b3 = st.columns(3)
                grad = b1.number_input("Graduación %", step=0.1)
                caf = b2.number_input("Cafeína mg", step=1.0)
                gas = b3.checkbox("¿Tiene gas?")
            
            notas_prod = st.text_area("Notas")

            # BOTÓN FINAL
            if st.form_submit_button("💾 Guardar en Catálogo", type="primary"):
                if nombre:
                    try:
                        nuevo = ProductoModel(
                            nombre=nombre, 
                            marca=marca, 
                            categoria=categoria, 
                            subtipo=subtipo,
                            # Usamos los macros que calculamos fuera del form
                            hidratos_g=macros_detectados['hidratos_g'],
                            azucares_g=macros_detectados['azucares_g'],
                            proteinas_g=macros_detectados['proteinas_g'],
                            fibra_g=macros_detectados['fibra_g'],
                            grasas_g=macros_detectados['grasas_g'],
                            
                            graduacion_pct=float(grad), 
                            cafeina_mg=float(caf), 
                            es_gas=gas, 
                            notas=notas_prod, 
                            nutriscore=nutriscore, 
                            nova=nova
                        )
                        
                        nuevo_id = dq.CatalogoQueries.insertar_producto(nuevo)
                        
                        if nuevo_id:
                            st.success(f"¡{nombre} guardado!")
                            st.session_state.id_recien_creado = nuevo_id
                            st.cache_data.clear()
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
                else:
                    st.error("El nombre es obligatorio")