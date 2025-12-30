import streamlit as st
import database.queries as dq


def calcular_calidad_registro(carrito):
    """Calcula qué porcentaje de los hidratos vienen de alimentos pesados."""
    if not carrito: return "N/A", "grey"
    
    total_hc = sum(item['hc'] for item in carrito)
    if total_hc == 0: return "Sin Hidratos", "blue"
    
    hc_pesados = sum(item['hc'] for item in carrito if item.get('es_pesado_estricto', True))
    
    ratio = hc_pesados / total_hc
    
    if ratio == 1.0:
        return "🥇 Registro Perfecto (100% Pesado)", "green"
    elif ratio >= 0.8:
        return "🥈 Registro Muy Fiable", "blue"
    elif ratio >= 0.5:
        return "⚠️ Registro Mixto (Estimado)", "orange"
    else:
        return "🎲 Registro 'A Ojo' (Poca fiabilidad)", "red"


def render_carrito():
    st.subheader("🛒 Comida actual")
    
    carrito = dq.CarritoQueries.obtener_carrito()

    if not carrito:
        st.info("Tu bandeja está vacía.")
        return

    # 1. MOSTRAR CALIDAD DEL REGISTRO (Tu idea del semáforo)
    mensaje_calidad, color_calidad = calcular_calidad_registro(carrito)
    st.caption("Calidad de los datos:")
    st.markdown(f":{color_calidad}[**{mensaje_calidad}**]")
    st.progress(sum(item['hc'] for item in carrito if item.get('es_pesado_estricto', True)) / (sum(item['hc'] for item in carrito) + 0.001))
    
    st.divider()

    # 1. Listado de items
    total_hc = 0
    total_gr = 0
    total_pr = 0
    total_fb = 0
    total_az = 0
    total_sat = 0
    
    for i, item in enumerate(carrito):
        c_info, c_del = st.columns([5, 1])
        c_info.caption(f"{item['nombre_display']} ({item['cantidad']}g)")
        c_info.caption(f"Offset: {item.get('offset', 0)} min")
        c_info.write(f"**{item['hc']}g HC** | {item['gr']}g GR | {item['pr']}g PR | {item['fb']}g FB")
        
        if c_del.button("❌", key=f"del_{i}"):
            dq.CarritoQueries.eliminar_item(item['id_item'])
            st.rerun()
            
        total_hc += item.get('hc', 0)
        total_gr += item.get('gr', 0)
        total_pr += item.get('pr', 0)
        total_fb += item.get('fb', 0)
        total_az += item.get('az', 0)
        total_sat += item.get('sat', 0)
        st.divider()

    # 2. Totales
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("HC Total", f"{round(total_hc, 1)}")
    c2.metric("Grasas", f"{round(total_gr, 1)}")
    c3.metric("Proteína", f"{round(total_pr, 1)}")
    c4.metric("Fibra", f"{round(total_fb, 1)}")

    st.divider()
    
    # 3. Contexto de la comida
    tipo = st.selectbox("Momento:", ["Desayuno", "Almuerzo", "Comida", "Merienda", "Cena", "Snack"])
    notas_comida = st.text_area("Notas:", placeholder="Ej: Comida fuera de casa...")
    
    # 4. Guardar
    if st.button("💾 Guardar Registro", type="primary", use_container_width=True):
        st.success("¡Guardado! (Aquí conectaremos la query de guardar comida)")
        # TODO: Implementar dq.RegistroQueries.guardar_comida(...)
        dq.CarritoQueries.vaciar_carrito()
        st.rerun()