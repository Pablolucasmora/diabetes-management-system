import streamlit as st

def render_carrito():
    st.subheader("🛒 Comida actual")
    
    if not st.session_state.carrito:
        st.info("Tu bandeja está vacía.")
        return

    # 1. Listado de items
    total_hc = 0
    total_gr = 0
    total_pr = 0
    
    for i, item in enumerate(st.session_state.carrito):
        c_info, c_del = st.columns([5, 1])
        c_info.caption(f"{item['nombre']} ({item['cantidad']}g)")
        c_info.write(f"**{item['hc']}g HC** | {item['gr']}g GR | {item['pr']}g PR")
        
        if c_del.button("❌", key=f"del_{i}"):
            st.session_state.carrito.pop(i)
            st.rerun()
            
        total_hc += item['hc']
        total_gr += item['gr']
        total_pr += item['pr']
        st.divider()

    # 2. Totales
    c1, c2, c3 = st.columns(3)
    c1.metric("HC Total", f"{round(total_hc, 1)}")
    c2.metric("Grasas", f"{round(total_gr, 1)}")
    c3.metric("Proteína", f"{round(total_pr, 1)}")
    
    st.divider()
    
    # 3. Contexto de la comida
    tipo = st.selectbox("Momento:", ["Desayuno", "Almuerzo", "Comida", "Merienda", "Cena", "Snack"])
    notas_comida = st.text_area("Notas:", placeholder="Ej: Comida fuera de casa...")
    
    # 4. Guardar
    if st.button("💾 Guardar Registro", type="primary", use_container_width=True):
        st.success("¡Guardado! (Aquí conectaremos la query de guardar comida)")
        # TODO: Implementar dq.RegistroQueries.guardar_comida(...)
        st.session_state.carrito = [] 
        st.rerun()