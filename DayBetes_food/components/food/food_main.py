from fasthtml.common import *
from DayBetes_food.components.food.foods import (
    Filters,
    MealSelector,
    QuickCreateButtons,
    SearchInput,
)
from DayBetes_food.database.queries.crud import get_default_user_id


def food_main(connection):
    user_id = get_default_user_id(connection)

    return Div(
        QuickCreateButtons(),
        SearchInput(),
        Filters(),
        MealSelector(connection, user_id=user_id or 0),
        id="food_top_bar",
        cls="""
            flex flex-col items-center
            justify-between lg:gap-4 md:gap-4 gap-3 md:w-lg lg:w-lg w-sm
            fixed inset-x-0 mx-auto
            top-0 pt-2 md:pt-7 lg:pt-7
            z-30
            bg-[#f6f2eb] border-b-[1px] border-white
        """,
        style=(
            "transform: translateZ(0);"
            "-webkit-transform: translateZ(0);"
            "backface-visibility: hidden;"
            "-webkit-backface-visibility: hidden;"
        ),
    ), Div(
        Div(
            "Loading...",
            id="food-list",
            hx_get="/food/list?filter=all&search_mode=recommended&page=1",
            hx_trigger="load",
            hx_swap="innerHTML",
            data_skip_page_loading="true",
            cls="flex flex-col items-center md:gap-3 lg:gap-3 gap-2 mt-4 transition-all duration-150 ease-out",
        ),
        id="food_list_wrapper",
        cls="""md:pt-[240px] lg:pt-[240px]
               pt-[170px]
               md:mb-50 lg:mb-50 mb-36
        """,
    )
