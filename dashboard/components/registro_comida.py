import streamlit as st
import database.queries as dq

def render_seccion_principal_registro():
    """
    Organiza la estructura visual de la pestaña de registro.
    """
    st.header("Registro de Comida")
    
    # Inicializamos el carrito si no existe
    if "carrito" not in st.session_state:
        st.session_state.carrito = []
    
    # Columna Izquierda: Buscador y Alta | Columna Derecha: Resumen
    col_izq, col_der = st.columns([2, 1])
    
    with col_izq:
        render_formulario_registro()

    with col_der:
        st.subheader("🛒 Comida actual")
        
        if not st.session_state.carrito:
            st.warning("Selecciona un alimento para empezar.")
        else:
            total_hc = 0
            total_gr = 0
            total_pr = 0
            # Mostramos los elementos del carrito
            for i, item in enumerate(st.session_state.carrito):
                c_nom, c_del = st.columns([4, 1])
                c_nom.write(f"**{item['nombre']}** ({item['cantidad']}g) → {item['hc']}g HC , {item['gr']}g GR, {item['pr']}g PR")
                if c_del.button("🗑️", key=f"del_{i}"):
                    st.session_state.carrito.pop(i)
                    st.rerun()
                total_hc += item['hc']
                total_gr += item['gr']
                total_pr += item['pr']
            
            st.divider()
            st.metric("Total Hidratos", f"{round(total_hc, 2)} g")
            st.metric("Total Grasas", f"{round(total_gr, 2)} g")
            st.metric("Total Proteínas", f"{round(total_pr, 2)} g")
        
        # Campos generales de la comida
        st.divider()
        tipo = st.selectbox("Momento:", ["Desayuno", "Almuerzo", "Comida", "Merienda", "Cena", "Snack"])
        notas_comida = st.text_area("Notas de la comida", placeholder="Ej: Comida en casa de mi abuela")
        
        if st.button("💾 Guardar Registro Completo", use_container_width=True, type="primary"):
            if st.session_state.carrito:
                st.success("¡Registro guardado con éxito! (Lógica de base de datos lista para conectar)")
                # Aquí iría el Paso 1.5: dq.RegistroQueries.guardar_comida(...)
                st.session_state.carrito = [] # Limpiamos tras guardar
                st.rerun()
            else:
                st.error("El carrito está vacío.")

def render_formulario_registro():
    st.subheader("🔍 Añadir Alimentos")

    # Inicializamos variable para auto-seleccionar el producto recién creado
    if "id_recien_creado" not in st.session_state:
        st.session_state.id_recien_creado = None

    # 1. Cargamos catálogo con caché
    @st.cache_data
    def cargar_catalogo():
        return dq.CatalogoQueries.obtener_todos_nombres_id()

    catalogo = cargar_catalogo()
    opciones = {f"{r['nombre']} ({r['marca']})": r['id_producto'] for r in catalogo}

    # 2. Buscador
    # Si tenemos un ID recién creado, lo usamos para la lógica, pero el buscador puede empezar en None
    seleccion = st.selectbox(
        "Busca o selecciona un alimento del catálogo:",
        options=list(opciones.keys()),
        index=None, 
        placeholder="Escribe el nombre del producto...",
        key="buscador_principal"
    )

    # Determinamos qué producto mostrar: el del buscador o el recién creado
    id_a_mostrar = None
    if seleccion:
        id_a_mostrar = opciones[seleccion]
        st.session_state.id_recien_creado = None # Si el usuario busca algo, anulamos el "recién creado"
    elif st.session_state.id_recien_creado:
        id_a_mostrar = st.session_state.id_recien_creado

    # 3. Mostrar producto seleccionado para añadir al carrito
    if id_a_mostrar:
        producto = dq.CatalogoQueries.obtener_producto_por_id(id_a_mostrar)
        
        if producto:
            color_bloque = "inverse" if st.session_state.id_recien_creado else "info"
            st.info(f"✨ **Seleccionado:** {producto.nombre} | {producto.hidratos_g}g HC por 100g/ml")
            
            c1, c2 = st.columns([2, 1])
            cantidad_str = c1.text_input("Cantidad (g/ml)", key=f"input_cant_{id_a_mostrar}")
            
            if c2.button("Añadir ➕", type="primary", key=f"btn_add_{id_a_mostrar}", use_container_width=True):
                try:
                    cantidad = int(cantidad_str)
                    if cantidad > 0:
                        factor = cantidad / 100.0
                        st.session_state.carrito.append({
                            "nombre": producto.nombre,
                            "cantidad": cantidad,
                            "hc": round(producto.hidratos_g * factor, 2),
                            "gr": round(producto.grasas_g * factor, 2),
                            "pr": round(producto.proteinas_g * factor, 2),
                            "id_producto": producto.id_producto
                        })
                        st.toast(f"✅ Añadido: {producto.nombre}")
                        st.session_state.id_recien_creado = None # Limpiamos tras añadir
                        st.rerun()
                    else:
                        st.error("Introduce una cantidad válida")
                except ValueError:
                    st.error("La cantidad debe ser un número entero")

    st.divider()

    # 4. Formulario de Alta Nueva
    with st.expander("➕ ¿No está en la lista? Crear producto nuevo"):
        categoria = st.selectbox("Categoría*", ["Alimento", "Bebida", "Suplemento"], key="new_cat")
        
        with st.form("form_alta_completa", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nombre = col1.text_input("Nombre*")
            marca = col2.text_input("Marca")
            subtipo = st.text_input("Subtipo (ej: Pasta, Refresco...)")

            st.write("**Valores nutricionales (por 100g/ml)**")
            n1, n2, n3, n4, n5 = st.columns(5)
            hc = n1.text_input("HC (g)")
            az = n2.text_input("AZ (g)")
            pr = n3.text_input("PR (g)")
            fb = n4.text_input("FB (g)")
            gr = n5.text_input("GR (g)")

            # Valoraciones nutricionales
            nutri_options = ["A", "B", "C", "D", "E", "Desconocido"]
            nutriscore = st.selectbox("NutriScore", nutri_options, index=5)
            nova = st.selectbox("NOVA", [1, 2, 3, 4, 'Desconocido'], index=4)

            # Campos dinámicos para Bebidas
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
                        def to_f(v): return float(v.replace(',', '.')) if v else 0.0
                        from database.queries import ProductoModel
                        nuevo = ProductoModel(
                            nombre=nombre, marca=marca, categoria=categoria, subtipo=subtipo,
                            hidratos_g=to_f(hc), azucares_g=to_f(az), proteinas_g=to_f(pr), fibra_g=to_f(fb), grasas_g=to_f(gr),
                            graduacion_pct=to_f(grad), cafeina_mg=to_f(caf), es_gas=gas, notas=notas_prod, nutriscore=nutriscore, nova=nova
                        )
                        nuevo_id = dq.CatalogoQueries.insertar_producto(nuevo)
                        if nuevo_id:
                            st.success(f"¡{nombre} creado! Ahora introduce la cantidad arriba.")
                            # Guardamos el ID para que aparezca arriba inmediatamente
                            st.session_state.id_recien_creado = nuevo_id
                            st.cache_data.clear()
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error en los datos: {e}")
                else:
                    st.error("El nombre es obligatorio")