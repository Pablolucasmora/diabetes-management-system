from datetime import datetime
from fasthtml.common import *

from DayBetes_food.database.queries.crud import get_cart_events


CATEGORY_OPTIONS = [
    "meat",
    "fish",
    "dairy",
    "eggs",
    "processed_meat",
    "legumes",
    "tubers",
    "nuts",
    "vegetables",
    "fruits",
    "cereals",
    "oils_and_fats",
    "sweets",
    "beverages",
    "sauces",
    "condiments",
    "supplements",
]

MEAL_TYPES = ["breakfast", "brunch", "lunch", "afternoon_snack", "dinner", "snack", "rescue"]

GLYCEMIC_INDEX_OPTIONS = ["high", "medium", "low"]

INITIAL_STATE_OPTIONS = ["solid", "mashed/creamy", "liquid", "gel"]

FILTER_ITEM_CLS = """
    px-3 py-1.5
    w-full
    text-[11px] md:text-xs
    rounded-full
    transition-all duration-200
    cursor-pointer
    border border-white/80
    shadow-sm
"""


def on_after(target="this"):
    return {"hx-on:htmx:after-request": f"""
    var btn = {target if target == "this" else f"document.getElementById('{target}')"};
    if(event.detail.successful) {{
        btn.style.backgroundColor = 'rgb(74, 222, 128)';
    }} else {{
        btn.style.backgroundColor = 'rgb(248, 113, 113)';
    }}
    setTimeout(function() {{ btn.style.backgroundColor = ''; }}, 300);
    setTimeout(function() {{ location.reload(); }}, 600);
"""}


def MealSelector(connection, user_id: int, selected_id: int = None):
    events = get_cart_events(connection, user_id)

    options = [
        Option(
            event["name"] or f"Meal {event['meal_time'].strftime('%H:%M')}",
            value=str(event["id"]),
            selected=(event["id"] == selected_id),
        )
        for event in events
    ]

    if not options:
        options = [Option("- No meals yet -", value="", cls="text-gray-500/50")]

    options.append(Option("New Meal", value="0", selected=(selected_id == 0)))

    return Div(
        Select(
            *options,
            id="meal_selector",
            name="intake_event_id",
            hx_get="/meal_selector_input",
            hx_target="#meal_name_input",
            hx_trigger="change",
            hx_include="this",
            style="color: gray" if not events else "",
            cls="""
            border-[1px] px-2 py-1
            md:text-sm lg:text-sm text-xs
            shadow-sm rounded-md focus:outline-none
            lg:w-40 md:w-40 w-32
            border-white cursor-pointer
            """,
        ),
        Div(id="meal_name_input", cls="lg:w-40 md:w-40 w-32 bg-transparent"),
        cls="flex flex-col gap-2 items-end md:w-md lg:w-md w-xs",
    )


def Filters():
    filters = [("All", "all"), ("Food", "food"), ("Recipes", "recipes"), ("Favs", "favs")]
    buttons = []
    for text, value in filters:
        buttons.append(
            Button(
                text,
                cls=f"{FILTER_ITEM_CLS} {'bg-black text-white shadow-md' if value == 'all' else 'bg-transparent text-gray-700'}",
                data_food_filter_btn="true",
                data_filter_value=value,
                hx_get="/food/list",
                hx_target="#food-list",
                hx_swap="innerHTML",
                hx_include="#food_search_input, #food_filter",
                **{
                    "hx-on:click": (
                        f"document.getElementById('food_filter').value='{value}';"
                        "var active='bg-black text-white shadow-md';"
                        "var inactive='bg-transparent text-gray-700';"
                        "document.querySelectorAll('[data-food-filter-btn]').forEach(function(btn){"
                        "btn.classList.remove('bg-black','text-white','shadow-md');"
                        "btn.classList.add('bg-transparent','text-gray-700');"
                        "});"
                        "this.classList.remove('bg-transparent','text-gray-700');"
                        "this.classList.add('bg-black','text-white','shadow-md');"
                    ),
                },
            )
        )

    return Div(
        Input(type="hidden", id="food_filter", name="filter", value="all"),
        Div(
            *buttons,
            cls="""
                relative
                flex items-center justify-between
                gap-3
                w-full
                rounded-full
            """,
        ),
        cls="md:w-md lg:w-md w-xs transition-all",
    )


def SearchInput():
    return Input(
        inputmode="text",
        placeholder="What did you eat?",
        name="search",
        id="food_search_input",
        cls="""
            web_input
            border-[0.6px] border-white inset-shadow-none
            rounded-2xl
            bg-gray-200/50
            md:w-md lg:w-md
            w-xs
            transition-all
            p-4
        """,
        hx_get="/food/list",
        hx_target="#food-list",
        hx_trigger="keyup changed delay:300ms",
        hx_include="#food_filter",
        hx_swap="innerHTML",
    )


