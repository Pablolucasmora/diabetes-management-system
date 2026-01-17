import streamlit as st
import database.queries as dq
from datetime import datetime, timedelta

# --- FUNCIONES CALLBACK (Se ejecutan al cambiar los inputs) ---
def actualizar_hora_grupo(grupo_key):
    """Guarda la nueva hora en BD inmediatamente"""
    nueva_hora = st.session_state[f"time_{grupo_key}"]
    dq.CarritoQueries.actualizar_cabecera_grupo(grupo_key, hora_str=nueva_hora.strftime("%H:%M"))

def actualizar_tipo_grupo(grupo_key):
    """Guarda el nuevo tipo en BD inmediatamente"""
    nuevo_tipo = st.session_state[f"type_{grupo_key}"]
    dq.CarritoQueries.actualizar_cabecera_grupo(grupo_key, tipo=nuevo_tipo)

def actualizar_notas_grupo(grupo_key):
    """Guarda las notas en BD inmediatamente"""
    nuevas_notas = st.session_state[f"notes_{grupo_key}"]
    dq.CarritoQueries.actualizar_cabecera_grupo(grupo_key, notas=nuevas_notas)

def actualizar_rest_grupo(grupo_key):
    """Guarda el check de restaurante en BD inmediatamente"""
    nuevo_val = st.session_state[f"rest_{grupo_key}"]
    dq.CarritoQueries.actualizar_cabecera_grupo(grupo_key, es_restaurante=nuevo_val)


from dateutil import parser # Asegúrate de tener: pip install python-dateutil

# --- 1. CALLBACKS: GUARDAN LOS CAMBIOS EN BD AL MOMENTO ---
def actualizar_hora(grupo):
    nueva = st.session_state[f"time_{grupo}"].strftime("%H:%M")
    dq.CarritoQueries.actualizar_cabecera_grupo(grupo, hora_str=nueva)

def actualizar_tipo(grupo):
    dq.CarritoQueries.actualizar_cabecera_grupo(grupo, tipo=st.session_state[f"type_{grupo}"])

def actualizar_rest(grupo):
    dq.CarritoQueries.actualizar_cabecera_grupo(grupo, es_restaurante=st.session_state[f"rest_{grupo}"])

def actualizar_notas(grupo):
    dq.CarritoQueries.actualizar_cabecera_grupo(grupo, notas=st.session_state[f"notes_{grupo}"])


