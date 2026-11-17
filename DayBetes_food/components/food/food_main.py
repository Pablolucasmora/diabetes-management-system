from dataclasses import asdict
from urllib.parse import urlencode

from fasthtml.common import *
from DayBetes_food.components.injection_zone import asset_busted
from DayBetes_food.config import ASSISTANT_ENABLED
from DayBetes_food.components.food.food_actions import FoodActionsModal
from DayBetes_food.components.food.food_list import (
    Filters,
    FoodView,
    FoodFiltersModal,
    MealSelector,
    QuickCreateButtons,
    SearchInput,
)


from DayBetes_food.components.food.recipe_add import RecipeAddModal


def food_main(view: FoodView, events: list, plate_options: list, last_used_plate: int | None):
    """The Food page, opened on `view`: its pill, tabs and filters (frontend §5, §9.3).

    `events` are the planned meals and `plate_options` the plates of the first
    one, which the meal selector shows chosen (frontend_conventions.md §6); the
    route reads them (code_conventions.md §1.4).
    """
    selected_event_id = events[0].id if events else None

    return Div(
        # The page is asked for again on coming back, with the state of its URL
        # (static/js/food_view.js, frontend_conventions.md §5).
        hx_history="false",
        data_food_view="true",
    ), Script(src=asset_busted("/js/food_view.js"), defer="defer"), Div(
        # Blurs the whole page behind an open menu of the header
        # (static/js/food_quick_create.js). It is a single fixed layer with
        # backdrop-filter, instead of `filter: blur()` on each element: Safari
        # and Chrome paint coloured seams on blurred layers inside the glass
        # header (frontend_conventions.md §8).
        Div(
            id="food_menu_scrim",
            cls="fixed inset-0 z-[1] backdrop-blur-[1px] opacity-0 invisible transition-opacity duration-200",
        ),
        QuickCreateButtons(assistant_enabled=ASSISTANT_ENABLED),
        SearchInput(view),
        Filters(view),
        MealSelector(
            events,
            selected_id=selected_event_id,
            plate_options=plate_options,
            selected_plate_id=last_used_plate,
        ),
        id="food_top_bar",
        cls="""
            flex flex-col items-center
            justify-between lg:gap-3 md:gap-3 gap-2.5 md:w-2xl lg:w-2xl w-full
            sticky mx-auto
            top-0 pt-2 md:pt-7 lg:pt-7 pb-2
            z-[600]
            web_glass_strong rounded-b-3xl
        """,
    ), Div(
        Div(
            "Loading...",
            id="food-list",
            # The page's own view: a fixed query here showed another tab's list on
            # coming back. Not hx-include, which the cards inside would inherit.
            hx_get=f"/food/list?{urlencode({**asdict(view), 'page': 1})}",
            hx_trigger="load",
            hx_swap="innerHTML",
            data_skip_page_loading="true",
            cls="flex flex-col items-center md:gap-3 lg:gap-3 gap-2 mt-4 transition-all duration-150 ease-out",
        ),
        # Outside #food-list, so a new search does not remove an open pop-up.
        FoodActionsModal(),
        *RecipeAddModal(),
        *FoodFiltersModal(),
        id="food_list_wrapper",
        cls="""md:mb-50 lg:mb-50 mb-36""",
    )
