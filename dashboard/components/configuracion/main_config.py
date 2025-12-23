import streamlit as st
from .usuario import render_tab_usuario
from .catalogo import render_tab_catalogo

def render_configuracion():
    st.header("⚙️ Parámetros del Sistema")
    
    tab_usr, tab_cat = st.tabs(["👤 Datos de Usuario", "🏷️ Etiquetas de Catálogo"])

    with tab_usr:
        render_tab_usuario()

    with tab_cat:
        render_tab_catalogo()