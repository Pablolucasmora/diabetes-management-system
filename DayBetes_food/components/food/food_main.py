from fasthtml.common import *
from DayBetes_food.components.food.foods import Filters, SearchInput, FoodList, MealSelector
from DayBetes_food.database.queries.crud import get_all_catalog

def food_main(connection):
    foods = get_all_catalog(connection)
    
    return Div(
        Filters(),
        SearchInput(),
        MealSelector(connection, user_id=1),
        cls="""
            flex flex-col items-center
            justify-between lg:gap-6 md:gap-6 gap-3 w-full
            md:mt-7 lg:mt-7 fixed left-1/2 -translate-x-1/2 bg-[#f6f2eb]
        """
    ), Div(
    FoodList(foods),
    id="food_list_wrapper",
    cls="md:pt-[190px] lg:pt-[190px] pt-[135px] transition-all"
)
