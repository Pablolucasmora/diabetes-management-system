import streamlit as st
from streamlit_option_menu import option_menu
from database.connection import init_db
# Importamos la función que acabamos de completar en el componente
import components.registro_comida as rc
import components.configuracion as config

def main():
    # 1. Configuración de la página (Siempre lo primero)
    st.set_page_config(
    page_title="Mi App Móvil",
    layout="centered", # 'centered' suele ser mejor para móviles que 'wide'
    initial_sidebar_state="collapsed" # Colapsa la barra lateral para ganar espacio
    )
    
    # 2. Inicializar DB (Crea tablas si no existen)
    init_db()

    # 1. Configuración de la barra lateral
    with st.sidebar:
        opcion = option_menu(
            menu_title=None,       # Título del menú
            options=["Imputación de Datos", "Visualización Histórica", "Configuración"], # Textos
            icons=["box-arrow-in-down", "bar-chart-line", "gear"], # Iconos de Bootstrap
            menu_icon="cast",                  # Icono del título
            default_index=0,                   # Opción por defecto
            orientation="vertical"             # Orientación del menú
        )

    # 2. Lógica de navegación
    if opcion == "Imputación de Datos":
        rc.render_seccion_principal_registro()

    elif opcion == "Visualización Histórica":
        st.header("📊 Visualización de los últimos días")
        st.info("Esta sección está en desarrollo. Aquí conectaremos con los datos de LibreView.")

    elif opcion == "Configuración":
        config.render_configuracion()




if __name__ == "__main__":
    main()