def render_carrito():
    st.markdown("""
    <style>
    /* Ocultar la flecha en las métricas */
    [data-testid="stMetricDelta"] svg {
        display: none;
    }
    </style>
    """, unsafe_allow_html=True)

    st.subheader("🛒 Bandeja de Entrada")
    
    carrito = dq.CarritoQueries.obtener_carrito()
    if not carrito:
        st.info("Tu bandeja está vacía.")
        return

    # Agrupar items
    grupos = {}
    for item in carrito:
        gn = item.get('grupo_nombre', 'Comida Actual')
        if gn not in grupos: grupos[gn] = []
        grupos[gn].append(item)

    for nombre_grupo, alimentos in grupos.items():
        
        # --- PREPARACIÓN DE DATOS (PERSISTENCIA) ---
        meta = alimentos[0] # Usamos el primer item para leer la config del grupo
        
        # 1. Recuperar Hora: ¿Hay una guardada manualmente? Si no, calcular mínima.
        hora_db = meta.get('hora_inicio_manual')
        if hora_db:
            try: val_hora = datetime.strptime(hora_db, "%H:%M").time()
            except: val_hora = datetime.now().time()
        else:
            # Cálculo automático del mínimo
            fechas = [x['fecha_agregado'] for x in alimentos if x.get('fecha_agregado')]
            try: val_hora = parser.parse(min(fechas)).time() if fechas else datetime.now().time()
            except: val_hora = datetime.now().time()

        # 2. Recuperar Tipo
        tipo_manual = meta.get('tipo_comida_manual')
        opts = ["Desayuno", "Almuerzo", "Comida", "Merienda", "Cena", "Snack", "Rescate"]
        idx_tipo = opts.index(tipo_manual) if (tipo_manual and tipo_manual in opts) else 2

        # 3. Recuperar Extras
        val_rest = bool(meta.get('es_restaurante_manual', 0))
        val_notas = meta.get('notas_manual') or ""

        # --- RENDERIZADO ---
        hc_grupo = sum(item['hc'] for item in alimentos)
        
        with st.expander(f"🍽️ {nombre_grupo} ({round(hc_grupo, 1)}g HC)", expanded=True):
            
            c_hora, c_tipo = st.columns(2)
            
            # WIDGETS CON CALLBACKS (on_change)
            hora_ingesta = c_hora.time_input(
                "Hora Inicio", value=val_hora, key=f"time_{nombre_grupo}",
                on_change=actualizar_hora, args=(nombre_grupo,)
            )
            
            tipo_comida = c_tipo.selectbox(
                "Momento", opts, index=idx_tipo, key=f"type_{nombre_grupo}",
                on_change=actualizar_tipo, args=(nombre_grupo,)
            )

            dt_ingesta = datetime.combine(datetime.now().date(), hora_ingesta)
            st.divider()

            # --- LISTADO DE ITEMS ---
            t_hc, t_gr, t_pr, t_fb, t_az, t_sat = 0, 0, 0, 0, 0, 0
            
            # Bandera para saber si hay algún desconocido en este grupo
            hay_fibra_null = False

            for i, item in enumerate(alimentos):
                c_info, c_del = st.columns([5, 1])
                
                # Offset y Tiempos
                offset = item.get('offset_minutos') # Asegúrate que coincide con tu DB
                txt_offset = "" # Por defecto vacío para que no ensucie
                
                if offset is not None:
                    try:
                        val_offset = float(offset)
                        if val_offset != 0:
                            dt_inyeccion = dt_ingesta - timedelta(minutes=val_offset)
                            signo = "-" if val_offset > 0 else "+"
                            txt_offset = f" \n {signo}{int(val_offset)}min (~{dt_inyeccion.strftime('%H:%M')})"
                    except: pass
                
                # Visualización
                val_sat = item.get('sat', 0)
                val_az = item.get('az', 0)
                
                val_fb = item.get('fb') # Puede ser float, 0 o None

                if val_fb is None:
                    # CASO NULL: No sabemos cuánto hay
                    txt_fb = "--" 
                    hay_fibra_null = True
                    # No sumamos nada a t_fb (es como sumar 0 para evitar errores)
                else:
                    # CASO DATO REAL (incluido 0)
                    txt_fb = f"{val_fb}g"
                    t_fb += val_fb # Suma segura porque sabemos que es número

                nombre_display = item.get('nombre_display', 'Desconocido')
                c_info.markdown(f"**{nombre_display}** ({item['cantidad']}g)")
                c_info.caption(txt_offset)
                c_info.caption(
                    f"{item['hc']}g HC ({val_az:.1f}g Az) | "
                    f"{item['gr']}g GR ({val_sat:.1f}g sat) | "
                    f"{item['pr']}g PR | {txt_fb} FB "
                )
                
                if c_del.button("❌", key=f"del_{item['id_item']}"):
                    dq.CarritoQueries.eliminar_item(item['id_item'])
                    st.rerun()

                t_hc += item.get('hc', 0); t_gr += item.get('gr', 0)
                t_pr += item.get('pr', 0); t_fb += val_fb if val_fb is not None else 0
                t_az += val_az; t_sat += val_sat
                st.divider()

            # --- TOTALES ---
            m1, m2 = st.columns(2)
            m1.metric("HC Total", f"{round(t_hc, 1)}", delta=f"{round(t_az, 1)} Azúcar" if t_az > 0 else None, delta_color="off")
            m2.metric("Grasas", f"{round(t_gr, 1)}", delta=f"{round(t_sat, 1)} Sat" if t_sat > 0 else None, delta_color="off")
            
            m3, m4 = st.columns(2)
            m3.metric("Proteína", f"{round(t_pr, 1)}")
            # --- LÓGICA DE VISUALIZACIÓN TOTAL FIBRA ---
            label_fibra = f"{round(t_fb, 1)}"
            
            if hay_fibra_null:
                # Si había algún NULL, añadimos un "+" o un aviso
                label_fibra += "/+" 
                help_fibra = "El valor es aproximado. Algunos alimentos no tienen dato de fibra (--)."
            else:
                help_fibra = None

            m4.metric("Fibra", label_fibra, help=help_fibra)    
            # --- EXTRAS Y GUARDADO ---
            es_restaurante = st.checkbox("Comida fuera / Restaurante", value=val_rest, key=f"rest_{nombre_grupo}", on_change=actualizar_rest, args=(nombre_grupo,))
            notas = st.text_area("Notas:", value=val_notas, key=f"notes_{nombre_grupo}", height=1, on_change=actualizar_notas, args=(nombre_grupo,))

            if st.button(f"💾 Registrar {nombre_grupo}", type="primary", use_container_width=True, key=f"save_{nombre_grupo}"):
                datos_guardar = {
                    "inicio": dt_ingesta,
                    "tipo_comida": tipo_comida,
                    "notas": notas,
                    "es_restaurante": es_restaurante,
                    "alimentos": alimentos
                }
                if dq.ComidaQueries.añadir_comida(datos_guardar):
                    st.success(f"¡{nombre_grupo} guardada!")
                    dq.CarritoQueries.eliminar_grupo(nombre_grupo)
                    st.rerun()
                else:
                    st.error("Error al guardar.")