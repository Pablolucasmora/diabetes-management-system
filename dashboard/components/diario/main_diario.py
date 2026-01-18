import streamlit as st
from .buscador import render_buscador
from .nuevo_producto import render_nuevo_producto, render_custom_food_entry
from .carrito import render_carrito
from .panel_control import render_panel_control_z

def render_diario():
        # Asegurar que existe el carrito en sesión
    if "carrito" not in st.session_state:
        st.session_state.carrito = []
    
    # Layout Principal: 2 columnas (Izquierda ancha, Derecha estrecha)
    col_izq, col_der = st.columns([1, 1], gap="medium")
    
    with col_izq:
        # Apilamos los componentes de entrada
        render_buscador()
        st.divider()
        render_custom_food_entry()
        st.divider()
        with st.expander(label ="🛒 Tu Bandeja de Entrada", expanded=False):
            render_carrito()
        st.divider()
        render_nuevo_producto()

    st.divider()

    col1, col2, col3 = st.columns([3, 6, 3])
    with col2:
        st.header("📝 Diario de Alimentación")

        render_panel_control_z()
