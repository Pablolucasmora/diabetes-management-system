from fasthtml.common import *
from DayBetes_food.components.food.food_main import food_main
from DayBetes_food.components.ui import render_page
from DayBetes_food.database.queries.crud import get_all_catalogo, add_evento_ingesta, get_all_usuarios
from DayBetes_food.components.food.alimentos import FoodCard, BotonAdd
from DayBetes_food.database.connection import get_connection



def setup_food_routes(rt):
    
    @rt("/food")
    def get(req):
        return render_page(req, food_main)
    
    @rt("/search_food")
    def get(request: Request, search: str):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        conexion = get_connection()
        resultados = get_all_catalogo(conexion, search)
        
        if not resultados:
            return ""

        lista_html = [FoodCard(alimento) for alimento in resultados]

        return H2("Catalogo", cls="text-gray-500/50"), *lista_html

    @rt("/add_food/{alimento_id}")
    def post(request: Request, alimento_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        
        conexion = get_connection()
        
        usuarios = get_all_usuarios(conexion)
        if not usuarios:
            return HTMLResponse("No hay usuarios", status_code=400)
        
        user_id = usuarios[0]["id"]
        
        evento_id = add_evento_ingesta(
            conexion,
            user_id=user_id,
            estado="planificado"
        )
        
        headers = {"HX-Trigger": "addSuccess" if evento_id else "addError"}
        return HTMLResponse("", headers=headers)
    
    @rt("/selector_comida_input")
    def get(request: Request, evento_ingesta_id: str):
        if evento_ingesta_id != "0":
            return ""
        
        on_after = {"hx-on::after-request": """
            var trigger = event.detail.xhr.getResponseHeader('HX-Trigger');
            var btn = this;
            if(trigger === 'addSuccess') {
                btn.classList.add('bg-green-400');
                setTimeout(function() { btn.classList.remove('bg-green-400'); }, 300);
            } else {
                btn.classList.add('bg-red-400');
                setTimeout(function() { btn.classList.remove('bg-red-400'); }, 300);
            }
        """}
        
        return Div(
            Input(
                placeholder="Nombre de la comida",
                name="nombre_comida",
                id="input_nombre_comida_text",
                autofocus=True,
                cls="""
                border-[1px] px-2 py-1
                md:text-sm lg:text-sm text-xs
                shadow-sm rounded-md focus:outline-none
                border-gray-300 w-full
                """,
                hx_post="/crear_evento_named",
                hx_trigger="keyup[keyCode==13]",
                hx_target="#input_nombre_comida",
                hx_swap="none",
                hx_include="this"
            ),
            Button(
                "Añadir",
                cls="""
                border-[1px] px-2 py-1
                md:text-sm lg:text-sm text-xs
                shadow-sm rounded-md cursor-pointer
                border-gray-300 hover:bg-gray-200
                transition-colors duration-300
                """,
                hx_post="/crear_evento_named",
                hx_target="#selector_comida_input_wrapper",
                hx_swap="none",
                hx_include="#input_nombre_comida_text",
                **on_after
            ),
            cls="flex gap-2 w-full"
        )

    @rt("/crear_evento_named")
    def post(request: Request, nombre_comida: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        
        conexion = get_connection()
        
        usuarios = get_all_usuarios(conexion)
        if not usuarios:
            return HTMLResponse("No hay usuarios", status_code=400)
        
        user_id = usuarios[0]["id"]
        
        evento_id = add_evento_ingesta(
            conexion,
            user_id=user_id,
            estado="planificado",
            nombre=nombre_comida or None
        )
        
        headers = {"HX-Trigger": "addSuccess" if evento_id else "addError"}
        return HTMLResponse("", headers=headers)
