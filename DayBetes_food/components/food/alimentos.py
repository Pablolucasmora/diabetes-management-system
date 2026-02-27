from fasthtml.common import *
from DayBetes_food.database.queries.crud import get_eventos_carrito
from datetime import datetime


BTN_FILTER_CLS = """
    boton_web md:text-[16px] md:p-1 lg:text-[16px] lg:p-1 
    text-sm rounded-xl p-1 w-10/12 p-2
"""

def SelectorComida(conexion, user_id: int, selected_id: int = None):
    eventos = get_eventos_carrito(conexion, user_id)
    
    opciones = [
        Option(
            evento["nombre"] or f"Comida {evento['hora_comida'].strftime('%H:%M')}",
            value=str(evento["id"]),
            selected=(evento["id"] == selected_id)
        )
        for evento in eventos
    ] + [Option("Nueva Comida", value="0", selected=(selected_id == 0))]
    
    if not opciones:
        opciones = [Option("No hay comidas planificadas", value="", disabled=True)]
    
    return Div(        
        Select(
            *opciones,
            id="selector_comida",
            name="evento_ingesta_id",
            hx_get="/selector_comida_input",
            hx_target="#input_nombre_comida",
            hx_trigger="change",
            hx_include="this",
            cls="""
            border-[1px] px-2 py-1 
            md:text-sm lg:text-sm text-xs
            shadow-sm rounded-md focus:outline-none
            border-white cursor-pointer
            """
        ),
        Div(id="input_nombre_comida"),
        cls="flex flex-col gap-2 justify-end md:w-md lg:w-md w-xs"
    )



def Filtros():
    """Barra de filtros para alimentos"""
    filtros = [
        ("All", "col-start-1 col-span-1"),
        ("Foods", "col-start-2 col-span-1"),
        ("Recipes", "col-start-3 col-span-1"),
        ("Favs", "col-start-4 col-span-1"),
    ]
    
    botones = [
        Button(texto, cls=f"{BTN_FILTER_CLS} {clases}")
        for texto, clases in filtros
    ]
    
    return Div(
        *botones,
        cls=f"md:w-md lg:w-md w-xs grid grid-cols-4 grid-rows-1 justify-center md:gap-3 lg:gap-3 gap-1 transition-all"
    )


def BusquedaInput():
    """Input de búsqueda con HTMX"""
    return Input(
        inputmode="text",
        placeholder="¿Qué comiste?",
        cls="""
            input_web
            contenedor_web
            border-[0.6px] border-white inset-shadow-none
            rounded-2xl
            bg-gray-200/50
            md:w-md lg:w-md
            w-xs
            transition-all
            p-4
        """,
        name="search",
        hx_get="/search_food",
        hx_target="#food-list",
        hx_trigger="keyup changed delay:300ms",
        hx_swap="innerHTML"
    )


def FoodCard(alimento):
    """Card de alimento individual"""
    return Div(
        H1(alimento["nombre"], cls="col-start-1 col-span-4"),
        Div(f"{alimento['hidratos_100g']} CH", cls="text-sm col-start-1 col-span-2"),
        BotonAdd(hx_post=f"/add_food/{alimento["id"]}"),
        cls="boton_web food_entry grid grid-cols-5 grid-rows-2 items-center"
    )


def BotonAdd(**attrs):
    """Botón añadir alimento"""
    on_after = {"hx-on::after-request": """
    var trigger = event.detail.xhr.getResponseHeader('HX-Trigger');
    var btn = this;
    if(trigger === 'addSuccess') {
        btn.classList.add('bg-green-400');
        setTimeout(function() { btn.classList.remove('bg-green-400'); }, 500);
        setTimeout(function() { location.reload(); }, 2000);
    } else {
        btn.classList.add('bg-red-400');
        setTimeout(function() { btn.classList.remove('bg-red-400'); }, 500);
        setTimeout(function() { location.reload(); }, 2000);
    }
"""}
    
    return Button(
        "+",
        cls="""
            cursor-pointer rounded-lg 
            border-[1px] border-gray-500/30 shadow-none
            hover:bg-gray-500/50
            md:w-12 lg:w-12 w-10
            h-8
            col-start-5
            row-start-1 row-span-2
            justify-self-end
            transition-colors duration-300
        """,
        hx_swap="none",
        **on_after,
        **attrs
    )


def FoodList(alimentos):
    """Lista de alimentos"""
    if not alimentos:
        return H2("No hay alimentos", cls="text-gray-500/50")
    
    return Div(
        H2("Catálogo", cls="text-gray-500/50"),
        *[FoodCard(alimento) for alimento in alimentos],
        id="food-list",
        cls=f"flex flex-col items-center md:gap-3 lg:gap-3 gap-2 mt-4 "
    )
