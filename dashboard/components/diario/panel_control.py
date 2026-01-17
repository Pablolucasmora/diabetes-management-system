import streamlit as st
import database.queries as dq
import json

def render_panel_control_z():
    with st.expander("🕰️ Historial de Acciones (Deshacer/Rehacer) (Últimos 2 cambios)"):
        
        # Obtenemos los últimos 2 logs
        logs = dq.db.execute_query("SELECT * FROM historial_cambios ORDER BY id_log DESC LIMIT 2")

        if not logs:
            st.caption("Historial limpio.")
            return

        for log in logs:
            c_info, c_btn = st.columns([3, 1])
            
            # --- 1. Preparación de Datos ---
            estado = log['estado']
            accion = log['accion']
            tabla_clean = log['tabla_afectada'].replace('_', ' ').title()
            
            # --- 2. Extracción Inteligente del Nombre ---
            # Si es DELETE, miramos el pasado (valor_anterior). Si no, el presente (valor_nuevo).
            json_raw = log['valor_anterior'] if accion == 'DELETE' else log['valor_nuevo']
            nombre_producto = ""
            
            if json_raw:
                try:
                    datos = json.loads(json_raw)
                    # Intentamos buscar 'nombre_display' primero, luego 'nombre'
                    nombre_producto = datos.get('nombre_display') or datos.get('nombre') or ""
                except Exception:
                    nombre_producto = "" # Si falla el JSON, lo dejamos vacío

            # --- 3. Construcción del Texto ---
            if nombre_producto:
                txt_base = f"**{accion}** `{nombre_producto}` en {tabla_clean}"
            else:
                txt_base = f"**{accion}** en {tabla_clean}"

            # --- 4. Renderizado (Activo vs Deshecho) ---
            if estado == 'ACTIVO':
                # Estado normal: Botón DESHACER
                c_info.markdown(f"✅ {txt_base}")
                if c_btn.button("↩️ Deshacer", key=f"undo_{log['id_log']}"):
                    ok, msg = dq.AuditoriaManager.deshacer(log['id_log'])
                    if ok: st.rerun()
                    else: st.error(msg)
            else:
                # Estado deshecho: Botón REHACER (Texto tachado)
                c_info.markdown(f"~~{txt_base}~~ (Deshecho)")
                if c_btn.button("🔁 Rehacer", key=f"redo_{log['id_log']}"):
                    ok, msg = dq.AuditoriaManager.rehacer(log['id_log'])
                    if ok: st.rerun()
                    else: st.error(msg)
            
            st.divider()