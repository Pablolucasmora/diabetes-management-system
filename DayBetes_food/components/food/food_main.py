from fasthtml.common import *
from DayBetes_food.components.food.foods import (
    CreatePanels,
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
    catalog_items = get_all_catalog(connection)
    manual_items = get_all_manual_intakes(connection, users_id=user_id) if user_id else []
    recipes = get_all_recipes(connection, users_id=user_id) if user_id else []
    foods = _sorted_food_entries(catalog_items, manual_items, recipes)
    
    return Div(
        QuickCreateButtons(),
        CreatePanels(),
        SearchInput(),
        Filters(),
        MealSelector(connection, user_id=user_id or 0),
        cls="""
            flex flex-col items-center
            justify-between lg:gap-5 md:gap-5 gap-3 w-full
            md:mt-7 lg:mt-7 mt-2 fixed left-1/2 -translate-x-1/2 bg-[#f6f2eb]
        """
    ), Div(
    FoodList(foods),
    id="food_list_wrapper",
    cls="""md:pt-[250px] lg:pt-[250px] 
           pt-[180px] transition-all
           md:mb-50 lg:mb-50 mb-36
    """
)
