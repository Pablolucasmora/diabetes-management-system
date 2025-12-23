import streamlit as st
from streamlit_option_menu import option_menu
from database.connection import get_db_manager

# --- IMPORTACIONES MODULARIZADAS ---

# 1. Diario: Importamos la función principal del nuevo archivo orquestador
from components.diario.main_diario import render_diario

# 2. Configuración: Importamos la función principal de configuración
from components.configuracion.main_config import render_configuracion

def main():
    # 1. Configuración de la página (Siempre lo primero)
    st.set_page_config(
        page_title="Gestión Diabetes TFG",
        layout="centered", # 'centered' es ideal para simular vista móvil
        initial_sidebar_state="collapsed"
    )
    
    # 2. Inicializar DB (Patrón Singleton)
    db = get_db_manager()
    db.init_db()

    # 3. Configuración del menú lateral
    with st.sidebar:
        opcion = option_menu(
            menu_title=None,
            options=["Diario", "Visualización", "Configuración"],
            icons=["journal-medical", "bar-chart-line", "gear"], 
            default_index=0,
            orientation="vertical"
        )

    # 4. Lógica de navegación
    if opcion == "Diario":
        # Ahora llamamos a la nueva estructura modular
        render_diario()

    elif opcion == "Visualización":
        st.header("📊 Visualización Histórica")
        st.info("Conexión con datos de glucemia en desarrollo.")

    elif opcion == "Configuración":
        # Llamamos al gestor de pestañas de configuración
        render_configuracion()

if __name__ == "__main__":
    main()