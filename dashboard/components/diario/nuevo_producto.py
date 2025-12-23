import streamlit as st
import database.queries as dq
from database.queries import ProductoModel

def render_nuevo_producto():
    with st.expander("➕ ¿No está en la lista? Crear producto nuevo"):
        categoria = st.selectbox("Categoría*", ["Alimento", "Bebida", "Suplemento"], key="new_cat")
        
        with st.form("form_alta_completa", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nombre = col1.text_input("Nombre*")
            marca = col2.text_input("Marca")
            # Ahora subtipo es texto libre, como acordamos
            subtipo = st.text_input("Subtipo (ej: Pasta, Refresco...)")

            st.write("**Valores nutricionales (por 100g/ml)**")
            n1, n2, n3, n4, n5 = st.columns(5)
            hc = n1.text_input("HC (g)")
            az = n2.text_input("AZ (g)")
            pr = n3.text_input("PR (g)")
            fb = n4.text_input("FB (g)")
            gr = n5.text_input("GR (g)")

            # Valoraciones
            nutri_options = ["A", "B", "C", "D", "E", "Desconocido"]
            nutriscore = st.selectbox("NutriScore", nutri_options, index=5)
            nova = st.selectbox("NOVA", [1, 2, 3, 4, 'Desconocido'], index=4)

            # Bebidas
            grad, caf, gas = "0.0", "0.0", False
            if categoria == "Bebida":
                st.write("**Detalles de Bebida**")
                b1, b2, b3 = st.columns(3)
                grad = b1.text_input("Graduación %")
                caf = b2.text_input("Cafeína mg")
                gas = b3.checkbox("¿Tiene gas?")
            
            notas_prod = st.text_area("Notas")

            if st.form_submit_button("Guardar en Catálogo"):
                if nombre:
                    try:
                        # Helper para convertir texto a float
                        def to_f(v): return float(v.replace(',', '.')) if v else 0.0
                        
                        nuevo = ProductoModel(
                            nombre=nombre, marca=marca, categoria=categoria, subtipo=subtipo,
                            hidratos_g=to_f(hc), azucares_g=to_f(az), proteinas_g=to_f(pr), 
                            fibra_g=to_f(fb), grasas_g=to_f(gr), graduacion_pct=to_f(grad), 
                            cafeina_mg=to_f(caf), es_gas=gas, notas=notas_prod, 
                            nutriscore=nutriscore, nova=nova
                        )
                        
                        nuevo_id = dq.CatalogoQueries.insertar_producto(nuevo)
                        
                        if nuevo_id:
                            st.success(f"¡{nombre} creado! Ahora búscalo arriba.")
                            # Guardamos el ID en sesión para auto-seleccionarlo en el buscador
                            st.session_state.id_recien_creado = nuevo_id
                            st.cache_data.clear() # Limpiamos caché para que aparezca
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error en los datos: {e}")
                else:
                    st.error("El nombre es obligatorio")