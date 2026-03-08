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


def _sorted_food_entries(catalog_items, manual_items, recipes, viewer_user_id: int | None = None):
    def _is_owned(entry_type: str, item: dict) -> bool:
        if not viewer_user_id:
            return False
        raw_owner = item.get("created_by") if entry_type in ("catalog", "manual_intake") else item.get("users_id")
        try:
            return int(raw_owner) == int(viewer_user_id)
        except (TypeError, ValueError):
            return False

    entries = []
    for item in catalog_items:
        entries.append({"entry_type": "catalog", "is_owned": _is_owned("catalog", item), **item})
    for item in manual_items:
        entries.append({"entry_type": "manual_intake", "is_owned": _is_owned("manual_intake", item), **item})
    for item in recipes:
        entries.append({"entry_type": "recipe", "is_owned": _is_owned("recipe", item), **item})

    entries.sort(
        key=lambda item: (
            0 if (item.get("favorite") or item.get("is_owned")) else 1,
            0 if item.get("favorite") else 1,
            (item.get("name") or "").lower(),
        )
    )
    return entries

def food_main(connection):
    user_id = get_default_user_id(connection)
    catalog_items = get_all_catalog(connection, viewer_user_id=user_id) if user_id else get_all_catalog(connection, viewer_user_id=-1)
    manual_items = get_all_manual_intakes(connection, viewer_user_id=user_id) if user_id else get_all_manual_intakes(connection, viewer_user_id=-1)
    recipes = get_all_recipes(connection, viewer_user_id=user_id) if user_id else get_all_recipes(connection, viewer_user_id=-1)
    foods = _sorted_food_entries(catalog_items, manual_items, recipes, viewer_user_id=user_id)
    foods = [item for item in foods if item.get("favorite") or item.get("is_owned")]
    
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