def _labeled_input(label: str, name: str, typ: str = "text", placeholder: str = ""):
    return Div(
        Label(label, cls="text-xs text-gray-700"),
        Input(
            type=typ,
            name=name,
            placeholder=placeholder,
            cls="web_input border border-white rounded-lg px-2 py-1 text-xs",
        ),
        cls="flex flex-col gap-1",
    )


def _labeled_select(label: str, name: str, options: list[str]):
    return Div(
        Label(label, cls="text-xs text-gray-700"),
        Select(
            Option("-", value=""),
            *[Option(opt, value=opt) for opt in options],
            name=name,
            cls="web_input border border-white rounded-lg px-2 py-1 text-xs",
        ),
        cls="flex flex-col gap-1",
    )


def _favorite_checkbox(name: str = "favorite"):
    return Label(
        Input(type="checkbox", name=name, value="true"),
        Span("Favorite", cls="text-xs text-gray-700"),
        cls="flex items-center gap-2",
    )


def QuickCreateButtons():
    return Div(
        Button(
            "Add catalog",
            type="button",
            cls="web_button px-2 py-1 text-[10px] md:text-xs",
            onclick="document.getElementById('create_catalog_panel').classList.toggle('hidden')",
        ),
        Button(
            "Add manual",
            type="button",
            cls="web_button px-2 py-1 text-[10px] md:text-xs",
            onclick="document.getElementById('create_manual_panel').classList.toggle('hidden')",
        ),
        Button(
            "Add recipe",
            type="button",
            cls="web_button px-2 py-1 text-[10px] md:text-xs",
            onclick="document.getElementById('create_recipe_panel').classList.toggle('hidden')",
        ),
        cls="flex items-center justify-center gap-2 md:w-md lg:w-md w-xs",
    )


def CreateCatalogPanel():
    return Div(
        Form(
            Div(
                _labeled_input("Name*", "name"),
                _labeled_input("Brand", "brand"),
                _labeled_select("Category*", "category", CATEGORY_OPTIONS),
                _labeled_input("Subtype*", "subtype"),
                _labeled_select("Initial state", "initial_state", INITIAL_STATE_OPTIONS),
                _labeled_select("Nutriscore", "nutriscore", ["A", "B", "C", "D", "E"]),
                _labeled_input("NOVA (1-4)", "nova", "number"),
                _labeled_input("Yuka (0-100)", "yuka", "number"),
                _labeled_input("Default portion", "default_portion", "number"),
                _labeled_input("Calories/100g", "calories_100g", "number"),
                _labeled_input("Carbs/100g", "carbs_100g", "number"),
                _labeled_input("Sugars/100g", "sugars_100g", "number"),
                _labeled_input("Fats/100g", "fats_100g", "number"),
                _labeled_input("Saturated/100g", "saturated_100g", "number"),
                _labeled_input("Proteins/100g", "proteins_100g", "number"),
                _labeled_input("Fiber/100g", "fiber_100g", "number"),
                _labeled_input("Caffeine", "caffeine", "number"),
                _labeled_input("Alcohol", "alcohol", "number"),
                _labeled_input("Barcode", "barcode"),
                _labeled_input("Cooking factor", "cooking_factor", "number"),
                _favorite_checkbox(),
                cls="grid grid-cols-2 gap-2",
            ),
            Button(
                "Create catalog item",
                type="submit",
                cls="web_button px-3 py-2 text-xs",
            ),
            hx_post="/food/create/catalog",
            hx_target="#create_catalog_result",
            hx_swap="innerHTML",
            cls="web_container p-3 rounded-2xl flex flex-col gap-3",
        ),
        Div(id="create_catalog_result", cls="text-xs"),
        id="create_catalog_panel",
        cls="hidden md:w-md lg:w-md w-xs flex flex-col gap-2",
    )


