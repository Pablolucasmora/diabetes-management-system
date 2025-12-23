import streamlit as st

def render_tab_catalogo():
    st.subheader("🍎 Diccionario de Categorías")
    
    accion = st.segmented_control(
        "Acción sobre el catálogo:",
        options=["Ver Categorías", "Añadir Categoría"],
        default="Ver Categorías"
    )

    if accion == "Ver Categorías":
        st.write("Estructura actual de etiquetas para el análisis:")
        # Aquí conectaremos con tu SQL: SELECT * FROM catalogo_subtipos
        st.info("Actualmente tienes 20 subtipos base cargados.")

    elif accion == "Añadir Categoría":
        with st.form("form_nuevo_subtipo"):
            nombre = st.text_input("Nombre de la nueva etiqueta (ej: Cereales)")
            tipo = st.selectbox("Grupo Raíz:", ["Alimento", "Bebida"])
            if st.form_submit_button("Registrar en DB"):
                st.success(f"Etiqueta '{nombre}' lista para ser usada en el registro.")