from fasthtml.common import *
from DayBetes_food.components.food.foods import (
    Filters,
    FoodList,
    MealSelector,
    QuickCreateButtons,
    SearchInput,
)
from DayBetes_food.database.queries.crud import (
    get_all_catalog,
    get_all_manual_intakes,
    get_all_recipes,
    get_default_user_id,
)


def _sorted_food_entries(catalog_items, manual_items, recipes):
    entries = []
    for item in catalog_items:
        entries.append({"entry_type": "catalog", **item})
    for item in manual_items:
        entries.append({"entry_type": "manual_intake", **item})
    for item in recipes:
        entries.append({"entry_type": "recipe", **item})

    entries.sort(key=lambda item: (0 if item.get("favorite") else 1, (item.get("name") or "").lower()))
    return entries

def food_main(connection):
    user_id = get_default_user_id(connection)
    catalog_items = get_all_catalog(connection, viewer_user_id=user_id) if user_id else get_all_catalog(connection, viewer_user_id=-1)
    manual_items = get_all_manual_intakes(connection, viewer_user_id=user_id) if user_id else get_all_manual_intakes(connection, viewer_user_id=-1)
    recipes = get_all_recipes(connection, viewer_user_id=user_id) if user_id else get_all_recipes(connection, viewer_user_id=-1)
    foods = _sorted_food_entries(catalog_items, manual_items, recipes)
    
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
    FoodList(foods),
    id="food_list_wrapper",
    cls="""md:pt-[240px] lg:pt-[240px]
           pt-[170px]
           md:mb-50 lg:mb-50 mb-36
    """
)
