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
    # Diccionario maestro
    opciones = {f"{r['nombre']} ({r['marca']})": r['id_producto'] for r in catalogo}

    # ======================================================
    # 2. WIDGET DE BÚSQUEDA (MODIFICADO PARA MÓVIL)
    # ======================================================
    # Usamos columnas para poner el icono y dar sensación de barra de búsqueda
    col_search, col_icon = st.columns([5, 1])
    
    # Este input SI despliega el teclado del móvil correctamente
    filtro_usuario = col_search.text_input(
        "Filtro rápido:", 
        placeholder="Escribe para buscar (ej: arroz...)", 
        label_visibility="collapsed",
        key="filtro_texto_movil"
    )
    col_icon.write("🔎")

    # Filtramos la lista en Python antes de pasársela al selectbox
    if filtro_usuario:
        lista_filtrada = [k for k in opciones.keys() if filtro_usuario.lower() in k.lower()]
    else:
        # Si no hay texto, mostramos todo (o lista vacía si prefieres limpiar pantalla)
        lista_filtrada = list(opciones.keys())

    # El selectbox ahora carga ligero y no se traba
    seleccion = st.selectbox(
        "Selecciona el resultado:",
        options=lista_filtrada,
        index=None, 
        placeholder="Elige de la lista...",
        key="buscador_final_filtrado" # Key distinta para no chocar
    )
    # ======================================================

    # 3. Lógica de selección
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
            # Info visual
            color = "green" if st.session_state.id_recien_creado else "blue"
            st.markdown(f":{color}[**Seleccionado:** {producto.nombre} | {producto.hidratos_g}g HC / 100g]")
            
            # --- LÓGICA DE CANTIDADES Y UNIDADES ---
            
            # 1. Valor por defecto (Si la BD tiene porción definida, la usamos)
            valor_base = float(producto.porcion_default_g) if (producto.porcion_default_g and producto.porcion_default_g > 0) else None
            
            c_cant, c_mult, c_btn = st.columns([1.5, 1, 1.2], gap="small")
            
            # Input A: Tamaño de la ración (Editable)
            racion_input = c_cant.text_input(
                "Ración (g/ml)", 
                value=str(valor_base) if valor_base else "100", # Por defecto 100 si no hay dato
                key=f"input_base_{id_a_mostrar}"
            )
            
            # Input B: Veces (Unidades)
            veces_val = c_mult.number_input(
                "Nº Veces", 
                min_value=0.1, 
                value=1.0, 
                step=0.5, 
                key=f"input_mult_{id_a_mostrar}"
            )
            
            # Cálculo final seguro
            try:
                racion_val = float(racion_input) if racion_input else 0
                veces_val = float(veces_val) if veces_val else 1
                cantidad_final = racion_val * veces_val
            except ValueError:
                cantidad_final = 0

            # Botón con feedback
            texto_boton = f"Añadir ({int(cantidad_final)}g) ➕"

            pesado_estricto = st.checkbox("Pesado Estricto", value=True, key=f"chk_pesado_{id_a_mostrar}")

            # --- SELECCIÓN DE GRUPO ---
            st.write("**Opciones de Agrupación**")
            c_grupo, c_botones = st.columns([2, 1])
            
            grupos_existentes = dq.CarritoQueries.obtener_grupos_activos()
            opcion_nuevo = "➕ Nuevo Grupo..."
            opciones_grupo = grupos_existentes + [opcion_nuevo]
            idx_default = 0
            
            seleccion_grupo = c_grupo.selectbox(
                "Añadir a:", 
                options=opciones_grupo, 
                index=idx_default,
                key=f"sel_grupo_{id_a_mostrar}"
            )
            
            nombre_grupo_final = seleccion_grupo
            if seleccion_grupo == opcion_nuevo:
                nombre_grupo_final = c_grupo.text_input(
                    "Nombre del nuevo grupo:", 
                    value="Comida", 
                    key=f"txt_grupo_{id_a_mostrar}"
                )

            # --- ACCIÓN DE GUARDADO ---
            if st.button(texto_boton, key=f"btn_add_{id_a_mostrar}", use_container_width=True):
                try:
                    cantidad = int(cantidad_final)
                    unidades = float(veces_val) # Guardamos el número de veces como unidades

                    if cantidad > 0:
                        factor = cantidad / 100.0
                        
                        # Cálculo seguro de fibra (evitando TypeError)
                        fibra_final = None
                        if producto.fibra_g is not None and producto.fibra_g != "":
                            try:
                                fibra_final = round(float(producto.fibra_g) * factor, 2)
                            except ValueError:
                                fibra_final = None
                        item_dict = {
                            "nombre_display": producto.nombre,
                            "cantidad": cantidad,
                            "unidades": unidades,  # <--- AQUÍ GUARDAMOS LAS UNIDADES
                            "grupo_nombre": nombre_grupo_final,
                            
                            # Macros seguros con float()
                            "hc": round(float(producto.hidratos_g) * factor, 2),
                            "gr": round(float(producto.grasas_g) * factor, 2),
                            "pr": round(float(producto.proteinas_g) * factor, 2),
                            "fb": fibra_final, # Usamos el cálculo protegido de arriba
                            "az": round(float(producto.azucares_g) * factor, 2),
                            "sat": round(float(producto.grasas_sat_g) * factor, 2),
                            
                            "id_producto": producto.id_producto,
                            "offset": None,
                            "es_manual": False,
                            "es_pesado_estricto": pesado_estricto,
                        }
                        
                        dq.CarritoQueries.agregar_item(item_dict) 
                        # Mensaje bonito formateando el float (quita el .0 si es entero)
                        uni_str = f"{unidades:g}" 
                        st.toast(f"✅ Añadido: {producto.nombre} (x{uni_str})")
                        
                        # Limpiamos selección
                        st.session_state.id_recien_creado = None
                        st.rerun()
                    else:
                        st.warning("La cantidad debe ser mayor a 0")
                except ValueError as e:
                    st.error(f"Error en los datos: {e}")