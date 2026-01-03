import streamlit as st
import database.queries as dq

def render_buscador():
    st.subheader("🔍 Añadir Alimentos")

    # Inicialización de estado
    if "id_recien_creado" not in st.session_state:
        st.session_state.id_recien_creado = None

    # 1. Cargar catálogo (Cacheado para velocidad)
    @st.cache_data
    def cargar_catalogo():
        return dq.CatalogoQueries.obtener_todos_nombres_id()

    catalogo = cargar_catalogo()
    # Diccionario para buscar: "Manzana (Marca)" -> ID 5
    opciones = {f"{r['nombre']} ({r['marca']})": r['id_producto'] for r in catalogo}

    # 2. Widget de búsqueda
    seleccion = st.selectbox(
        "Busca o selecciona un alimento:",
        options=list(opciones.keys()),
        index=None, 
        placeholder="Escribe para buscar...",
        key="buscador_principal"
    )

    # 3. Lógica de selección (Prioridad: Buscador > Recién Creado)
    id_a_mostrar = None
    if seleccion:
        id_a_mostrar = opciones[seleccion]
        st.session_state.id_recien_creado = None 
    elif st.session_state.id_recien_creado:
        id_a_mostrar = st.session_state.id_recien_creado

    # 4. Panel de "Añadir al carrito"
    if id_a_mostrar:
        producto = dq.CatalogoQueries.obtener_producto_por_id(id_a_mostrar)
        
        if producto:
            # Mostramos info visual
            color = "green" if st.session_state.id_recien_creado else "blue"
            st.markdown(f":{color}[**Seleccionado:** {producto.nombre} | {producto.hidratos_g}g HC / 100g]")
            
            # --- NUEVA LÓGICA DE CANTIDADES ---
            
            # 1. Definimos el valor por defecto
            # Si tiene ración definida en BD, la usamos. Si no, ponemos 100g por defecto.
            valor_base = float(producto.porcion_default_g) if (producto.porcion_default_g and producto.porcion_default_g > 0) else None
            
            # 2. Dividimos el espacio en 3 columnas: [Ración] [Multiplicador] [Botón]
            c_cant, c_mult, c_btn = st.columns([1.5, 1, 1.2], gap="small")
            
            # Input A: Tamaño de la ración (Editable)
            racion_input = c_cant.text_input(
                "Ración (g/ml)", 
                value=str(valor_base) if valor_base else None, 
                key=f"input_base_{id_a_mostrar}"
            )
            
            # Input B: Veces (Multiplicador)
            veces_input = c_mult.text_input(
                "Nº Veces", 
                value="1",
                key=f"input_mult_{id_a_mostrar}"
            )
            
            # Cálculo final
            cantidad_final = float(racion_input) * float(veces_input) if racion_input and veces_input else 0

            # Botón con feedback visual de la cantidad total
            texto_boton = f"Añadir ({int(cantidad_final)}g) ➕"

            c1, c2 = st.columns([2, 1])
            offset = c1.text_input("Offset (min)", key=f"input_offset_{id_a_mostrar}")
            pesado_estricto = c2.checkbox("Pesado Estricto", value=True, key=f"chk_pesado_{id_a_mostrar}")

            # --- SELECCIÓN DE GRUPO ---
            st.write("**Opciones de Agrupación**")
            c_grupo, c_botones = st.columns([2, 1])
            
            # 1. Recuperamos grupos existentes
            grupos_existentes = dq.CarritoQueries.obtener_grupos_activos()
            
            # 2. Lógica del Widget: Selectbox + opción "Nuevo"
            opcion_nuevo = "➕ Nuevo Grupo..."
            opciones = grupos_existentes + [opcion_nuevo]
            
            # Si no hay grupos, seleccionamos "Nuevo" por defecto. Si hay, el primero (el más reciente).
            idx_default = 0 if grupos_existentes else 0
            
            seleccion_grupo = c_grupo.selectbox(
                "Añadir a:", 
                options=opciones, 
                index=idx_default,
                key=f"sel_grupo_{id_a_mostrar}"
            )
            
            nombre_grupo_final = seleccion_grupo
            
            # Si elige crear nuevo, mostramos el input de texto
            if seleccion_grupo == opcion_nuevo:
                nombre_grupo_final = c_grupo.text_input(
                    "Nombre del nuevo grupo:", 
                    value="Comida", 
                    key=f"txt_grupo_{id_a_mostrar}"
                )

            if st.button(texto_boton, key=f"btn_add_{id_a_mostrar}", use_container_width=True):
                try:
                    cantidad = int(cantidad_final)
                    if cantidad > 0:
                        factor = cantidad / 100.0

                        item_dict = {
                            "nombre_display": producto.nombre,
                            "cantidad": cantidad,
                            "grupo_nombre": nombre_grupo_final,
                            "hc": round(producto.hidratos_g * factor, 2),
                            "gr": round(producto.grasas_g * factor, 2),
                            "pr": round(producto.proteinas_g * factor, 2),
                            "fb": round(producto.fibra_g * factor, 2),
                            "az": round(producto.azucares_g * factor, 2),
                            "sat": round(producto.grasas_sat_g * factor, 2),
                            "id_producto": producto.id_producto,
                            "offset": int(offset) if offset else None,
                            "es_manual": False,
                            "es_pesado_estricto": pesado_estricto,

                        }
                        dq.CarritoQueries.agregar_item(item_dict) 
                        st.toast(f"✅ Añadido: {producto.nombre}")
                        st.session_state.id_recien_creado = None
                        st.rerun()
                    else:
                        st.warning("La cantidad debe ser mayor a 0")
                except ValueError:
                    st.error("Introduce un número entero")