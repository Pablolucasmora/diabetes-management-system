import streamlit as st
import database.queries as dq
from datetime import datetime, timedelta
from dateutil import parser # Asegúrate de tener: pip install python-dateutil

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
    [data-testid="stMetricDelta"] svg { display: none; }
    /* Estilo para simular una métrica con color personalizado */
    .fiber-metric {
        font-size: 2rem;
        font-weight: 600;
        line-height: 1.2;
    }
    .fiber-label {
        font-size: 0.875rem;
        color: rgba(250, 250, 250, 0.6);
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
        
        # --- PREPARACIÓN DE DATOS ---
        meta = alimentos[0]
        
        # 1. Recuperar Hora
        hora_db = meta.get('hora_inicio_manual')
        if hora_db:
            try: val_hora = datetime.strptime(hora_db, "%H:%M").time()
            except: val_hora = datetime.now().time()
        else:
            fechas = [x['fecha_agregado'] for x in alimentos if x.get('fecha_agregado')]
            try: val_hora = parser.parse(min(fechas)).time() if fechas else datetime.now().time()
            except: val_hora = datetime.now().time()

        # 2. Recuperar Config
        tipo_manual = meta.get('tipo_comida_manual')
        opts = ["Desayuno", "Almuerzo", "Comida", "Merienda", "Cena", "Snack", "Rescate"]
        idx_tipo = opts.index(tipo_manual) if (tipo_manual and tipo_manual in opts) else 2
        val_rest = bool(meta.get('es_restaurante_manual', 0))
        val_notas = meta.get('notas_manual') or ""

        # --- CABECERA GRUPO ---
        hc_grupo = sum(item['hc'] for item in alimentos)
        
        with st.expander(f"🍽️ {nombre_grupo} ({round(hc_grupo, 1)}g HC)", expanded=True):
            
            c_hora, c_tipo = st.columns(2)
            hora_ingesta = c_hora.time_input("Hora Inicio", value=val_hora, key=f"time_{nombre_grupo}", on_change=actualizar_hora, args=(nombre_grupo,))
            tipo_comida = c_tipo.selectbox("Momento", opts, index=idx_tipo, key=f"type_{nombre_grupo}", on_change=actualizar_tipo, args=(nombre_grupo,))
            dt_ingesta = datetime.combine(datetime.now().date(), hora_ingesta)
            st.divider()

            # --- LISTADO DE ITEMS E INICIALIZACIÓN DE ACUMULADORES ---
            t_hc, t_gr, t_pr, t_fb, t_az, t_sat = 0, 0, 0, 0, 0, 0
            
            # Variables para calcular la incertidumbre ponderada
            peso_total_grupo = 0.0
            peso_sin_dato_fibra = 0.0

            for i, item in enumerate(alimentos):
                # Calcular pesos para la incertidumbre
                peso_item = float(item['cantidad'] or 0)
                peso_total_grupo += peso_item
                
                # Gestión de Fibra (NULL vs Valor)
                val_fb = item.get('fb')
                if val_fb is None:
                    txt_fb = "--"
                    peso_sin_dato_fibra += peso_item # Sumamos al "saco" desconocido
                    # t_fb no se toca (es 0)
                else:
                    txt_fb = f"{val_fb}g"
                    t_fb += val_fb

                # --- RENDERIZADO ITEM ---
                c_info, c_qty, c_del = st.columns([4, 1.5, 0.5])
                unidades = float(item.get('unidades', 1) or 1)
                
                c_info.markdown(f"**{item.get('nombre_display', 'Desconocido')}**")
                c_peso, c_macros, c_offset = c_info.columns([1, 2.5, 1])
                
                key_dinamica = f"peso_{item['id_item']}_u{unidades}"
                
                def actualizar_peso_callback(id, key):
                    dq.CarritoQueries.actualizar_peso_item(id, st.session_state[key])

                with c_peso:
                    st.number_input("g", value=peso_item, step=5.0, key=key_dinamica, label_visibility="collapsed", on_change=actualizar_peso_callback, args=(item['id_item'], key_dinamica))

                with c_macros:
                    st.caption(f"**HC: {round(item['hc'], 1)}** | G: {round(item['gr'], 1)} | P: {round(item['pr'], 1)} | F: {txt_fb}")
                
                with c_offset:
                    offset = st.text_input("Offset (min)", key=f"input_offset_{id_a_mostrar}")

                with c_qty:
                    key_units = f"u_in_{item['id_item']}_{item['cantidad']}"
                    def update_units_callback(id_prod, k_state):
                        dq.CarritoQueries.actualizar_unidades_absoluto(id_prod, st.session_state[k_state])
                    
                    st.number_input(label = "Unidades", min_value=0.1, value=unidades, step=0.5, format="%.2f", key=key_units, on_change=update_units_callback, args=(item['id_item'], key_units))

                if c_del.button("❌", key=f"del_{item['id_item']}"):
                    dq.CarritoQueries.eliminar_item(item['id_item'])
                    st.rerun()

                st.divider()
                
                # Sumar macros restantes
                t_hc += item.get('hc', 0); t_gr += item.get('gr', 0); t_pr += item.get('pr', 0)
                t_az += (item.get('az') or 0); t_sat += (item.get('sat') or 0)

            # --- CÁLCULO FINAL INCERTIDUMBRE (0.0 - 1.0) ---
            if peso_total_grupo > 0:
                incertidumbre_fibra_pct = peso_sin_dato_fibra / peso_total_grupo
            else:
                incertidumbre_fibra_pct = 0.0

            # --- VISUALIZACIÓN DE TOTALES ---
            m1, m2 = st.columns(2)
            m1.metric("HC Total", f"{round(t_hc, 1)}", delta=f"{round(t_az, 1)} Azúcar" if t_az > 0 else None, delta_color="off")
            m2.metric("Grasas", f"{round(t_gr, 1)}", delta=f"{round(t_sat, 1)} Sat" if t_sat > 0 else None, delta_color="off")
            
            m3, m4 = st.columns(2)
            m3.metric("Proteína", f"{round(t_pr, 1)}")
            
            # --- SEMÁFORO DE FIBRA ---
            with m4:
                st.markdown('<p class="fiber-label">Fibra</p>', unsafe_allow_html=True)
                
                texto_fibra = f"{round(t_fb, 1)}g"
                pct_display = f"{incertidumbre_fibra_pct:.0%}"
                
                if incertidumbre_fibra_pct == 0.0:
                    # Verde (Fiable)
                    st.markdown(f'<div class="fiber-metric" style="color: #4CAF50;">{texto_fibra}</div>', unsafe_allow_html=True)
                elif incertidumbre_fibra_pct < 0.20:
                    # Naranja (Precaución)
                    st.markdown(f'<div class="fiber-metric" style="color: #FF9800;">⚠️ {texto_fibra}</div>', unsafe_allow_html=True)
                    st.caption(f"Falta dato del {pct_display} del plato.")
                else:
                    # Rojo (Peligro)
                    st.markdown(f'<div class="fiber-metric" style="color: #F44336;">❓ {texto_fibra}</div>', unsafe_allow_html=True)
                    st.caption(f"Dato no fiable. Falta info del {pct_display} del plato.")

            # --- EXTRAS Y GUARDADO ---
            es_restaurante = st.checkbox("Comida fuera / Restaurante", value=val_rest, key=f"rest_{nombre_grupo}", on_change=actualizar_rest, args=(nombre_grupo,))
            notas = st.text_area("Notas:", value=val_notas, key=f"notes_{nombre_grupo}", height=1, on_change=actualizar_notas, args=(nombre_grupo,))

            if st.button(f"💾 Registrar {nombre_grupo}", type="primary", use_container_width=True, key=f"save_{nombre_grupo}"):
                datos_guardar = {
                    "inicio": dt_ingesta,
                    "tipo_comida": tipo_comida,
                    "notas": notas,
                    "incertidumbre_fibra_pct": incertidumbre_fibra_pct, 
                    "es_restaurante": es_restaurante,
                    "alimentos": alimentos
                }
                if dq.ComidaQueries.añadir_comida(datos_guardar):
                    st.success(f"¡{nombre_grupo} guardada!")
                    dq.CarritoQueries.eliminar_grupo(nombre_grupo)
                    st.rerun()
                else:
                    st.error("Error al guardar.")