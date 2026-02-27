from fasthtml.common import *
from DayBetes_food.components.food.alimentos import Filtros, BusquedaInput, FoodList, SelectorComida
from DayBetes_food.database.queries.crud import get_all_catalogo

def food_main(conexion):
    alimentos = get_all_catalogo(conexion)
    
    return Div(
        Filtros(),
        BusquedaInput(),
        SelectorComida(conexion, user_id=1),
        cls="""
            flex flex-col items-center
            justify-between lg:gap-6 md:gap-6 gap-3 w-full
            md:mt-7 lg:mt-7 fixed left-1/2 -translate-x-1/2 bg-[#f6f2eb]
        """
    ), Div(
    FoodList(alimentos),
    id="food_list_wrapper",
    cls="md:pt-[190px] lg:pt-[190px] pt-[135px] transition-all"
)
