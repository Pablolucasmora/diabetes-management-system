import streamlit as st
from .buscador import render_buscador
from .nuevo_producto import render_nuevo_producto
from .carrito import render_carrito

def render_diario():
    col1, col2, col3 = st.columns([2, 6, 1])
    with col2:
        st.header("📝 Diario de Alimentación")
    
    st.divider()
    # Asegurar que existe el carrito en sesión
    if "carrito" not in st.session_state:
        st.session_state.carrito = []
    
    # Layout Principal: 2 columnas (Izquierda ancha, Derecha estrecha)
    col_izq, col_der = st.columns([1, 1], gap="medium")
    
    with col_izq:
        # Apilamos los componentes de entrada
        render_buscador()
        st.divider()
        render_nuevo_producto()

    with col_der:
        # Componente de resumen (sticky style visualmente)
        with st.container(border=True):
            render_carrito()