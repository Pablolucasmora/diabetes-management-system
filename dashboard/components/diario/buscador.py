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
            
            c1, c2 = st.columns([2, 1])
            cantidad_str = c1.text_input("Cantidad (g/ml)", key=f"input_cant_{id_a_mostrar}")
            
            if c2.button("Añadir ➕", key=f"btn_add_{id_a_mostrar}", use_container_width=True):
                try:
                    cantidad = int(cantidad_str)
                    if cantidad > 0:
                        factor = cantidad / 100.0
                        # Añadimos al estado global 'carrito'
                        st.session_state.carrito.append({
                            "nombre": producto.nombre,
                            "cantidad": cantidad,
                            "hc": round(producto.hidratos_g * factor, 2),
                            "gr": round(producto.grasas_g * factor, 2),
                            "pr": round(producto.proteinas_g * factor, 2),
                            "id_producto": producto.id_producto
                        })
                        st.toast(f"✅ Añadido: {producto.nombre}")
                        st.session_state.id_recien_creado = None
                        st.rerun()
                    else:
                        st.warning("La cantidad debe ser mayor a 0")
                except ValueError:
                    st.error("Introduce un número entero")