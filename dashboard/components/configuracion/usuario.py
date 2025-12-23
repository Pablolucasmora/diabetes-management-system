import streamlit as st

def render_tab_usuario():
    st.subheader("👤 Perfil de Sujeto")
    st.caption("Estos datos son variables independientes para el análisis posterior.")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        peso = c1.number_input("Peso actual (kg)", value=70.0, step=0.1)
        sensibilidad = c2.number_input("Sensibilidad Insulina (Factor)", value=1.0)
        
    if st.button("Guardar Perfil"):
        st.success("Variables de sujeto actualizadas.")