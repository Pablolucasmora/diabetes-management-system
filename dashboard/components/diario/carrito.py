import streamlit as st
import database.queries as dq
from datetime import datetime, timedelta


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
    st.subheader("🛒 Bandeja de Entrada")
    
    # 1. Cargar datos de la BD
    carrito = dq.CarritoQueries.obtener_carrito()

    if not carrito:
        st.info("Tu bandeja está vacía.")
        return

    # 2. AGRUPAR ITEMS POR 'grupo_nombre'
    # Creamos un diccionario: { "Desayuno": [item1, item2], "Snack": [item3] }
    grupos = {}
    for item in carrito:
        gn = item.get('grupo_nombre', 'Comida Actual') # Valor por defecto si es antiguo
        if gn not in grupos: grupos[gn] = []
        grupos[gn].append(item)

    # 3. RENDERIZAR CADA GRUPO EN SU PROPIO EXPANDER
    for nombre_grupo, alimentos in grupos.items():
        
        # Calculamos HC total del grupo para el título
        hc_grupo = sum(item['hc'] for item in alimentos)
        
        # Usamos expanded=True para que se vean abiertos por defecto
        with st.expander(f"🍽️ {nombre_grupo} ({round(hc_grupo, 1)}g HC)", expanded=True):
            
            # --- A. CONTEXTO DE LA COMIDA (Hora y Tipo) ---
            # Al estar dentro del bucle, usamos keys únicas basadas en el nombre del grupo
            c_hora, c_tipo = st.columns(2)
            
            hora_ingesta = c_hora.time_input(
                "Hora Inicio", 
                value=datetime.now().time(), 
                key=f"time_{nombre_grupo}"
            )
            
            tipo_comida = c_tipo.selectbox(
                "Momento", 
                ["Desayuno", "Almuerzo", "Comida", "Merienda", "Cena", "Snack", "Rescate"],
                index=2, # Por defecto "Comida", puedes cambiarlo
                key=f"type_{nombre_grupo}"
            )

            # Preparamos la fecha base para calcular inyecciones
            dt_ingesta = datetime.combine(datetime.now().date(), hora_ingesta)
            
            st.divider()

            # --- B. LISTADO DE ITEMS ---
            # Variables para totales del grupo
            t_hc, t_gr, t_pr, t_fb, t_az, t_sat = 0, 0, 0, 0, 0, 0

            for i, item in enumerate(alimentos):
                c_info, c_del = st.columns([5, 1])
                
                # 1. Cálculos visuales
                offset = item.get('offset', 0)

                # 2. Lógica blindada: Solo calculamos si hay un dato real
                txt_offset = "Offset None"
                
                if offset is not None:
                    # Solo hacemos la resta si offset es un número (int/float)
                    try:
                        val_offset = float(offset)
                        if val_offset != 0:
                            dt_inyeccion = dt_ingesta - timedelta(minutes=val_offset)
                            signo = "-" if val_offset > 0 else "+"
                            txt_offset = f" \n {signo}{int(val_offset)}min (~{dt_inyeccion.strftime('%H:%M')})"
                    except Exception as e:
                        print(e) # Si por lo que sea falla, no mostramos offset y ya está
                
                # Texto de grasas saturadas si existen
                val_sat = item.get('grasas_sat_g', 0)

                # 2. Renderizado del Item
                nombre_display = item.get('nombre_display', 'Desconocido')
                c_info.markdown(f"**{nombre_display}** ({item['cantidad']}g)")
                c_info.caption(txt_offset)
                c_info.caption(
                    f"{item['hc']}g HC ({item['az']:.1f}g Az) | "
                    f"{item['gr']}g GR ({val_sat:.1f}g sat) | "
                    f"{item['pr']}g PR | "
                    f"{item['fb']}g FB "
                )
                
                # 3. Botón de Eliminar Item
                if c_del.button("❌", key=f"del_{item['id_item']}"):
                    dq.CarritoQueries.eliminar_item(item['id_item'])
                    st.rerun()

                # 4. Acumular totales
                t_hc += item.get('hc', 0)
                t_gr += item.get('gr', 0)
                t_pr += item.get('pr', 0)
                t_fb += item.get('fb', 0)
                t_az += item.get('az', 0)
                t_sat += item.get('grasas_sat_g', 0)
                
                st.divider()

            # --- C. TOTALES DEL GRUPO ---
            # Fila 1: Los Macros Principales (HC y Grasas)
            m1, m2 = st.columns(2)
            m1.metric("HC Total", f"{round(t_hc, 1)}")
            m2.metric("Grasas", f"{round(t_gr, 1)}", delta=f"{round(t_sat, 1)} Sat" if t_sat > 0 else None, delta_color="inverse")
            
            # Fila 2: Los Secundarios (Proteína y Fibra)
            m3, m4 = st.columns(2)
            m3.metric("Proteína", f"{round(t_pr, 1)}")
            m4.metric("Fibra", f"{round(t_fb, 1)}")

            # --- D. NOTAS Y GUARDADO ---
            notas = st.text_area("Notas:", placeholder="Ej: Comida fuera de casa...", key=f"notes_{nombre_grupo}")
            
            if st.button(f"💾 Registrar {nombre_grupo}", type="primary", use_container_width=True, key=f"save_{nombre_grupo}"):
                # TODO: Aquí conectarás con dq.RegistroQueries.guardar_comida(...)
                # Pasándole: alimentos, dt_ingesta, tipo_comida, notas
                
                st.success(f"¡{nombre_grupo} guardada correctamente!")
                
                # Importante: Borrar SOLO los items de este grupo
                dq.CarritoQueries.eliminar_grupo(nombre_grupo)
                st.rerun()