def CreateManualPanel():
    return Div(
        Form(
            Div(
                _labeled_input("Name*", "name"),
                _labeled_input("Description", "description"),
                _labeled_input("Subtype*", "subtype"),
                _labeled_input("Origin", "origin"),
                _labeled_input("Amount g*", "amount_g", "number"),
                _labeled_input("Calories/100g", "calories_100g", "number"),
                _labeled_input("Carbs/100g", "carbs_100g", "number"),
                _labeled_input("Sugars/100g", "sugars_100g", "number"),
                _labeled_input("Fats/100g", "fats_100g", "number"),
                _labeled_input("Saturated/100g", "saturated_100g", "number"),
                _labeled_input("Proteins/100g", "proteins_100g", "number"),
                _labeled_input("Fiber/100g", "fiber_100g", "number"),
                _labeled_input("Caffeine", "caffeine", "number"),
                _labeled_input("Alcohol", "alcohol", "number"),
                _labeled_select("Glycemic index", "glycemic_index", GLYCEMIC_INDEX_OPTIONS),
                _labeled_input("IG confidence 1-5", "ig_confidence", "number"),
                _favorite_checkbox(),
                cls="grid grid-cols-2 gap-2",
            ),
            Button(
                "Create manual intake",
                type="submit",
                cls="web_button px-3 py-2 text-xs",
            ),
            hx_post="/food/create/manual",
            hx_target="#create_manual_result",
            hx_swap="innerHTML",
            cls="web_container p-3 rounded-2xl flex flex-col gap-3",
        ),
        Div(id="create_manual_result", cls="text-xs"),
        id="create_manual_panel",
        cls="hidden md:w-md lg:w-md w-xs flex flex-col gap-2",
    )


def CreateRecipePanel():
    return Div(
        Form(
            Div(
                _labeled_input("Name*", "name"),
                _labeled_select("Meal type", "meal_type", MEAL_TYPES),
                Div(
                    Label("Notes", cls="text-xs text-gray-700"),
                    Textarea(
                        "",
                        name="notes",
                        rows="3",
                        cls="web_input border border-white rounded-lg px-2 py-1 text-xs",
                    ),
                    cls="flex flex-col gap-1 col-span-2",
                ),
                _favorite_checkbox(),
                cls="grid grid-cols-2 gap-2",
            ),
            Button(
                "Create recipe",
                type="submit",
                cls="web_button px-3 py-2 text-xs",
            ),
            hx_post="/food/create/recipe",
            hx_target="#create_recipe_result",
            hx_swap="innerHTML",
            cls="web_container p-3 rounded-2xl flex flex-col gap-3",
        ),
        Div(id="create_recipe_result", cls="text-xs"),
        id="create_recipe_panel",
        cls="hidden md:w-md lg:w-md w-xs flex flex-col gap-2",
    )


def CreatePanels():
    return Div(
        CreateCatalogPanel(),
        CreateManualPanel(),
        CreateRecipePanel(),
        cls="flex flex-col gap-2 items-center",
    )


def FavoriteButton(entry_type: str, entry_id: int, favorite: bool):
    icon = "images/content/fav_icon.svg" if favorite else "images/content/not_fav_icon.svg"
    return Button(
        Img(src=icon, cls="w-4 h-4"),
        type="button",
        title="Toggle favorite",
        cls="""
            web_button p-1.5
            border-gray-500/30 shadow-none
            w-8 h-8
            flex items-center justify-center
            hover:bg-gray-500/20
        """,
        hx_post=f"/food/favorite/{entry_type}/{entry_id}",
        hx_swap="outerHTML",
    )


def AddButton(**attrs):
    attrs.setdefault("hx_include", "#meal_selector")
    return Button(
        "+",
        cls="""
            web_button
            rounded-lg
            border-gray-500/30 shadow-none
            hover:bg-gray-500/50
            w-8 h-8
            flex items-center justify-center
            transition-colors duration-300
            text-base
        """,
        hx_swap="none",
        **on_after(),
        **attrs,
    )


def _entry_meta(food):
    if food["entry_type"] == "catalog":
        carbs = food.get("carbs_100g")
        return f"Food · {carbs if carbs is not None else '-'} CH"
    if food["entry_type"] == "manual_intake":
        carbs = food.get("carbs_100g")
        return f"Manual · {carbs if carbs is not None else '-'} CH"
    return "Recipe"


def FoodCard(food):
    add_path = f"/add_food/{food['id']}"
    if food["entry_type"] == "manual_intake":
        add_path = f"/add_manual_intake/{food['id']}"
    if food["entry_type"] == "recipe":
        add_path = f"/add_recipe/{food['id']}"

    return Div(
        Div(
            H1(food["name"], cls="font-semibold"),
            Div(_entry_meta(food), cls="text-sm text-gray-700"),
            cls="flex flex-col gap-0.5 min-w-0",
        ),
        Div(
            FavoriteButton(food["entry_type"], food["id"], bool(food.get("favorite"))),
            AddButton(hx_post=add_path),
            cls="flex items-center gap-2 ml-3",
        ),
        cls="web_button food_entry flex items-center justify-between",
    )


def FoodList(foods):
    if not foods:
        return Div(H2("No items", cls="text-gray-500/50"), cls="flex flex-col items-center")

    return Div(
        H2("Food", cls="text-gray-500/50"),
        *[FoodCard(food) for food in foods],
        id="food-list",
        cls="flex flex-col items-center md:gap-3 lg:gap-3 gap-2 mt-4",
    )
