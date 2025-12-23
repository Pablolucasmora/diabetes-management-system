import streamlit as st

def render_configuracion():
    izq, centro, der = st.columns([1, 4, 1])
    with centro:

        st.header("⚙️ Configuración")
        
        # Control segmentado principal
        perfil, diccionario_alimentos, metas = st.tabs(
            ["👤 Perfil", "🍎 Diccionario de Alimentos", "📊 Metas"]
        )


        st.divider()

        with perfil:
            st.subheader("Preferencias de Usuario")
            st.info("Aquí podrás ajustar tus datos antropométricos y sensibilidad a la insulina.")
            # Aquí irían inputs de peso, altura, etc.

        with diccionario_alimentos:
            st.subheader("Gestión de Subtipos")
            
            selected_sub = st.segmented_control(
                "Acción:",
                options=["Listar Subtipos", "Añadir Nuevo"],
                default="Listar Subtipos"
            )

            if selected_sub == "Listar Subtipos":
                st.write("Subtipos actuales en el sistema:")
                # Esto es un ejemplo, luego lo conectaremos a la DB
                col1, col2 = st.columns(2)
                col1.write("**Alimentos:**")
                col1.caption("Proteína, Legumbre, Cereal, Fruta...")
                col2.write("**Bebidas:**")
                col2.caption("Agua, Refresco, Alcohol...")

            elif selected_sub == "Añadir Nuevo":
                with st.form("nuevo_subtipo"):
                    nuevo_nombre = st.text_input("Nombre del subtipo")
                    categoria_padre = st.selectbox("Pertenece a:", ["Alimento", "Bebida"])
                    if st.form_submit_button("Guardar Subtipo"):
                        st.success(f"Subtipo '{nuevo_nombre}' añadido correctamente.")