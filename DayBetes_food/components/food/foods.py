import json
from fasthtml.common import *

from DayBetes_food.database.queries.crud import get_cart_events
from DayBetes_food.components.cart.cart_shared import CHECKBOX_CLS
from DayBetes_food.time_utils import utc_naive_to_local


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
COOKING_OPTIONS = ["steam", "boiled-al-dente", "boiled-soft", "fried", "raw", "oven", "airfryer", "toaster", "griddle"]
CONSERVATION_OPTIONS = ["freshly-made", "fridge", "freezer", "pre-cooked"]

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


def _help_icon(help_text: str):
    return Button(
        "?",
        type="button",
        title=help_text,
        onclick=f"alert({help_text!r});",
        cls="""
            web_button rounded-full
            h-4 w-4 md:h-5 md:w-5
            text-[10px] md:text-xs
            p-0 leading-none
            flex items-center justify-center
            shadow-none
        """,
    )


def _label_with_help(text: str, help_text: str, for_id: str = ""):
    return Div(
        Label(text, cls="text-xs text-gray-700", **({"for": for_id} if for_id else {})),
        _help_icon(help_text),
        cls="flex items-center gap-1",
    )


def on_after(target="this", reload_page=True):
    reload_snippet = "setTimeout(function() { location.reload(); }, 600);" if reload_page else ""
    return {"hx-on:htmx:after-request": f"""
    var btn = {target if target == "this" else f"document.getElementById('{target}')"};
    if(!btn) return;
    if(event.detail.successful) {{
        btn.style.backgroundColor = 'rgb(74, 222, 128)';
    }} else {{
        btn.style.backgroundColor = 'rgb(248, 113, 113)';
    }}
    setTimeout(function() {{ btn.style.backgroundColor = ''; }}, 300);
    {reload_snippet}
"""}


def _close_modal_js(modal_id: str) -> str:
    return (
        f"const m=document.getElementById('{modal_id}');"
        "if(!m) return;"
        "m.classList.remove('opacity-100');"
        "m.classList.add('opacity-0','invisible','pointer-events-none');"
    )


def _open_modal_js(modal_id: str) -> str:
    return (
        f"const m=document.getElementById('{modal_id}');"
        "if(!m) return;"
        "m.classList.remove('invisible','opacity-0','pointer-events-none');"
        "m.classList.add('opacity-100');"
    )


def _food_back_button(label: str = "Back"):
    return Button(
        label,
        type="button",
        cls="web_button self-start px-3 py-1.5 text-sm",
        onclick="if(window.history.length>1){window.history.back();}else{window.location.href='/food';}",
    )


def ConfirmActionModal(modal_id: str, title: str, question: str, yes_button):
    return Div(
        Div(
            Div(
                Div(
                    P(title, cls="text-lg font-semibold"),
                    P(question, cls="text-sm md:text-base text-gray-700"),
                    cls="flex flex-col gap-1",
                ),
                Div(
                    yes_button,
                    Button(
                        "No",
                        type="button",
                        cls="web_button px-4 py-2 text-sm",
                        onclick=_close_modal_js(modal_id),
                    ),
                    cls="flex items-center gap-2 justify-end",
                ),
                onclick="event.stopPropagation()",
                cls="web_container p-5 md:p-6 rounded-3xl w-[92vw] max-w-md flex flex-col gap-4",
            ),
            id=modal_id,
            onclick=_close_modal_js(modal_id),
            cls="""
                fixed inset-0 z-[70]
                flex items-center justify-center
                bg-black/35 backdrop-blur-xl
                px-4
                opacity-0 invisible pointer-events-none
                transition-opacity duration-200
            """,
        ),
    )


def MealSelector(connection, user_id: int, selected_id: int = None):
    events = get_cart_events(connection, user_id)

    options = []
    for event in events:
        local_meal_time = utc_naive_to_local(event.get("meal_time"))
        label = event["name"] or (
            f"Meal {local_meal_time.strftime('%H:%M')}" if local_meal_time else f"Meal {event['id']}"
        )
        options.append(
            Option(
                label,
                value=str(event["id"]),
                selected=(event["id"] == selected_id),
            )
        )

    if not options:
        options = [Option("- No meals yet -", value="", cls="text-gray-500/50")]

    options.append(Option("New Meal", value="0", selected=(selected_id == 0)))

    return Div(
        Label("Meal selector", cls="text-xs text-gray-600", **{"for": "meal_selector"}),
        Select(
            *options,
            id="meal_selector",
            name="intake_event_id",
            data_skip_page_loading="true",
            aria_label="Meal selector",
            **{
                "hx-on:change": (
                    "var box=document.getElementById('meal_name_input');"
                    "var input=document.getElementById('meal_name_input_text');"
                    "if(!box||!input) return;"
                    "if(this.value==='0'){"
                    "box.classList.remove('hidden');"
                    "setTimeout(function(){input.focus();},0);"
                    "} else {"
                    "box.classList.add('hidden');"
                    "input.value='';"
                    "}"
                )
            },
            style="color: gray" if not events else "",
            cls="""
            border-[1px] px-2 py-1
            md:text-sm lg:text-sm text-xs
            shadow-sm rounded-md focus:outline-none
            lg:w-40 md:w-40 w-32
            border-white cursor-pointer
            """,
        ),
        Div(
            Div(
                Input(
                    placeholder="Meal name",
                    name="meal_name",
                    id="meal_name_input_text",
                    autofocus="autofocus" if selected_id == 0 else None,
                    data_skip_page_loading="true",
                    cls="""
                    border-[1px] px-2 py-1
                    md:text-sm lg:text-sm text-base
                    shadow-sm rounded-md focus:outline-none
                    border-gray-300 w-full
                    """,
                    hx_post="/create_named_event",
                    hx_trigger="keyup[keyCode==13]",
                    hx_target="#meal_name_input",
                    hx_swap="none",
                    hx_push_url="false",
                    hx_include="this",
                    **on_after("add_meal_btn")
                ),
                Button(
                    "Add",
                    id="add_meal_btn",
                    data_skip_page_loading="true",
                    cls="""
                    border-[1px] px-2 py-1
                    md:text-sm lg:text-sm text-xs
                    shadow-sm rounded-md cursor-pointer
                    border-gray-300 hover:bg-gray-200
                    transition-colors duration-300
                    """,
                    hx_post="/create_named_event",
                    hx_target="#meal_name_input",
                    hx_swap="none",
                    hx_push_url="false",
                    hx_include="#meal_name_input_text",
                    **on_after()
                ),
                cls="flex gap-2 w-full",
            ),
            id="meal_name_input",
            cls=f"lg:w-40 md:w-40 w-32 bg-transparent {'hidden' if selected_id != 0 else ''}",
        ),
        cls="flex items-center justify-center gap-2  md:w-md lg:w-md w-xs mb-3",
    )


def Filters():
    filters = [("Search", "all"), ("Food", "food"), ("Recipes", "recipes"), ("Favs", "favs")]
    buttons = []
    for text, value in filters:
        buttons.append(
            Button(
                text,
                cls=f"{FILTER_ITEM_CLS} {'bg-black text-white shadow-md' if value == 'all' else 'bg-transparent text-gray-700'}",
                data_food_filter_btn="true",
                data_filter_value=value,
                data_skip_page_loading="true",
                hx_get="/food/list",
                hx_target="#food-list",
                hx_swap="innerHTML",
                hx_include="#food_search_input, #food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
                **{
                    "hx-on:click": (
                        f"document.getElementById('food_filter').value='{value}';"
                        "document.querySelectorAll('[data-food-filter-btn]').forEach(function(btn){"
                        "btn.classList.remove('bg-black','text-white','shadow-md');"
                        "btn.classList.add('bg-transparent','text-gray-700');"
                        "});"
                        "this.classList.remove('bg-transparent','text-gray-700');"
                        "this.classList.add('bg-black','text-white','shadow-md');"
                        "var searchTabs=document.getElementById('food_search_tabs');"
                        "if(searchTabs){"
                        "if(this.dataset.filterValue==='all'){"
                        "searchTabs.classList.remove('hidden');"
                        "}else{"
                        "searchTabs.classList.add('hidden');"
                        "}"
                        "}"
                        "var foodTabs=document.getElementById('food_food_tabs');"
                        "if(foodTabs){"
                        "if(this.dataset.filterValue==='food'){"
                        "foodTabs.classList.remove('hidden');"
                        "}else{"
                        "foodTabs.classList.add('hidden');"
                        "}"
                        "}"
                        "var favsTabs=document.getElementById('food_favs_tabs');"
                        "if(favsTabs){"
                        "if(this.dataset.filterValue==='favs'){"
                        "favsTabs.classList.remove('hidden');"
                        "}else{"
                        "favsTabs.classList.add('hidden');"
                        "}"
                        "}"
                        "var recipesTabs=document.getElementById('food_recipes_tabs');"
                        "if(recipesTabs){"
                        "if(this.dataset.filterValue==='recipes'){"
                        "recipesTabs.classList.remove('hidden');"
                        "}else{"
                        "recipesTabs.classList.add('hidden');"
                        "}"
                        "}"
                    ),
                },
            )
        )

    return Div(
        Input(type="hidden", id="food_filter", name="filter", value="all"),
        Input(type="hidden", id="food_search_mode", name="search_mode", value="recommended"),
        Input(type="hidden", id="food_food_mode", name="food_mode", value="catalog"),
        Input(type="hidden", id="food_favs_mode", name="favs_mode", value="catalog"),
        Input(type="hidden", id="food_recipes_mode", name="recipes_mode", value="mine"),
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
        Div(
            Div(
                Button(
                    "Recommended",
                    type="button",
                    data_skip_page_loading="true",
                    data_search_mode_btn="true",
                    data_search_mode_value="recommended",
                    cls="inline-flex px-0 pb-2 text-lg font-bold text-black text-left transition-colors duration-150 cursor-pointer",
                    style="transform: translateX(0); border-bottom: 2px solid #111827;",
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include="#food_search_input, #food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
                    **{
                        "hx-on:click": (
                            "var mode='recommended';"
                            "var modeInput=document.getElementById('food_search_mode');"
                            "if(modeInput){modeInput.value=mode;}"
                            "document.querySelectorAll('[data-search-mode-btn]').forEach(function(btn){"
                            "btn.classList.remove('text-black','font-bold');"
                            "btn.classList.add('text-gray-400','font-medium');"
                            "btn.style.borderBottom='2px solid transparent';"
                            "});"
                            "this.classList.remove('text-gray-400');"
                            "this.classList.remove('font-medium');"
                            "this.classList.add('text-black','font-bold');"
                            "this.style.borderBottom='2px solid #111827';"
                        ),
                    },
                ),
                cls="w-1/2 flex items-end justify-center",
            ),
            Div(
                Button(
                    "Global",
                    type="button",
                    data_skip_page_loading="true",
                    data_search_mode_btn="true",
                    data_search_mode_value="global",
                    cls="inline-flex px-0 pb-2 text-lg font-medium text-gray-400 text-right transition-colors duration-150 cursor-pointer",
                    style="transform: translateX(0); border-bottom: 2px solid transparent;",
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include="#food_search_input, #food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
                    **{
                        "hx-on:click": (
                            "var mode='global';"
                            "var modeInput=document.getElementById('food_search_mode');"
                            "if(modeInput){modeInput.value=mode;}"
                            "document.querySelectorAll('[data-search-mode-btn]').forEach(function(btn){"
                            "btn.classList.remove('text-black','font-bold');"
                            "btn.classList.add('text-gray-400','font-medium');"
                            "btn.style.borderBottom='2px solid transparent';"
                            "});"
                            "this.classList.remove('text-gray-400');"
                            "this.classList.remove('font-medium');"
                            "this.classList.add('text-black','font-bold');"
                            "this.style.borderBottom='2px solid #111827';"
                        ),
                    },
                ),
                cls="w-1/2 flex items-end justify-center",
            ),
            id="food_search_tabs",
            cls="w-full flex items-end justify-between mt-4",
        ),
        Div(
            Div(
                Button(
                    "Catalog",
                    type="button",
                    data_skip_page_loading="true",
                    data_food_mode_btn="true",
                    data_food_mode_value="catalog",
                    cls="inline-flex px-0 pb-2 text-lg font-bold text-black text-left transition-colors duration-150 cursor-pointer",
                    style="transform: translateX(0); border-bottom: 2px solid #111827;",
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include="#food_search_input, #food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
                    **{
                        "hx-on:click": (
                            "var mode='catalog';"
                            "var modeInput=document.getElementById('food_food_mode');"
                            "if(modeInput){modeInput.value=mode;}"
                            "document.querySelectorAll('[data-food-mode-btn]').forEach(function(btn){"
                            "btn.classList.remove('text-black','font-bold');"
                            "btn.classList.add('text-gray-400','font-medium');"
                            "btn.style.borderBottom='2px solid transparent';"
                            "});"
                            "this.classList.remove('text-gray-400');"
                            "this.classList.remove('font-medium');"
                            "this.classList.add('text-black','font-bold');"
                            "this.style.borderBottom='2px solid #111827';"
                        ),
                    },
                ),
                cls="w-1/2 flex items-end justify-center",
            ),
            Div(
                Button(
                    "Manual",
                    type="button",
                    data_skip_page_loading="true",
                    data_food_mode_btn="true",
                    data_food_mode_value="manual",
                    cls="inline-flex px-0 pb-2 text-lg font-medium text-gray-400 text-right transition-colors duration-150 cursor-pointer",
                    style="transform: translateX(0); border-bottom: 2px solid transparent;",
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include="#food_search_input, #food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
                    **{
                        "hx-on:click": (
                            "var mode='manual';"
                            "var modeInput=document.getElementById('food_food_mode');"
                            "if(modeInput){modeInput.value=mode;}"
                            "document.querySelectorAll('[data-food-mode-btn]').forEach(function(btn){"
                            "btn.classList.remove('text-black','font-bold');"
                            "btn.classList.add('text-gray-400','font-medium');"
                            "btn.style.borderBottom='2px solid transparent';"
                            "});"
                            "this.classList.remove('text-gray-400');"
                            "this.classList.remove('font-medium');"
                            "this.classList.add('text-black','font-bold');"
                            "this.style.borderBottom='2px solid #111827';"
                        ),
                    },
                ),
                cls="w-1/2 flex items-end justify-center",
            ),
            id="food_food_tabs",
            cls="hidden w-full flex items-end justify-between mt-4",
        ),
        Div(
            Div(
                Button(
                    "Mine",
                    type="button",
                    data_skip_page_loading="true",
                    data_recipes_mode_btn="true",
                    data_recipes_mode_value="mine",
                    cls="inline-flex px-0 pb-2 text-lg font-bold text-black text-left transition-colors duration-150 cursor-pointer",
                    style="transform: translateX(0); border-bottom: 2px solid #111827;",
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include="#food_search_input, #food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
                    **{
                        "hx-on:click": (
                            "var mode='mine';"
                            "var modeInput=document.getElementById('food_recipes_mode');"
                            "if(modeInput){modeInput.value=mode;}"
                            "document.querySelectorAll('[data-recipes-mode-btn]').forEach(function(btn){"
                            "btn.classList.remove('text-black','font-bold');"
                            "btn.classList.add('text-gray-400','font-medium');"
                            "btn.style.borderBottom='2px solid transparent';"
                            "});"
                            "this.classList.remove('text-gray-400');"
                            "this.classList.remove('font-medium');"
                            "this.classList.add('text-black','font-bold');"
                            "this.style.borderBottom='2px solid #111827';"
                        ),
                    },
                ),
                cls="w-1/2 flex items-end justify-center",
            ),
            Div(
                Button(
                    "Discover",
                    type="button",
                    data_skip_page_loading="true",
                    data_recipes_mode_btn="true",
                    data_recipes_mode_value="discover",
                    cls="inline-flex px-0 pb-2 text-lg font-medium text-gray-400 text-right transition-colors duration-150 cursor-pointer",
                    style="transform: translateX(0); border-bottom: 2px solid transparent;",
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include="#food_search_input, #food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
                    **{
                        "hx-on:click": (
                            "var mode='discover';"
                            "var modeInput=document.getElementById('food_recipes_mode');"
                            "if(modeInput){modeInput.value=mode;}"
                            "document.querySelectorAll('[data-recipes-mode-btn]').forEach(function(btn){"
                            "btn.classList.remove('text-black','font-bold');"
                            "btn.classList.add('text-gray-400','font-medium');"
                            "btn.style.borderBottom='2px solid transparent';"
                            "});"
                            "this.classList.remove('text-gray-400');"
                            "this.classList.remove('font-medium');"
                            "this.classList.add('text-black','font-bold');"
                            "this.style.borderBottom='2px solid #111827';"
                        ),
                    },
                ),
                cls="w-1/2 flex items-end justify-center",
            ),
            id="food_recipes_tabs",
            cls="hidden w-full flex items-end justify-between mt-4",
        ),
        Div(
            Div(
                Button(
                    "Catalog",
                    type="button",
                    data_skip_page_loading="true",
                    data_favs_mode_btn="true",
                    data_favs_mode_value="catalog",
                    cls="inline-flex px-0 pb-2 text-lg font-bold text-black text-left transition-colors duration-150 cursor-pointer",
                    style="transform: translateX(0); border-bottom: 2px solid #111827;",
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include="#food_search_input, #food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
                    **{
                        "hx-on:click": (
                            "var mode='catalog';"
                            "var modeInput=document.getElementById('food_favs_mode');"
                            "if(modeInput){modeInput.value=mode;}"
                            "document.querySelectorAll('[data-favs-mode-btn]').forEach(function(btn){"
                            "btn.classList.remove('text-black','font-bold');"
                            "btn.classList.add('text-gray-400','font-medium');"
                            "btn.style.borderBottom='2px solid transparent';"
                            "});"
                            "this.classList.remove('text-gray-400');"
                            "this.classList.remove('font-medium');"
                            "this.classList.add('text-black','font-bold');"
                            "this.style.borderBottom='2px solid #111827';"
                        ),
                    },
                ),
                cls="w-1/3 flex items-end justify-center",
            ),
            Div(
                Button(
                    "Manual",
                    type="button",
                    data_skip_page_loading="true",
                    data_favs_mode_btn="true",
                    data_favs_mode_value="manual",
                    cls="inline-flex px-0 pb-2 text-lg font-medium text-gray-400 text-center transition-colors duration-150 cursor-pointer",
                    style="transform: translateX(0); border-bottom: 2px solid transparent;",
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include="#food_search_input, #food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
                    **{
                        "hx-on:click": (
                            "var mode='manual';"
                            "var modeInput=document.getElementById('food_favs_mode');"
                            "if(modeInput){modeInput.value=mode;}"
                            "document.querySelectorAll('[data-favs-mode-btn]').forEach(function(btn){"
                            "btn.classList.remove('text-black','font-bold');"
                            "btn.classList.add('text-gray-400','font-medium');"
                            "btn.style.borderBottom='2px solid transparent';"
                            "});"
                            "this.classList.remove('text-gray-400');"
                            "this.classList.remove('font-medium');"
                            "this.classList.add('text-black','font-bold');"
                            "this.style.borderBottom='2px solid #111827';"
                        ),
                    },
                ),
                cls="w-1/3 flex items-end justify-center",
            ),
            Div(
                Button(
                    "Recipes",
                    type="button",
                    data_skip_page_loading="true",
                    data_favs_mode_btn="true",
                    data_favs_mode_value="recipes",
                    cls="inline-flex px-0 pb-2 text-lg font-medium text-gray-400 text-right transition-colors duration-150 cursor-pointer",
                    style="transform: translateX(0); border-bottom: 2px solid transparent;",
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include="#food_search_input, #food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
                    **{
                        "hx-on:click": (
                            "var mode='recipes';"
                            "var modeInput=document.getElementById('food_favs_mode');"
                            "if(modeInput){modeInput.value=mode;}"
                            "document.querySelectorAll('[data-favs-mode-btn]').forEach(function(btn){"
                            "btn.classList.remove('text-black','font-bold');"
                            "btn.classList.add('text-gray-400','font-medium');"
                            "btn.style.borderBottom='2px solid transparent';"
                            "});"
                            "this.classList.remove('text-gray-400');"
                            "this.classList.remove('font-medium');"
                            "this.classList.add('text-black','font-bold');"
                            "this.style.borderBottom='2px solid #111827';"
                        ),
                    },
                ),
                cls="w-1/3 flex items-end justify-center",
            ),
            id="food_favs_tabs",
            cls="hidden w-full flex items-end justify-between mt-4",
        ),
        cls="md:w-md lg:w-md w-xs transition-all",
    )


def SearchInput():
    return Input(
        inputmode="text",
        placeholder="What did you eat?",
        name="search",
        id="food_search_input",
        data_skip_page_loading="true",
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
        hx_trigger="keyup changed delay:500ms",
        hx_include="#food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode",
        hx_swap="innerHTML",
    )


def RecipeIngredientSearchInput(recipe_id: int):
    return Input(
        inputmode="text",
        placeholder="Search food to add",
        name="search",
        id="recipe_ingredient_search_input",
        data_skip_page_loading="true",
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
        hx_get=f"/food/recipe/{recipe_id}/ingredients/list",
        hx_target="#recipe-ingredient-list",
        hx_trigger="keyup changed delay:300ms",
        hx_swap="innerHTML",
    )


def _labeled_input(
    label: str,
    name: str,
    typ: str = "text",
    placeholder: str = "",
    help_text: str = "",
    step: str = "",
    value: str | None = None,
    select_on_click: bool = True,
    input_style: str = "",
):
    help_value = help_text or f"What to enter in {label}"
    input_id = f"field_{name}"
    return Div(
        _label_with_help(label, help_value, for_id=input_id),
        Input(
            type=typ,
            id=input_id,
            name=name,
            placeholder=placeholder,
            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-base mr-1",
            style=input_style,
            **({"onclick": "this.select()"} if select_on_click else {}),
            **({"step": step} if step else {}),
            **({"value": value} if value is not None else {}),
        ),
        cls="flex flex-col gap-1",
    )


def _tag_badge_style(tag_name: str) -> str:
    text = (tag_name or "").strip().lower()
    hue = 0
    for ch in text:
        hue = (hue * 31 + ord(ch)) % 360
    return (
        f"background:hsl({hue} 80% 90%);"
        f"border-color:hsl({hue} 70% 55%);"
        f"color:hsl({hue} 55% 28%);"
    )


def _tags_multiselect_input(
    tag_options: list[str] | None = None,
    selected_tags: list[str] | None = None,
    *,
    label: str = "Tags",
    field_name: str = "tags_json",
    input_style: str = "",
):
    options = sorted({(x or "").strip() for x in (tag_options or []) if (x or "").strip()})
    selected = []
    seen = set()
    for raw in (selected_tags or []):
        clean = " ".join((raw or "").strip().split())
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            selected.append(clean)
    input_id = f"field_{field_name}_picker"
    return Div(
        _label_with_help(label, "Select one or more tags. You can add new ones with Add.", for_id=input_id),
        Div(
            Input(type="hidden", name=field_name, value=json.dumps(selected, ensure_ascii=True), data_tags_hidden="true"),
            Input(
                type="text",
                id=input_id,
                data_tags_input="true",
                placeholder="Type to search tags",
                autocomplete="off",
                cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-base mr-1",
                style=input_style,
            ),
            Div(
                data_tags_suggestions="true",
                cls="absolute left-0 right-0 top-full mt-1 z-[70] rounded-md border border-gray-200 bg-white shadow-lg overflow-hidden",
                style="display:none;background:#fff;backdrop-filter:none;z-index:70;",
            ),
            Div(
                *[
                    Div(
                        Span(tag, cls="text-xs font-semibold"),
                        Button("x", type="button", data_tags_remove=tag, cls="ml-1 text-xs font-bold"),
                        data_tags_chip=tag,
                        cls="inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs",
                        style=_tag_badge_style(tag),
                    )
                    for tag in selected
                ],
                data_tags_chips="true",
                cls="mt-2 flex flex-wrap gap-1.5",
            ),
            data_tags_multiselect="true",
            data_tags_options=json.dumps(options, ensure_ascii=True),
            data_tags_suggest_url="/food/tags/suggestions",
            cls="relative",
        ),
        cls="flex flex-col gap-1 col-span-1 md:col-span-2",
    )


def _searchable_autocomplete_input(
    label: str,
    name: str,
    options: list[str] | None = None,
    help_text: str = "",
    placeholder: str = "",
    allow_add: bool = True,
    value: str | None = None,
    case_mode: str = "lower",
):
    normalized_options = sorted({(opt or "").strip() for opt in (options or []) if (opt or "").strip()})
    options_json = json.dumps(normalized_options)
    placeholder_value = placeholder or f"Type {label.lower()}"
    help_value = help_text or f"Search and select {label.lower()}."
    input_id = f"field_{name}"
    return Div(
        _label_with_help(label, help_value, for_id=input_id),
        Div(
            (Input(type="hidden", name=f"{name}__added", value="0", data_searchable_added_flag="true") if allow_add else None),
            Input(
                type="text",
                id=input_id,
                name=name,
                data_searchable_input="true",
                placeholder=placeholder_value,
                autocomplete="off",
                cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-base mr-1",
                onclick="this.select()",
                **({"value": value} if value is not None else {}),
            ),
            Div(
                data_searchable_suggestions="true",
                cls="""
                    absolute left-0 right-0 top-full mt-1 z-[70]
                    rounded-md border border-gray-200
                    bg-white opacity-100 shadow-lg
                    overflow-hidden
                """,
                style="display:none;background:#fff;backdrop-filter:none;z-index:70;",
            ),
            data_searchable_autocomplete="true",
            data_searchable_options=options_json,
            data_searchable_allow_add="1" if allow_add else "0",
            data_searchable_case_mode=case_mode,
            cls="relative",
        ),
        cls="flex flex-col gap-1",
    )


def _searchable_compact_input(
    name: str,
    options: list[str] | None = None,
    value: str | None = None,
    placeholder: str = "",
    allow_add: bool = False,
    autosave: bool = False,
):
    normalized_options = sorted({(opt or "").strip() for opt in (options or []) if (opt or "").strip()})
    options_json = json.dumps(normalized_options)
    return Div(
        (Input(type="hidden", name=f"{name}__added", value="0", data_searchable_added_flag="true") if allow_add else None),
        Input(
            type="text",
            name=name,
            data_searchable_input="true",
            placeholder=placeholder or "Search",
            autocomplete="off",
            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-base w-full min-w-0",
            **(
                {
                    "oninput": (
                        "if(!this.form) return;"
                        "clearTimeout(this._dbAutoSaveTimer);"
                        "this._dbAutoSaveTimer=setTimeout(()=>{if(this.form) htmx.trigger(this.form,'submit');},350);"
                    ),
                    "onblur": "if(this.form) htmx.trigger(this.form,'submit');",
                    "onchange": "if(this.form) htmx.trigger(this.form,'submit');",
                }
                if autosave
                else {}
            ),
            **({"value": value} if value is not None else {}),
        ),
        Div(
            data_searchable_suggestions="true",
            cls="""
                absolute left-0 right-0 top-full mt-1 z-[200]
                rounded-md border border-gray-200
                bg-white opacity-100 shadow-lg
                overflow-hidden
            """,
            style="display:none;background:#fff;backdrop-filter:none;z-index:200;",
        ),
        data_searchable_autocomplete="true",
        data_searchable_options=options_json,
        data_searchable_allow_add="1" if allow_add else "0",
        cls="relative w-full min-w-0",
    )


def _brand_autocomplete_input(brand_options: list[str] | None = None, value: str | None = None):
    return _searchable_autocomplete_input(
        label="Brand",
        name="brand",
        options=brand_options,
        help_text="Brand or manufacturer name.",
        placeholder="Type brand",
        allow_add=True,
        value=value,
        case_mode="title",
    )


def _searchable_autocomplete_bootstrap_script():
    return Script(
        """
        (function () {
          if (window.__dbSearchableAutocompleteBootstrapped) return;
          window.__dbSearchableAutocompleteBootstrapped = true;

          function normalize(v) { return String(v || "").trim(); }
          function storageKeyFor(input) {
            if (!input) return "";
            var form = input.form;
            var action = form && form.getAttribute ? (form.getAttribute("hx-post") || form.getAttribute("action") || "") : "";
            return "dbSearchableValue::" + window.location.pathname + window.location.search + "::" + (input.name || "") + "::" + action;
          }
          function persistValue(input) {
            if (!input || !window.localStorage) return;
            var key = storageKeyFor(input);
            if (!key) return;
            window.localStorage.setItem(key, String(input.value || ""));
          }
          function restoreValue(input) {
            if (!input || !window.localStorage) return;
            var key = storageKeyFor(input);
            if (!key) return;
            var saved = window.localStorage.getItem(key);
            if (saved == null) return;
            if (!normalize(input.value)) {
              input.value = saved;
            }
          }
          function escapeHtml(v) {
            return String(v || "")
              .replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#39;");
          }

          function bindOne(root) {
            if (!root || root.dataset.searchableBound === "1") return;
            root.dataset.searchableBound = "1";

            var input = root.querySelector("[data-searchable-input='true']");
            var box = root.querySelector("[data-searchable-suggestions='true']");
            var addedFlag = root.querySelector("[data-searchable-added-flag='true']");
            if (!input || !box) return;

            var options = [];
            try { options = JSON.parse(root.dataset.searchableOptions || "[]"); }
            catch (_) { options = []; }
            var allowAdd = root.dataset.searchableAllowAdd === "1";
            var caseMode = root.dataset.searchableCaseMode || "lower";
            restoreValue(input);

            function formatByCaseMode(v) {
              var text = normalize(v);
              if (!text) return "";
              if (caseMode === "title") {
                var words = text.toLowerCase().split(/\\s+/);
                for (var i = 0; i < words.length; i += 1) {
                  var w = words[i];
                  if (!w) continue;
                  words[i] = w.charAt(0).toUpperCase() + w.slice(1);
                }
                return words.join(" ");
              }
              return text.toLowerCase();
            }

            function closeBox() {
              box.style.display = "none";
              box.innerHTML = "";
              root.style.zIndex = "";
            }

            function setAddedFlag(value) {
              if (!addedFlag) return;
              addedFlag.value = value ? "1" : "0";
            }

            function similarityScore(nameLower, qLower) {
              if (!qLower) return 0;
              if (nameLower === qLower) return 1000;
              if (nameLower.indexOf(qLower) === 0) return 800;
              if (nameLower.indexOf(qLower) !== -1) return 600;

              var qSet = new Set(qLower.split(""));
              var nSet = new Set(nameLower.split(""));
              var inter = 0;
              qSet.forEach(function (ch) { if (nSet.has(ch)) inter += 1; });
              var union = new Set([].concat(Array.from(qSet), Array.from(nSet))).size || 1;
              return Math.floor((inter / union) * 300);
            }

            function render() {
              var q = normalize(input.value);
              var qLower = q.toLowerCase();
              var matches = [];

              for (var i = 0; i < options.length; i += 1) {
                var name = normalize(options[i]);
                if (!name) continue;
                var lower = name.toLowerCase();
                var score = similarityScore(lower, qLower);
                if (!q || score > 0) matches.push({ name: name, score: score });
              }

              matches.sort(function (a, b) {
                if (b.score !== a.score) return b.score - a.score;
                return a.name.localeCompare(b.name);
              });

              var rows = [];
              for (var j = 0; j < matches.length; j += 1) {
                var label = matches[j].name;
                var safe = escapeHtml(label);
                rows.push(
                  "<li class='border-b border-gray-200'>" +
                  "<button type='button' data-searchable-pick='" +
                  safe +
                  "' class='w-full text-left px-3 py-2 bg-white hover:bg-gray-200 text-sm text-gray-800 transition-colors'>" +
                  safe +
                  "</button></li>"
                );
              }

              var exactExists = options.some(function (x) {
                return normalize(x).toLowerCase() === qLower;
              });

              if (allowAdd && q && !exactExists) {
                rows.push(
                  "<li class='border-b border-gray-200'>" +
                  "<button type='button' data-searchable-add='true' class='w-full text-left px-3 py-2 bg-white hover:bg-gray-200 text-sm font-semibold text-gray-800 transition-colors'>Add: '" +
                  escapeHtml(q) +
                  "'</button></li>"
                );
              }

              if (rows.length) {
                box.innerHTML = (
                  "<div data-searchable-scroll='true' class='p-0 max-h-44 overflow-y-auto' " +
                  "style='-webkit-overflow-scrolling:touch;overscroll-behavior:contain;touch-action:pan-y;'>" +
                  "<ul>" + rows.join("") + "</ul></div>"
                );
                var items = box.querySelectorAll("li");
                if (items.length > 0) items[items.length - 1].classList.remove("border-b", "border-gray-200");
                var scrollArea = box.querySelector("[data-searchable-scroll='true']");
                if (scrollArea) {
                  scrollArea.addEventListener("wheel", function (ev) { ev.stopPropagation(); }, { passive: true });
                  scrollArea.addEventListener("touchmove", function (ev) { ev.stopPropagation(); }, { passive: true });
                }
                root.style.zIndex = "80";
              } else {
                box.innerHTML = "";
                root.style.zIndex = "";
              }
              box.style.display = rows.length ? "block" : "none";
            }

            box.addEventListener("click", function (ev) {
              var target = ev.target;
              if (!target) return;
              if (target.dataset && target.dataset.searchableAdd === "true") {
                var q = normalize(input.value);
                if (!q) return;
                var qLower = q.toLowerCase();
                var exists = options.some(function (x) { return normalize(x).toLowerCase() === qLower; });
                var formatted = formatByCaseMode(q);
                if (!exists) options.push(formatted);
                input.value = formatted;
                setAddedFlag(true);
                persistValue(input);
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
                input.dispatchEvent(new CustomEvent("db-searchable-commit", { bubbles: true }));
                setAddedFlag(true);
                closeBox();
                return;
              }
              var pick = target.dataset ? target.dataset.searchablePick : "";
              if (pick) {
                input.value = pick;
                setAddedFlag(false);
                persistValue(input);
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
                input.dispatchEvent(new CustomEvent("db-searchable-commit", { bubbles: true }));
                closeBox();
              }
            });

            input.addEventListener("focus", render);
            input.addEventListener("input", function () {
              setAddedFlag(false);
              persistValue(input);
              render();
            });
            input.addEventListener("change", function () { persistValue(input); });
            input.addEventListener("keydown", function (ev) {
              if (ev.key === "Escape") closeBox();
            });
            document.addEventListener("click", function (ev) {
              var target = ev.target;
              if (!root.contains(target)) {
                closeBox();
                return;
              }
              if (target !== input && !box.contains(target)) {
                closeBox();
              }
            });
          }

          function bindAll() {
            var roots = document.querySelectorAll("[data-searchable-autocomplete='true']");
            for (var i = 0; i < roots.length; i += 1) bindOne(roots[i]);
          }

          if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", bindAll);
          } else {
            bindAll();
          }
          document.body.addEventListener("htmx:afterSwap", bindAll);
        })();
        """
    )


def _tags_multiselect_bootstrap_script():
    return Script(
        """
        (function () {
          if (window.__dbTagsMultiBootstrappedV4) return;
          window.__dbTagsMultiBootstrappedV4 = true;

          function norm(v) { return String(v || "").trim().replace(/\\s+/g, " "); }
          function fold(v) {
            var text = norm(v).toLowerCase();
            try {
              return text.normalize("NFD").replace(/[\\u0300-\\u036f]/g, "");
            } catch (_) {
              return text;
            }
          }
          function esc(v) {
            return String(v || "")
              .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
          }
          function hue(tag) {
            var s = String(tag || "").toLowerCase();
            var h = 0;
            for (var i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) % 360;
            return h;
          }
          function chipStyle(tag) {
            var h = hue(tag);
            return "background:hsl(" + h + " 80% 90%);border-color:hsl(" + h + " 70% 55%);color:hsl(" + h + " 55% 28%);";
          }
          function parseHidden(hidden) {
            try {
              var arr = JSON.parse(hidden.value || "[]");
              if (!Array.isArray(arr)) return [];
              return arr.map(norm).filter(Boolean);
            } catch (_) { return []; }
          }
          function writeHidden(hidden, arr) {
            hidden.value = JSON.stringify(arr);
            hidden.dispatchEvent(new Event("input", { bubbles: true }));
            hidden.dispatchEvent(new Event("change", { bubbles: true }));
          }
          function readKnown() {
            try {
              var raw = window.localStorage ? window.localStorage.getItem("dbKnownTags") : null;
              var arr = raw ? JSON.parse(raw) : [];
              return Array.isArray(arr) ? arr.map(norm).filter(Boolean) : [];
            } catch (_) { return []; }
          }
          function writeKnown(values) {
            try {
              if (!window.localStorage) return;
              var seen = {};
              var out = [];
              for (var i = 0; i < values.length; i += 1) {
                var v = norm(values[i]);
                var k = v.toLowerCase();
                if (!v || seen[k]) continue;
                seen[k] = true;
                out.push(v);
              }
              window.localStorage.setItem("dbKnownTags", JSON.stringify(out));
            } catch (_) {}
          }
          function bindOne(root) {
            if (!root || root.dataset.tagsBound === "1") return;
            root.dataset.tagsBound = "1";
            var input = root.querySelector("[data-tags-input='true']");
            var box = root.querySelector("[data-tags-suggestions='true']");
            var hidden = root.querySelector("[data-tags-hidden='true']");
            var chips = root.querySelector("[data-tags-chips='true']");
            if (!input || !box || !hidden || !chips) return;
            var options = [];
            try { options = JSON.parse(root.dataset.tagsOptions || "[]"); } catch (_) { options = []; }
            options = options.concat(readKnown());
            var suggestUrl = root.dataset.tagsSuggestUrl || "";
            var selected = parseHidden(hidden);
            function mergeOptions(items) {
              if (!Array.isArray(items)) return;
              var seen = {};
              for (var i = 0; i < options.length; i += 1) {
                var ok = norm(options[i]).toLowerCase();
                if (ok) seen[ok] = true;
              }
              for (var j = 0; j < items.length; j += 1) {
                var clean = norm(items[j]);
                var key = clean.toLowerCase();
                if (!clean || seen[key]) continue;
                seen[key] = true;
                options.push(clean);
              }
            }
            function refreshOptions(q, done) {
              if (done) done();
              if (!suggestUrl) return;
              var url = suggestUrl + "?q=" + encodeURIComponent(q || "");
              fetch(url, { credentials: "same-origin" })
                .then(function (res) { return res.ok ? res.json() : null; })
                .then(function (payload) {
                  if (payload && Array.isArray(payload.tags)) {
                    mergeOptions(payload.tags);
                    if (done) done();
                  }
                })
                .catch(function () {});
            }
            function selectedSet() {
              var s = {};
              for (var i = 0; i < selected.length; i += 1) s[fold(selected[i])] = true;
              return s;
            }
            function syncChips() {
              chips.innerHTML = "";
              for (var i = 0; i < selected.length; i += 1) {
                var tag = selected[i];
                var safe = esc(tag);
                chips.insertAdjacentHTML("beforeend",
                  "<div data-tags-chip='" + safe + "' class='inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs' style='" + chipStyle(tag) + "'>" +
                  "<span class='text-xs font-semibold'>" + safe + "</span>" +
                  "<button type='button' data-tags-remove='" + safe + "' class='ml-1 text-xs font-bold'>x</button>" +
                  "</div>"
                );
              }
              writeHidden(hidden, selected);
              writeKnown(options.concat(selected));
            }
            function closeBox() { box.style.display = "none"; box.innerHTML = ""; root.style.zIndex = ""; }
            function render() {
              var qRaw = norm(input.value);
              var q = fold(qRaw);
              var rows = [];
              var sel = selectedSet();
              var shown = 0;
              for (var i = 0; i < options.length; i += 1) {
                var name = norm(options[i]);
                if (!name || sel[fold(name)]) continue;
                if (q && fold(name).indexOf(q) === -1) continue;
                var safe = esc(name);
                rows.push("<li class='border-b border-gray-200'><button type='button' data-tags-pick='" + safe + "' class='w-full text-left px-3 py-2 bg-white hover:bg-gray-200 text-sm text-gray-800'>" + safe + "</button></li>");
                shown += 1;
                if (shown >= 12) break;
              }
              var exactExists = options.some(function (x) { return fold(x) === q; });
              if (q && !exactExists && !sel[q]) {
                rows.push("<li class='border-b border-gray-200'><button type='button' data-tags-add='true' class='w-full text-left px-3 py-2 bg-white hover:bg-gray-200 text-sm font-semibold text-gray-800'>Add: '" + esc(qRaw) + "'</button></li>");
              }
              if (!rows.length) { closeBox(); return; }
              box.innerHTML = "<div class='p-0 max-h-44 overflow-y-auto'><ul>" + rows.join("") + "</ul></div>";
              box.style.display = "block";
              root.style.zIndex = "80";
            }
            box.addEventListener("click", function (ev) {
              var t = ev.target;
              if (!t || !t.closest) return;
              var pickBtn = t.closest("[data-tags-pick]");
              if (pickBtn && box.contains(pickBtn)) {
                var clean = norm(pickBtn.getAttribute("data-tags-pick"));
                if (clean && !selectedSet()[fold(clean)]) selected.push(clean);
                if (!options.some(function (x) { return fold(x) === fold(clean); })) options.push(clean);
                input.value = "";
                syncChips();
                closeBox();
                return;
              }
              var addBtn = t.closest("[data-tags-add='true']");
              if (addBtn && box.contains(addBtn)) {
                var add = norm(input.value);
                if (!add) return;
                if (!selectedSet()[fold(add)]) selected.push(add);
                if (!options.some(function (x) { return fold(x) === fold(add); })) options.push(add);
                input.value = "";
                syncChips();
                closeBox();
              }
            });
            chips.addEventListener("click", function (ev) {
              var t = ev.target;
              if (!t || !t.closest) return;
              var removeBtn = t.closest("[data-tags-remove]");
              if (!removeBtn || !chips.contains(removeBtn)) return;
              var rem = fold(removeBtn.getAttribute("data-tags-remove"));
              selected = selected.filter(function (x) { return fold(x) !== rem; });
              syncChips();
            });
            input.addEventListener("focus", function () {
              render();
              refreshOptions("", render);
            });
            input.addEventListener("input", function () {
              render();
              refreshOptions(norm(input.value), render);
            });
            input.addEventListener("blur", function () {
              setTimeout(function () {
                if (!root.contains(document.activeElement)) closeBox();
              }, 0);
            });
            input.addEventListener("keydown", function (ev) { if (ev.key === "Escape") closeBox(); });
            document.addEventListener("mousedown", function (ev) {
              if (!root.contains(ev.target)) closeBox();
            });
            document.addEventListener("click", function (ev) {
              if (!root.contains(ev.target)) closeBox();
            });
            render();
            refreshOptions("", render);
            syncChips();
          }
          function bindAll(scope) {
            var root = scope || document;
            var nodes = root.querySelectorAll("[data-tags-multiselect='true']");
            for (var i = 0; i < nodes.length; i += 1) bindOne(nodes[i]);
          }
          if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { bindAll(document); });
          else bindAll(document);
          document.body.addEventListener("htmx:afterSwap", function (event) {
            var target = event && event.detail ? event.detail.target : null;
            bindAll(target || document);
          });
        })();
        """
    )


def _form_draft_bootstrap_script():
    return Script(
        """
        (function () {
          if (window.__dbFoodFormDraftsBootstrapped) return;
          window.__dbFoodFormDraftsBootstrapped = true;

          function byName(form, name) {
            var all = form.querySelectorAll("input[name], select[name], textarea[name]");
            var result = [];
            for (var i = 0; i < all.length; i += 1) {
              if (all[i].name === name) result.push(all[i]);
            }
            return result;
          }

          function saveForm(form) {
            var key = form.getAttribute("data-draft-key");
            if (!key || !window.localStorage) return;
            var fields = form.querySelectorAll("input[name], select[name], textarea[name]");
            var payload = {};
            for (var i = 0; i < fields.length; i += 1) {
              var el = fields[i];
              if (!el || el.disabled) continue;
              var type = (el.type || "").toLowerCase();
              if (type === "submit" || type === "button" || type === "reset" || type === "file" || type === "image") continue;
              var name = el.name;
              if (!name) continue;
              if (type === "checkbox") {
                payload[name] = !!el.checked;
              } else if (type === "radio") {
                if (el.checked) payload[name] = el.value;
              } else {
                payload[name] = el.value;
              }
            }
            try {
              window.localStorage.setItem(key, JSON.stringify(payload));
            } catch (_) {}
          }

          function restoreForm(form) {
            var key = form.getAttribute("data-draft-key");
            if (!key || !window.localStorage) return;
            var raw = null;
            try { raw = window.localStorage.getItem(key); } catch (_) {}
            if (!raw) return;
            var data = null;
            try { data = JSON.parse(raw); } catch (_) { return; }
            if (!data || typeof data !== "object") return;

            var names = Object.keys(data);
            for (var i = 0; i < names.length; i += 1) {
              var name = names[i];
              var value = data[name];
              var fields = byName(form, name);
              for (var j = 0; j < fields.length; j += 1) {
                var el = fields[j];
                if (!el || el.disabled) continue;
                var type = (el.type || "").toLowerCase();
                if (type === "checkbox") {
                  if (!el.checked) el.checked = !!value;
                } else if (type === "radio") {
                  if (!el.checked) el.checked = String(el.value) === String(value);
                } else if (value != null) {
                  if (!String(el.value || "").trim()) {
                    el.value = String(value);
                  }
                }
              }
            }
          }

          function bindForm(form) {
            if (!form || form.dataset.draftBound === "1") return;
            form.dataset.draftBound = "1";
            restoreForm(form);
            form.addEventListener("focusout", function () { saveForm(form); });
            form.addEventListener("change", function () { saveForm(form); });
            form.addEventListener("input", function () { saveForm(form); });
            form.addEventListener("submit", function () { saveForm(form); });
          }

          function bindAll(scope) {
            var root = scope || document;
            var forms = root.querySelectorAll("form[data-draft-key]");
            for (var i = 0; i < forms.length; i += 1) bindForm(forms[i]);
          }

          if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", function () { bindAll(document); });
          } else {
            bindAll(document);
          }
          document.body.addEventListener("htmx:afterSwap", function (event) {
            var target = event && event.detail ? event.detail.target : null;
            bindAll(target || document);
          });
        })();
        """
    )


def RecipeMacrosGrid(recipe_id: int, per100: dict, total_amount: float):
    return Div(
        *_detail_macro_tiles(per100, total_amount),
        id=f"food_detail_recipe_{recipe_id}_macros",
        cls="grid grid-cols-2 md:grid-cols-3 gap-2",
    )


def _labeled_select(label: str, name: str, options: list[str], help_text: str = "", selected_value: str = ""):
    help_value = help_text or f"What to select in {label}"
    select_id = f"field_{name}"
    return Div(
        _label_with_help(label, help_value, for_id=select_id),
        Select(
            Option("-", value="", selected=(selected_value == "")),
            *[Option(opt, value=opt, selected=(opt == selected_value)) for opt in options],
            id=select_id,
            name=name,
            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-xs mr-1",
        ),
        cls="flex flex-col gap-1",
    )


def _favorite_checkbox(name: str = "favorite", checked: bool = True, centered: bool = False):
    checkbox_id = f"field_{name}"
    return Div(
        Label(
            Input(
                type="checkbox",
                id=checkbox_id,
                name=name,
                value="true",
                checked=checked,
                cls=CHECKBOX_CLS,
            ),
            Span(
                Svg(
                    Path(
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z",
                        fill_rule="evenodd",
                        clip_rule="evenodd",
                    ),
                    xmlns="http://www.w3.org/2000/svg",
                    cls="h-3.5 w-3.5",
                    viewBox="0 0 20 20",
                    fill="currentColor",
                    stroke="currentColor",
                    stroke_width="1",
                ),
                cls="""
                    absolute text-white opacity-0 peer-checked:opacity-100
                    top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2
                    pointer-events-none
                """,
            ),
            cls="flex items-center cursor-pointer relative h-5 w-5",
        ),
        Label("Favorite", cls="text-xs text-gray-700 cursor-pointer", **{"for": checkbox_id}),
        _help_icon("Mark as favorite so it appears highlighted and in Favs filter."),
        cls=(
            "flex items-center justify-center gap-2 col-span-1 md:col-span-2"
            if centered
            else "flex items-center justify-end gap-2 col-span-1 md:col-span-2"
        ),
    )


def _private_checkbox(name: str = "is_private", checked: bool = False, centered: bool = False):
    checkbox_id = f"field_{name}"
    return Div(
        Label(
            Input(
                type="checkbox",
                id=checkbox_id,
                name=name,
                value="true",
                checked=checked,
                cls=CHECKBOX_CLS,
            ),
            Span(
                Svg(
                    Path(
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z",
                        fill_rule="evenodd",
                        clip_rule="evenodd",
                    ),
                    xmlns="http://www.w3.org/2000/svg",
                    cls="h-3.5 w-3.5",
                    viewBox="0 0 20 20",
                    fill="currentColor",
                    stroke="currentColor",
                    stroke_width="1",
                ),
                cls="""
                    absolute text-white opacity-0 peer-checked:opacity-100
                    top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2
                    pointer-events-none
                """,
            ),
            cls="flex items-center cursor-pointer relative h-5 w-5",
        ),
        Label("Private", cls="text-xs text-gray-700 cursor-pointer", **{"for": checkbox_id}),
        _help_icon("If enabled, only you can see this item. If disabled, everyone can see it."),
        cls=(
            "flex items-center justify-center gap-2 col-span-1 md:col-span-2"
            if centered
            else "flex items-center justify-end gap-2 col-span-1 md:col-span-2"
        ),
    )


def _create_flags_row(favorite_checked: bool = True, private_checked: bool = False):
    return Div(
        _favorite_checkbox(checked=favorite_checked, centered=True),
        _private_checkbox(checked=private_checked, centered=True),
        cls="col-span-1 md:col-span-2 flex items-center justify-between gap-2",
    )


def _smart_macros_block(prefix: str, prefill: dict | None = None):
    prefill = prefill or {}
    def _mv(key: str):
        value = prefill.get(key)
        if value is None or value == "":
            return ""
        return str(value)
    def _smart_prefill_text():
        calories = prefill.get("calories_100g")
        carbs = prefill.get("carbs_100g")
        sugars = prefill.get("sugars_100g")
        proteins = prefill.get("proteins_100g")
        fats = prefill.get("fats_100g")
        saturated = prefill.get("saturated_100g")
        fiber = prefill.get("fiber_100g")
        parts = []
        if calories not in (None, ""):
            parts.append(f"{calories}kcal")
        if carbs not in (None, ""):
            parts.append(f"{carbs}hc")
        if sugars not in (None, ""):
            parts.append(f"{sugars}az")
        if proteins not in (None, ""):
            parts.append(f"{proteins}prot")
        if fats not in (None, ""):
            parts.append(f"{fats}grasas")
        if saturated not in (None, ""):
            parts.append(f"{saturated}sat")
        if fiber not in (None, ""):
            parts.append(f"{fiber}fibra")
        return " ".join(parts)
    input_id = f"{prefix}_smart_macros_input"
    output_id = f"{prefix}_smart_macros_output"
    return Div(
        _label_with_help(
            "Smart macros (per 100g/ml)",
            (
                "Write macros in free text. Examples: '120kcal 30hc 12az 20prot 10 grasas 3 sat 5 fibra', "
                "'carbs 30g proteins 20g'. Synonyms accepted: hc/ch/hidratos/carbos, "
                "prote/prot/proteina, grasas/gr/grasa, sat/saturadas/st/gs, fibra/fb, az/azucar, kcal/cal."
            ),
            for_id=input_id,
        ),
        Input(
            type="text",
            id=input_id,
            name=f"{prefix}_smart_macros_raw",
            placeholder="Ej: 120kcal, 30hc, 12az, 20prot, 10 grasas, 3 sat, 5 fibra",
            data_smart_macros="true",
            data_smart_macros_output=f"#{output_id}",
            data_smart_macros_prefix=prefix,
            oninput="dbSmartMacrosSync(this)",
            onchange="dbSmartMacrosSync(this)",
            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-base",
            value=_smart_prefill_text(),
        ),
        Div(
            "Escribe macros para ver la deteccion." if not _smart_prefill_text() else "Imported from barcode data.",
            id=output_id,
            cls="text-xs text-gray-700 min-h-5",
        ),
        Input(type="hidden", name=f"{prefix}_smart_macros_enabled", value="1"),
        # Hidden fields populated by Smart Macros parser
        Input(type="hidden", name="calories_100g", id=f"{prefix}_calories_100g", value=_mv("calories_100g")),
        Input(type="hidden", name="carbs_100g", id=f"{prefix}_carbs_100g", value=_mv("carbs_100g")),
        Input(type="hidden", name="sugars_100g", id=f"{prefix}_sugars_100g", value=_mv("sugars_100g")),
        Input(type="hidden", name="proteins_100g", id=f"{prefix}_proteins_100g", value=_mv("proteins_100g")),
        Input(type="hidden", name="fats_100g", id=f"{prefix}_fats_100g", value=_mv("fats_100g")),
        Input(type="hidden", name="saturated_100g", id=f"{prefix}_saturated_100g", value=_mv("saturated_100g")),
        Input(type="hidden", name="fiber_100g", id=f"{prefix}_fiber_100g", value=_mv("fiber_100g")),
        cls="flex flex-col gap-1 col-span-1 md:col-span-2",
    )


def _advanced_toggle(section_id: str):
    return Div(
        Button(
            "Advanced",
            type="button",
            cls="web_button px-2 py-1 text-xs w-fit",
            onclick=(
                f"const el=document.getElementById('{section_id}');"
                "if(!el) return;"
                "el.classList.toggle('hidden');"
            ),
        ),
        cls="col-span-1 md:col-span-2",
    )


def QuickCreateButtons():
    menu_button_cls = """
        web_button
        h-12 w-12 md:h-14 md:w-14 p-3 md:p-4
        rounded-3xl md:rounded-4xl
        bg-[#f6f2eb]/50 backdrop-blur-lg
        border border-white/80
        shadow-md
        flex items-center justify-center
        transition-transform duration-150
        hover:scale-[1.04] z-[130]
        active:scale-95
    """
    menu_panel_cls = """
        absolute top-full right-0 z-[9999] mt-3
        w-[min(52vw,calc(100vw-1.5rem))]
        min-w-[24rem]
        rounded-3xl
        border border-white/80
        shadow-lg
        ring-1 ring-inset ring-white/20
        p-3
        grid grid-cols-2 gap-2
        auto-rows-fr
    """
    option_button_cls = """
        web_button w-full h-full min-h-0 px-3 py-3 rounded-[1.1rem]
        text-left shadow-none z-[130]
        flex flex-col items-start justify-between gap-1
    """
    power_panel_cls = """
        absolute top-full left-0 z-[9999] mt-3
        w-[min(24rem,calc(100vw-1.5rem))]
        min-w-[18rem]
        rounded-3xl
        border border-white/80
        shadow-lg
        ring-1 ring-inset ring-white/20
        p-3
    """
    return Div(
        Div(
            Div(
                Button(
                    Img(src="/images/content/power_icon.svg", alt="", cls="h-6 w-6"),
                    type="button",
                    aria_label="Open power menu",
                    cls=menu_button_cls,
                    id="food_power_toggle",
                    aria_controls="food_power_menu",
                    aria_expanded="false",
                ),
                Div(
                    Form(
                        Input(type="hidden", name="entry_type", id="rescue_entry_type"),
                        Input(type="hidden", name="entry_id", id="rescue_entry_id"),
                        Input(type="hidden", name="consumed_g", id="rescue_consumed_g", value="0"),
                        Input(type="hidden", id="rescue_serving_g", value="100"),
                        Input(type="hidden", id="rescue_available_g", value="0"),
                        Div(
                            Span("Rescue item", cls="text-[11px] text-gray-600"),
                            Input(
                                id="rescue_search_input",
                                name="q",
                                type="text",
                                placeholder="Search rescue",
                                autocomplete="off",
                                cls="web_input bg-white/70 rounded-lg border border-gray-300 px-2 py-1 text-sm",
                            ),
                            Div(
                                id="rescue_selected_label",
                                cls="text-[11px] text-gray-700 min-h-[1rem]",
                            ),
                            Div(
                                id="rescue_picker_results",
                                hx_get="/food/rescue/options",
                                hx_trigger="load, keyup changed delay:220ms from:#rescue_search_input",
                                hx_include="#rescue_search_input",
                                hx_swap="innerHTML",
                                cls="max-h-32 overflow-y-auto rounded-xl border border-gray-200 bg-white/80 p-1",
                            ),
                            cls="flex flex-col gap-1",
                        ),
                        Div(
                            Div(
                                Span("Time", cls="text-[11px] text-gray-600"),
                                Input(
                                    type="time",
                                    name="meal_hour",
                                    id="rescue_meal_hour",
                                    cls="web_input bg-white/70 rounded-lg border border-gray-300 px-2 py-1 text-sm",
                                ),
                                cls="flex flex-col gap-1",
                            ),
                            Div(
                                Span("Unit", cls="text-[11px] text-gray-600"),
                                Select(
                                    Option("grams", value="grams"),
                                    Option("servings", value="servings"),
                                    id="rescue_unit",
                                    cls="web_input bg-white/70 rounded-lg border border-gray-300 px-2 py-1 text-sm",
                                ),
                                cls="flex flex-col gap-1",
                            ),
                            cls="grid grid-cols-2 gap-2",
                        ),
                        Div(
                            Div(
                                Span("Amount", cls="text-[11px] text-gray-600"),
                                Input(
                                    type="number",
                                    id="rescue_amount_value",
                                    step="any",
                                    min="0",
                                    value="0",
                                    cls="web_input bg-white/70 rounded-lg border border-gray-300 px-2 py-1 text-sm",
                                ),
                                cls="flex flex-col gap-1",
                            ),
                            Div(
                                Span("Eaten %", cls="text-[11px] text-gray-600"),
                                Input(
                                    type="number",
                                    id="rescue_eaten_percent",
                                    step="any",
                                    min="0",
                                    max="100",
                                    value="100",
                                    cls="web_input bg-white/70 rounded-lg border border-gray-300 px-2 py-1 text-sm",
                                ),
                                cls="flex flex-col gap-1",
                            ),
                            cls="grid grid-cols-2 gap-2",
                        ),
                        Div(
                            Span("Consumed: ", cls="text-[11px] text-gray-600"),
                            Span("0 g", id="rescue_consumed_label", cls="text-[11px] font-semibold text-gray-800"),
                            Span(" · Leftover: ", cls="text-[11px] text-gray-600"),
                            Span("0 g", id="rescue_leftover_label", cls="text-[11px] font-semibold text-gray-800"),
                            cls="text-[11px]",
                        ),
                        Button(
                            "OK",
                            type="submit",
                            cls="web_button w-full px-3 py-2 text-sm bg-black text-white border-black",
                        ),
                        Div(id="rescue_action_result", cls="text-[11px] min-h-[1rem]"),
                        hx_post="/food/rescue/log",
                        hx_target="#rescue_action_result",
                        hx_swap="innerHTML",
                        id="rescue_power_form",
                        cls="flex flex-col gap-2",
                    ),
                    id="food_power_menu",
                    role="menu",
                    aria_label="Power menu",
                    cls=power_panel_cls,
                    style=(
                        "z-index:10010;"
                        "width:min(22rem,calc(100vw - 1.5rem));min-width:10rem;"
                        "background:#f6f2eb;backdrop-filter:none;-webkit-backdrop-filter:none;filter:none;"
                        "visibility:hidden; opacity:0; transform:translateY(-8px) scale(0.97);"
                        "pointer-events:none;"
                        "transition: opacity 180ms ease, transform 180ms ease;"
                    ),
                ),
                cls="relative flex justify-start",
            ),
            Div(
                Button(
                    Img(src="/images/ui/plus_icon.svg", alt="", cls="h-6 w-6"),
                    type="button",
                    aria_label="Open add menu",
                    cls=menu_button_cls,
                    id="food_quick_create_toggle",
                    aria_controls="food_quick_create_menu",
                    aria_expanded="false",
                ),
                Div(
                    Button(
                        Div(
                            Span("Add catalog", cls="font-semibold text-gray-900"),
                            Span("Create a new food item", cls="text-[11px] text-gray-500"),
                            cls="flex flex-col items-start gap-0.5",
                        ),
                        type="button",
                        cls=option_button_cls,
                        hx_get="/food/create/catalog/form",
                        hx_target="#main_content",
                        hx_swap="innerHTML",
                        hx_push_url="true",
                    ),
                    Button(
                        Div(
                            Span("Add manual", cls="font-semibold text-gray-900"),
                            Span("Create a manual intake", cls="text-[11px] text-gray-500"),
                            cls="flex flex-col items-start gap-0.5",
                        ),
                        type="button",
                        cls=option_button_cls,
                        hx_get="/food/create/manual/form",
                        hx_target="#main_content",
                        hx_swap="innerHTML",
                        hx_push_url="true",
                    ),
                    Button(
                        Div(
                            Span("Add recipe", cls="font-semibold text-gray-900"),
                            Span("Create a recipe entry", cls="text-[11px] text-gray-500"),
                            cls="flex flex-col items-start gap-0.5",
                        ),
                        type="button",
                        cls=option_button_cls,
                        hx_get="/food/create/recipe/form",
                        hx_target="#main_content",
                        hx_swap="innerHTML",
                        hx_push_url="true",
                    ),
                    Button(
                        Div(
                            Div(
                                Span("Scanner", cls="font-semibold text-gray-900"),
                                Span("Open the barcode scanner", cls="text-[11px] text-gray-500"),
                                cls="flex flex-col items-start gap-0.5",
                            ),
                            cls="flex flex-col items-start gap-2",
                        ),
                        type="button",
                        cls=option_button_cls,
                        hx_get="/scanner",
                        hx_target="#main_content",
                        hx_swap="innerHTML",
                        hx_push_url="true",
                    ),
                    id="food_quick_create_menu",
                    role="menu",
                    aria_label="Create food menu",
                    cls=menu_panel_cls,
                    style=(
                        "z-index:10010;"
                        "width:min(22rem,calc(100vw - 1.5rem));min-width:10rem;"
                        "background:#f6f2eb;backdrop-filter:none;-webkit-backdrop-filter:none;filter:none;"
                        "visibility:hidden; opacity:0; transform:translateY(-8px) scale(0.97);"
                        "pointer-events:none;"
                        "transition: opacity 180ms ease, transform 180ms ease;"
                    ),
                ),
                cls="relative flex justify-end",
            ),
            cls="relative w-full flex items-center justify-between",
            style="isolation:isolate; z-index:9998;",
        ),
        cls="w-full flex justify-end px-3 md:px-0 z-[130] mb-2 md:mb-3",
        data_quick_create_root="true",
    )


def CreateCatalogPanel(
    brand_options: list[str] | None = None,
    category_options: list[str] | None = None,
    subtype_options: list[str] | None = None,
):
    return Div(
        Form(
            Div(
                _labeled_input("Name*", "name"),
                _brand_autocomplete_input(brand_options=brand_options),
                _searchable_autocomplete_input("Category*", "category", category_options or CATEGORY_OPTIONS, allow_add=True),
                _searchable_autocomplete_input("Subtype*", "subtype", subtype_options or [], allow_add=True),
                _searchable_autocomplete_input("Initial state", "initial_state", INITIAL_STATE_OPTIONS, allow_add=False),
                _searchable_autocomplete_input("Nutriscore", "nutriscore", ["A", "B", "C", "D", "E"], allow_add=False),
                _labeled_input("NOVA (1-4)", "nova", "number"),
                _labeled_input("Yuka (0-100)", "yuka", "number"),
                _labeled_input("Default portion", "default_portion", "number", step="any"),
                _labeled_input("Calories/100g", "calories_100g", "number"),
                _labeled_input("Carbs/100g", "carbs_100g", "number"),
                _labeled_input("Sugars/100g", "sugars_100g", "number"),
                _labeled_input("Fats/100g", "fats_100g", "number"),
                _labeled_input("Saturated/100g", "saturated_100g", "number"),
                _labeled_input("Proteins/100g", "proteins_100g", "number"),
                _labeled_input("Fiber/100g", "fiber_100g", "number"),
                _labeled_input("Caffeine", "caffeine", "number"),
                _labeled_input("Alcohol", "alcohol", "number"),
                _labeled_input(
                    "Barcode",
                    "barcode",
                    select_on_click=False,
                    input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
                ),
                _labeled_input("Cooking factor", "cooking_factor", "number", step="any"),
                _create_flags_row(),
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
            hx_push_url="false",
            data_draft_key="food_form_create_catalog_panel",
            cls="web_container p-3 rounded-2xl flex flex-col gap-3",
        ),
        Div(id="create_catalog_result", cls="text-xs"),
        id="create_catalog_panel",
        cls="hidden md:w-md lg:w-md w-xs flex flex-col gap-2",
    )


def CreateManualPanel(subtype_options: list[str] | None = None, origin_options: list[str] | None = None):
    return Div(
        Form(
            Div(
                _labeled_input("Name*", "name"),
                _labeled_input("Description", "description"),
                _searchable_autocomplete_input("Subtype*", "subtype", subtype_options or [], allow_add=True),
                _searchable_autocomplete_input("Origin", "source_origin", origin_options or [], allow_add=True),
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
                _searchable_autocomplete_input("Glycemic index", "glycemic_index", GLYCEMIC_INDEX_OPTIONS, help_text="Estimated glycemic index level.", allow_add=False),
                _labeled_input("IG confidence 1-5", "ig_confidence", "number"),
                _create_flags_row(),
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
            hx_push_url="false",
            data_draft_key="food_form_create_manual_panel",
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
                _create_flags_row(),
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
            hx_push_url="false",
            data_draft_key="food_form_create_recipe_panel",
            cls="web_container p-3 rounded-2xl flex flex-col gap-3",
        ),
        Div(id="create_recipe_result", cls="text-xs"),
        id="create_recipe_panel",
        cls="hidden md:w-md lg:w-md w-xs flex flex-col gap-2",
    )


def _create_page_shell(title: str, form, result_id: str):
    return Div(
        Div(_food_back_button(), cls="w-full flex justify-start"),
        Div(
            H1(title, cls="text-xl font-bold"),
            cls="flex items-center justify-center gap-3 w-full",
        ),
        Div(form, cls="w-full"),
        Div(id=result_id, cls="text-xs w-full"),
        _form_draft_bootstrap_script(),
        _searchable_autocomplete_bootstrap_script(),
        _tags_multiselect_bootstrap_script(),
        Script(src="/js/smart_macros.js?v=2", defer="defer"),
        data_hide_cart="true",
        cls="""
            flex flex-col items-center
            gap-4
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-xs
            w-full mx-auto
            md:mb-28 lg:mb-28 mb-24
        """,
    )


def CreateCatalogPage(
    brand_options: list[str] | None = None,
    category_options: list[str] | None = None,
    subtype_options: list[str] | None = None,
    prefill: dict | None = None,
    existing_item_id: int | None = None,
    tag_options: list[str] | None = None,
):
    result_id = "create_catalog_result_page"
    data = prefill or {}
    def _pv(key: str, fallback: str = ""):
        value = data.get(key)
        if value is None:
            return fallback
        return str(value)

    initial_barcode = _pv("barcode", "").strip()
    draft_suffix = initial_barcode if initial_barcode else "no_barcode"
    advanced_cls = (
        "grid grid-cols-1 md:grid-cols-2 gap-2 col-span-1 md:col-span-2"
        if any(_pv(k, "").strip() for k in ("initial_state", "nutriscore", "nova", "yuka", "caffeine", "alcohol", "barcode", "cooking_factor"))
        else "hidden grid grid-cols-1 md:grid-cols-2 gap-2 col-span-1 md:col-span-2"
    )
    form = Form(
        Div(
            _labeled_input("Name*", "name", help_text="Product name. Required.", value=_pv("name")),
            _brand_autocomplete_input(brand_options=brand_options, value=_pv("brand")),
            _searchable_autocomplete_input(
                "Category*",
                "category",
                category_options or CATEGORY_OPTIONS,
                help_text="Main category. Required.",
                allow_add=True,
                value=_pv("category"),
            ),
            _searchable_autocomplete_input(
                "Subtype*",
                "subtype",
                subtype_options or [],
                help_text="Specific subtype, e.g. yogurt, pasta, soda. Required.",
                allow_add=True,
                value=_pv("subtype"),
            ),
            _smart_macros_block("catalog", prefill=data),
            _labeled_input("Default portion", "default_portion", "number", help_text="Default serving size in g/ml.", step="any", value=_pv("default_portion")),
            _create_flags_row(
                favorite_checked=True,
                private_checked=str(data.get("is_private") or "").strip().lower() in ("1", "true", "on", "yes"),
            ),
            _tags_multiselect_input(
                tag_options=tag_options,
                selected_tags=[],
                input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
            ),
            _advanced_toggle("catalog_advanced"),
            Div(
                _searchable_autocomplete_input(
                    "Initial state",
                    "initial_state",
                    INITIAL_STATE_OPTIONS,
                    help_text="Physical state before preparation.",
                    allow_add=False,
                    value=_pv("initial_state"),
                ),
                _searchable_autocomplete_input(
                    "Nutriscore",
                    "nutriscore",
                    ["A", "B", "C", "D", "E"],
                    help_text="Nutrition quality score from A to E.",
                    allow_add=False,
                    value=_pv("nutriscore"),
                ),
                _labeled_input("NOVA (1-4)", "nova", "number", help_text="Food processing level from 1 to 4.", value=_pv("nova")),
                _labeled_input("Yuka (0-100)", "yuka", "number", help_text="Optional Yuka-style score from 0 to 100.", value=_pv("yuka")),
                _labeled_input("Caffeine", "caffeine", "number", help_text="Caffeine content in mg per 100g/ml.", value=_pv("caffeine")),
                _labeled_input("Alcohol", "alcohol", "number", help_text="Alcohol content in grams per 100g/ml.", value=_pv("alcohol")),
                _labeled_input(
                    "Barcode",
                    "barcode",
                    value=initial_barcode,
                    help_text="Optional product barcode.",
                    select_on_click=False,
                    input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
                ),
                _labeled_input("Cooking factor", "cooking_factor", "number", help_text="Raw/cooked weight conversion factor.", step="any", value=_pv("cooking_factor")),
                id="catalog_advanced",
                cls=advanced_cls,
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-2",
        ),
        (
            Div(
                P("A catalog item with this barcode already exists.", cls="text-sm text-gray-700"),
                A(
                    "Open existing item",
                    hx_get=f"/food/item/catalog/{int(existing_item_id)}",
                    hx_target="#main_content",
                    hx_push_url="true",
                    cls="web_button px-3 py-1.5 text-xs w-fit bg-black text-white border-black",
                ),
                cls="web_container rounded-xl p-2 flex items-center justify-between gap-2",
            )
            if existing_item_id
            else None
        ),
        Button("Create catalog item", type="submit", cls="web_button px-3 py-2 text-xs"),
        hx_post="/food/create/catalog",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key=f"food_form_create_catalog_page::{draft_suffix}",
        cls="web_container p-3 rounded-2xl flex flex-col gap-3 w-full",
    )
    return _create_page_shell("Create Catalog", form, result_id)


def CreateManualPage(
    subtype_options: list[str] | None = None,
    origin_options: list[str] | None = None,
    tag_options: list[str] | None = None,
):
    result_id = "create_manual_result_page"
    form = Form(
        Div(
            _labeled_input("Name*", "name", help_text="Manual intake name. Required."),
            _labeled_input("Description", "description", help_text="Optional short description."),
            _searchable_autocomplete_input(
                "Subtype*",
                "subtype",
                subtype_options or [],
                help_text="Specific subtype. Required.",
                allow_add=True,
            ),
            _searchable_autocomplete_input(
                "Origin",
                "source_origin",
                origin_options or [],
                help_text="Where it came from (home, restaurant, etc.).",
                allow_add=True,
            ),
            _labeled_input("Amount g*", "amount_g", "number", help_text="Consumed amount in grams/ml. Required."),
            _smart_macros_block("manual"),
            _create_flags_row(),
            _tags_multiselect_input(
                tag_options=tag_options,
                selected_tags=[],
                input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
            ),
            _advanced_toggle("manual_advanced"),
            Div(
                _labeled_input("Caffeine", "caffeine", "number", help_text="Caffeine content in mg per 100g/ml."),
                _labeled_input("Alcohol", "alcohol", "number", help_text="Alcohol content in grams per 100g/ml."),
                _searchable_autocomplete_input("Glycemic index", "glycemic_index", GLYCEMIC_INDEX_OPTIONS, help_text="Estimated glycemic index level.", allow_add=False),
                _labeled_input("IG confidence 1-5", "ig_confidence", "number", help_text="Confidence in glycemic index estimate (1 low, 5 high)."),
                id="manual_advanced",
                cls="hidden grid grid-cols-1 md:grid-cols-2 gap-2 col-span-1 md:col-span-2",
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-2",
        ),
        Button("Create manual intake", type="submit", cls="web_button px-3 py-2 text-xs"),
        hx_post="/food/create/manual",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key="food_form_create_manual_page",
        cls="web_container p-3 rounded-2xl flex flex-col gap-3 w-full",
    )
    return _create_page_shell("Create Manual Intake", form, result_id)


def CreateRecipePage(tag_options: list[str] | None = None):
    result_id = "create_recipe_result_page"
    form = Form(
        Div(
            _labeled_input("Name*", "name", help_text="Recipe name. Required."),
            _labeled_select("Meal type", "meal_type", MEAL_TYPES, help_text="When this recipe is usually eaten."),
            _create_flags_row(),
            _tags_multiselect_input(
                tag_options=tag_options,
                selected_tags=[],
                input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
            ),
            _advanced_toggle("recipe_advanced"),
            Div(
                Div(
                    _label_with_help("Notes", "Optional instructions, comments, or context about this recipe.", for_id="create_recipe_notes"),
                    Textarea(
                        "",
                        id="create_recipe_notes",
                        name="notes",
                        rows="3",
                        cls="web_input border border-white rounded-lg px-2 py-1 text-xs",
                    ),
                    cls="flex flex-col gap-1 col-span-1 md:col-span-2",
                ),
                id="recipe_advanced",
                cls="hidden grid grid-cols-1 md:grid-cols-2 gap-2 col-span-1 md:col-span-2",
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-2",
        ),
        Button("Create recipe", type="submit", cls="web_button px-3 py-2 text-xs"),
        hx_post="/food/create/recipe",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key="food_form_create_recipe_page",
        cls="web_container p-3 rounded-2xl flex flex-col gap-3 w-full",
    )
    return _create_page_shell("Create Recipe", form, result_id)


def _input_value(value) -> str:
    if value is None:
        return ""
    return str(value)


def _edit_page_shell(form, result_id: str):
    return Div(
        Div(form, cls="w-full"),
        Div(id=result_id, cls="text-xs w-full"),
        _form_draft_bootstrap_script(),
        _searchable_autocomplete_bootstrap_script(),
        _tags_multiselect_bootstrap_script(),
        data_hide_cart="true",
        cls="""
            flex flex-col items-center
            gap-4
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-xs
            w-full mx-auto
            md:mb-28 lg:mb-28 mb-24
        """,
    )


def _edit_tile(content, cls: str = ""):
    extra = f" {cls.strip()}" if cls and cls.strip() else ""
    return Div(content, cls=f"web_container p-3 rounded-xl flex flex-col gap-1{extra}")


def _edit_name_input(value: str):
    name_id = "edit_name"
    return Div(
        Label(
            "Name",
            **{"for": name_id},
            style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;",
        ),
        Textarea(
            value,
            id=name_id,
            name="name",
            rows="2",
            cls="""
                w-full text-2xl font-bold text-black text-center
                px-0 py-0 border-0 rounded-none
                bg-transparent shadow-none
                focus:outline-none resize-none mr-1
            """,
            style="background:transparent;border-color:transparent;box-shadow:none;",
        ),
    )


def EditCatalogPage(
    entry: dict,
    brand_options: list[str] | None = None,
    category_options: list[str] | None = None,
    subtype_options: list[str] | None = None,
    show_private: bool = False,
    tag_options: list[str] | None = None,
    selected_tags: list[str] | None = None,
):
    result_id = f"edit_catalog_result_{entry['id']}"
    form = Form(
        _edit_name_input(_input_value(entry.get("name"))),
        _edit_tile(_brand_autocomplete_input(brand_options=brand_options, value=_input_value(entry.get("brand")))),
        _edit_tile(
            _tags_multiselect_input(
                tag_options=tag_options,
                selected_tags=selected_tags or [],
                input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
            ),
            cls="w-full",
        ),
        Div(
            H2("Macros Summary", cls="font-semibold text-gray-900"),
            Div(
                _edit_tile(_labeled_input("Calories/100g", "calories_100g", "float", value=_input_value(entry.get("calories_100g")))),
                _edit_tile(_labeled_input("Carbs/100g", "carbs_100g", "float", value=_input_value(entry.get("carbs_100g")))),
                _edit_tile(_labeled_input("Sugars/100g", "sugars_100g", "float", value=_input_value(entry.get("sugars_100g")))),
                _edit_tile(_labeled_input("Fats/100g", "fats_100g", "float", value=_input_value(entry.get("fats_100g")))),
                _edit_tile(_labeled_input("Saturated/100g", "saturated_100g", "float", value=_input_value(entry.get("saturated_100g")))),
                _edit_tile(_labeled_input("Proteins/100g", "proteins_100g", "float", value=_input_value(entry.get("proteins_100g")))),
                _edit_tile(_labeled_input("Fiber/100g", "fiber_100g", "float", value=_input_value(entry.get("fiber_100g")))),
                cls="grid grid-cols-2 md:grid-cols-3 gap-2",
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            H2("Details", cls="font-semibold text-gray-900"),
            Div(
                _edit_tile(_searchable_autocomplete_input("Category*", "category", category_options or CATEGORY_OPTIONS, allow_add=True, value=_input_value(entry.get("category")))),
                _edit_tile(_searchable_autocomplete_input("Subtype*", "subtype", subtype_options or [], allow_add=True, value=_input_value(entry.get("subtype")))),
                _edit_tile(_labeled_input("Default portion", "default_portion", "number", step="any", value=_input_value(entry.get("default_portion")))),
                _edit_tile(_searchable_autocomplete_input("Initial state", "initial_state", INITIAL_STATE_OPTIONS, allow_add=False, value=_input_value(entry.get("initial_state")))),
                _edit_tile(_searchable_autocomplete_input("Nutriscore", "nutriscore", ["A", "B", "C", "D", "E"], allow_add=False, value=_input_value(entry.get("nutriscore")))),
                _edit_tile(_labeled_input("NOVA (1-4)", "nova", "number", value=_input_value(entry.get("nova")))),
                _edit_tile(_labeled_input("Yuka (0-100)", "yuka", "number", value=_input_value(entry.get("yuka")))),
                _edit_tile(_labeled_input("Caffeine", "caffeine", "number", value=_input_value(entry.get("caffeine")))),
                _edit_tile(_labeled_input("Alcohol", "alcohol", "number", value=_input_value(entry.get("alcohol")))),
                _edit_tile(
                    _labeled_input(
                        "Barcode",
                        "barcode",
                        value=_input_value(entry.get("barcode")),
                        select_on_click=False,
                        input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
                    )
                ),
                _edit_tile(_labeled_input("Cooking factor", "cooking_factor", "number", step="any", value=_input_value(entry.get("cooking_factor")))),
                cls="grid grid-cols-1 md:grid-cols-2 gap-2",
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        *([_private_checkbox(checked=bool(entry.get("is_private")), centered=True)] if show_private else []),
        Div(
            Button(
                "Back",
                type="button",
                cls="""
                    web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl
                    bg-white/85 text-gray-800 border border-gray-300
                    shadow-[0_6px_20px_rgba(17,24,39,0.08)]
                """,
                hx_get=f"/food/item/catalog/{entry['id']}",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button("Save changes", type="submit", cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-black text-white border-black"),
            cls="grid grid-cols-2 gap-3",
        ),
        hx_post=f"/food/edit/catalog/{entry['id']}",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key=f"food_form_edit_catalog_{entry['id']}",
        cls="flex flex-col gap-3 w-full",
    )
    return _edit_page_shell(form, result_id)


def EditManualPage(
    entry: dict,
    subtype_options: list[str] | None = None,
    origin_options: list[str] | None = None,
    show_private: bool = False,
    tag_options: list[str] | None = None,
    selected_tags: list[str] | None = None,
):
    result_id = f"edit_manual_result_{entry['id']}"
    form = Form(
        _edit_name_input(_input_value(entry.get("name"))),
        _edit_tile(_searchable_autocomplete_input("Brand / Origin", "source_origin", origin_options or [], allow_add=True, value=_input_value(entry.get("origin")))),
        _edit_tile(
            _tags_multiselect_input(
                tag_options=tag_options,
                selected_tags=selected_tags or [],
                input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
            ),
            cls="w-full",
        ),
        Div(
            H2("Macros Summary", cls="font-semibold text-gray-900"),
            Div(
                _edit_tile(_labeled_input("Calories/100g", "calories_100g", "number", value=_input_value(entry.get("calories_100g")))),
                _edit_tile(_labeled_input("Carbs/100g", "carbs_100g", "number", value=_input_value(entry.get("carbs_100g")))),
                _edit_tile(_labeled_input("Sugars/100g", "sugars_100g", "number", value=_input_value(entry.get("sugars_100g")))),
                _edit_tile(_labeled_input("Fats/100g", "fats_100g", "number", value=_input_value(entry.get("fats_100g")))),
                _edit_tile(_labeled_input("Saturated/100g", "saturated_100g", "number", value=_input_value(entry.get("saturated_100g")))),
                _edit_tile(_labeled_input("Proteins/100g", "proteins_100g", "number", value=_input_value(entry.get("proteins_100g")))),
                _edit_tile(_labeled_input("Fiber/100g", "fiber_100g", "number", value=_input_value(entry.get("fiber_100g")))),
                cls="grid grid-cols-2 md:grid-cols-3 gap-2",
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            H2("Details", cls="font-semibold text-gray-900"),
            Div(
                _edit_tile(
                    Div(
                        _label_with_help("Description", "Optional short description.", for_id="edit_manual_description"),
                        Textarea(
                            _input_value(entry.get("description")),
                            id="edit_manual_description",
                            name="description",
                            rows="4",
                            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-base mr-1 w-full",
                        ),
                        cls="flex flex-col gap-1",
                    ),
                    cls="col-span-1 md:col-span-2",
                ),
                _edit_tile(_searchable_autocomplete_input("Subtype*", "subtype", subtype_options or [], allow_add=True, value=_input_value(entry.get("subtype")))),
                _edit_tile(_labeled_input("Amount g*", "amount_g", "number", value=_input_value(entry.get("amount_g")))),
                _edit_tile(_labeled_input("Caffeine", "caffeine", "number", value=_input_value(entry.get("caffeine")))),
                _edit_tile(_labeled_input("Alcohol", "alcohol", "number", value=_input_value(entry.get("alcohol")))),
                _edit_tile(_searchable_autocomplete_input("Glycemic index", "glycemic_index", GLYCEMIC_INDEX_OPTIONS, allow_add=False, value=_input_value(entry.get("glycemic_index")))),
                _edit_tile(_labeled_input("IG confidence 1-5", "ig_confidence", "number", value=_input_value(entry.get("ig_confidence")))),
                cls="grid grid-cols-1 md:grid-cols-2 gap-2",
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        *([_private_checkbox(checked=bool(entry.get("is_private")), centered=True)] if show_private else []),
        Div(
            Button(
                "Back",
                type="button",
                cls="""
                    web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl
                    bg-white/85 text-gray-800 border border-gray-300
                    shadow-[0_6px_20px_rgba(17,24,39,0.08)]
                """,
                hx_get=f"/food/item/manual_intake/{entry['id']}",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button("Save changes", type="submit", cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-black text-white border-black"),
            cls="grid grid-cols-2 gap-3",
        ),
        hx_post=f"/food/edit/manual/{entry['id']}",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key=f"food_form_edit_manual_{entry['id']}",
        cls="flex flex-col gap-3 w-full",
    )
    return _edit_page_shell(form, result_id)


def EditRecipePage(
    entry: dict,
    show_private: bool = False,
    tag_options: list[str] | None = None,
    selected_tags: list[str] | None = None,
):
    result_id = f"edit_recipe_result_{entry['id']}"
    form = Form(
        _edit_name_input(_input_value(entry.get("name"))),
        _edit_tile(
            _tags_multiselect_input(
                tag_options=tag_options,
                selected_tags=selected_tags or [],
                input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
            ),
            cls="w-full",
        ),
        Div(
            H2("Details", cls="font-semibold text-gray-900"),
            Div(
                _edit_tile(_labeled_select("Meal type", "meal_type", MEAL_TYPES, selected_value=_input_value(entry.get("meal_type")))),
                _edit_tile(
                    Div(
                        _label_with_help("Notes", "Optional instructions, comments, or context about this recipe.", for_id="edit_recipe_notes"),
                        Textarea(
                            _input_value(entry.get("notes")),
                            id="edit_recipe_notes",
                            name="notes",
                            rows="3",
                            onclick="this.select()",
                            cls="web_input border border-white rounded-lg px-2 py-1 text-xs mr-1",
                        ),
                        cls="flex flex-col gap-1",
                    )
                ),
                cls="grid grid-cols-1 md:grid-cols-2 gap-2",
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        *([_private_checkbox(checked=bool(entry.get("is_private")), centered=True)] if show_private else []),
        Div(
            Button(
                "Back",
                type="button",
                cls="""
                    web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl
                    bg-white/85 text-gray-800 border border-gray-300
                    shadow-[0_6px_20px_rgba(17,24,39,0.08)]
                """,
                hx_get=f"/food/item/recipe/{entry['id']}",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button("Save changes", type="submit", cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-black text-white border-black"),
            cls="grid grid-cols-2 gap-3",
        ),
        hx_post=f"/food/edit/recipe/{entry['id']}",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key=f"food_form_edit_recipe_{entry['id']}",
        cls="flex flex-col gap-3 w-full",
    )
    return _edit_page_shell(form, result_id)


def FavoriteButton(entry_type: str, entry_id: int, favorite: bool):
    icon = "/images/content/fav_icon.svg" if favorite else "/images/content/not_fav_icon.svg"
    return Button(
        Img(src=icon, cls="w-4 h-4", alt=""),
        type="button",
        aria_label="Toggle favorite",
        title="Toggle favorite",
        cls="""
            web_button p-1.5
            border-gray-500/30 shadow-none
            w-8 h-8
            flex items-center justify-center
            hover:bg-gray-500/20
        """,
        hx_post=f"/food/favorite/{entry_type}/{entry_id}",
        hx_target="this",
        hx_swap="outerHTML",
        hx_trigger="click consume",
        hx_push_url="false",
        **{"hx-on:click": "event.stopPropagation();"},
        data_skip_page_loading="true",
        data_no_open="true",
    )


def AddButton(label: str = "+", include_meal_selector: bool = True, **attrs):
    if include_meal_selector:
        attrs.setdefault("hx_include", "#meal_selector")
    else:
        attrs.pop("hx_include", None)
    attrs.setdefault("data_skip_page_loading", "true")
    attrs.setdefault("hx_target", "this")
    attrs.setdefault("hx_trigger", "click consume")
    attrs.setdefault("hx_push_url", "false")
    attrs.setdefault("data_no_open", "true")
    attrs.setdefault("type", "button")
    button_cls = attrs.pop(
        "cls",
        """
            web_button
            rounded-lg
            border-gray-500/30 shadow-none
            hover:bg-gray-500/50
            w-8 h-8
            flex items-center justify-center
            transition-colors duration-300
            text-base
        """,
    )
    return Button(
        label,
        cls=button_cls,
        hx_swap="none",
        **on_after(reload_page=False),
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


def _float_or_zero(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _display_base_unit(entry_type: str, item: dict) -> str:
    if entry_type == "catalog" and (item.get("category") or "").strip().lower() == "beverages":
        return "ml"
    if entry_type == "manual_intake":
        subtype = (item.get("subtype") or "").strip().lower()
        liquid_hints = ("drink", "beverage", "juice", "soda", "smoothie", "milk", "coffee", "tea", "bebida")
        if any(token in subtype for token in liquid_hints):
            return "ml"
    return "g"


def _detail_unit_options(base_amount: float, base_unit: str):
    hundred_label = f"100{base_unit}"
    one_label = base_unit
    return [
        Option(
            f"serving ({base_amount:.0f}{base_unit})",
            value="portion",
            selected=True,
            data_factor=f"{base_amount:.6f}",
            data_unit_label="serving",
        ),
        Option(f"{hundred_label} (100{base_unit})", value="x100", data_factor="100.000000", data_unit_label=hundred_label),
        Option(f"{one_label} (1{base_unit})", value=base_unit, data_factor="1.000000", data_unit_label=one_label),
        Option(f"lb (453.59{base_unit})", value="lb", data_factor="453.592370", data_unit_label="lb"),
        Option(f"oz (28.35{base_unit})", value="oz", data_factor="28.349523", data_unit_label="oz"),
    ]


def _detail_macro_tiles(per100: dict, amount_g: float):
    specs = [
        ("calories_100g", "Calories", "kcal"),
        ("carbs_100g", "Carbs", "g"),
        ("sugars_100g", "Sugars", "g"),
        ("fats_100g", "Fats", "g"),
        ("saturated_100g", "Saturated", "g"),
        ("proteins_100g", "Proteins", "g"),
        ("fiber_100g", "Fiber", "g"),
    ]
    tiles = []
    for key, label, unit in specs:
        amount = (amount_g * _float_or_zero(per100.get(key))) / 100.0
        amount_text = f"{amount:.0f} {unit}" if unit == "kcal" else f"{amount:.1f} {unit}"
        tiles.append(
            Div(
                Span(label, cls="text-xs text-gray-600"),
                Span(
                    amount_text,
                    data_detail_macro_key=key,
                    data_per100=f"{_float_or_zero(per100.get(key)):.6f}",
                    data_unit=unit,
                    cls="text-base font-semibold text-gray-900",
                ),
                cls="web_container p-3 rounded-xl flex flex-col gap-1",
            )
        )
    return tiles


def _detail_info_rows(rows: list[tuple[str, str]]):
    blocks = []
    for label, value in rows:
        clean = (value or "").strip()
        if not clean:
            continue
        blocks.append(
            Div(
                Span(label, cls="text-xs text-gray-600"),
                Span(clean, cls="text-sm text-gray-900"),
                cls="web_container p-3 rounded-xl flex flex-col gap-1",
            )
        )
    if not blocks:
        return Div("No extra info yet.", cls="text-sm text-gray-500")
    return Div(*blocks, cls="grid grid-cols-1 md:grid-cols-2 gap-2")


def _recipe_portion_name(portion: dict) -> str:
    return portion.get("catalog_name") or portion.get("manual_intake_name") or f"Ingredient #{portion.get('id')}"


def _recipe_portion_entry_type(portion: dict) -> str:
    return "catalog" if portion.get("catalog_id") else "manual_intake"


def _recipe_portion_meta(portion: dict) -> str:
    carbs = portion.get("catalog_carbs_100g")
    if carbs is None:
        carbs = portion.get("manual_carbs_100g")
    entry_label = "Food" if portion.get("catalog_id") else "Manual"
    return f"{entry_label} · {carbs if carbs is not None else '-'} CH"


def _recipe_portion_base_amount(portion: dict) -> float:
    if portion.get("catalog_id"):
        return max(1.0, _float_or_zero(portion.get("catalog_default_portion")) or 100.0)
    return max(1.0, _float_or_zero(portion.get("manual_amount_g")) or 100.0)


def _recipe_portion_base_unit(portion: dict) -> str:
    if portion.get("catalog_id"):
        item = {"category": portion.get("catalog_category")}
        return _display_base_unit("catalog", item)
    item = {"subtype": portion.get("manual_subtype")}
    return _display_base_unit("manual_intake", item)


def RecipeIngredientRow(recipe_id: int, portion: dict):
    portion_id = int(portion.get("id") or 0)
    base_amount = _recipe_portion_base_amount(portion)
    base_unit = _recipe_portion_base_unit(portion)
    grams_value = max(0.0, _float_or_zero(portion.get("amount_g")))
    display_value = (grams_value / base_amount) if base_amount > 0 else grams_value
    display_id = f"recipe_portion_display_{portion_id}"
    select_id = f"recipe_portion_select_{portion_id}"
    grams_id = f"recipe_portion_grams_{portion_id}"
    side_unit_id = f"recipe_portion_side_{portion_id}"
    msg_id = f"recipe_portion_msg_{portion_id}"
    advanced_id = f"recipe_portion_advanced_{portion_id}"
    advanced_msg_id = f"recipe_portion_advanced_msg_{portion_id}"
    advanced_inner_id = f"recipe_portion_advanced_inner_{portion_id}"
    advanced_content_id = f"recipe_portion_advanced_content_{portion_id}"
    persist_key = f"recipe_portion_unit_{portion_id}"
    macros_grid_id = f"food_detail_recipe_{recipe_id}_macros"

    return Div(
        Div(
            Div(
                H3(_recipe_portion_name(portion), cls="text-left font-semibold"),
                P(_recipe_portion_meta(portion), cls="text-sm text-gray-700"),
                cls="flex flex-col gap-0.5 min-w-0",
            ),
            Div(
                Form(
                    Div(
                        Div(
                            Input(
                                type="text",
                                id=display_id,
                                inputmode="decimal",
                                value=f"{display_value:.2f}".replace(".", ","),
                                cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 w-16 text-base",
                                onclick="this.select()",
                                onchange=f"dbRecalcGrams('{display_id}','{select_id}','{grams_id}', true)",
                                onblur=f"dbRecalcGrams('{display_id}','{select_id}','{grams_id}', true)",
                            ),
                            Span("serving", id=side_unit_id, cls="text-xs text-gray-600 min-w-12 text-right"),
                            cls="flex items-center justify-end gap-2 w-full md:w-auto",
                        ),
                        Select(
                            *_detail_unit_options(base_amount, base_unit),
                            id=select_id,
                            data_display_id=display_id,
                            data_grams_id=grams_id,
                            data_side_unit_id=side_unit_id,
                            data_persist_key=persist_key,
                            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-xs w-full md:w-auto",
                            onchange=f"dbRecalcGrams('{display_id}','{select_id}','{grams_id}', true)",
                        ),
                        Input(type="hidden", id=grams_id, name="amount_g", value=f"{grams_value:.6f}"),
                        cls="flex flex-col items-end gap-2 md:flex-row md:items-center md:justify-end",
                    ),
                    Div(id=msg_id, cls="min-h-4 text-[10px] text-right text-gray-600"),
                    hx_post=f"/food/recipe/{recipe_id}/ingredient/{portion_id}/amount",
                    hx_trigger=f"change from:#{grams_id}",
                    hx_target=f"#{msg_id}",
                    hx_swap="innerHTML",
                    hx_push_url="false",
                    data_skip_page_loading="true",
                    **{
                        "hx-on:htmx:after-request": (
                            f"if(event.detail.successful){{htmx.ajax('GET','/food/recipe/{recipe_id}/macros',"
                            f"{{target:'#{macros_grid_id}',swap:'outerHTML'}});}}"
                        )
                    },
                        cls="flex flex-col items-end gap-1",
                    ),
                    Div(
                        Button(
                            "Advanced",
                            type="button",
                            cls="web_button px-2 py-1 text-[11px]",
                            onclick=(
                                f"const el=document.getElementById('{advanced_id}');"
                                f"const inner=document.getElementById('{advanced_inner_id}');"
                                f"const content=document.getElementById('{advanced_content_id}');"
                                "if(!el) return;"
                                "const isOpen = el.getAttribute('data-open') === '1';"
                                "if(!isOpen){"
                                "el.setAttribute('data-open','1');"
                                "el.style.overflow='hidden';"
                                "var h = content ? content.scrollHeight : (inner ? inner.scrollHeight + 16 : 240);"
                                "el.style.maxHeight = (h + 2) + 'px';"
                                "el.style.opacity = '1';"
                                "setTimeout(function(){ if(el.getAttribute('data-open')==='1'){ el.style.overflow='visible'; } }, 320);"
                                "} else {"
                                "el.setAttribute('data-open','0');"
                                "el.style.overflow='hidden';"
                                "el.style.maxHeight = '0px';"
                                "el.style.opacity = '0';"
                                "}"
                            ),
                        ),
                    Button(
                        "Delete",
                        type="button",
                        cls="web_button px-2 py-1 text-[11px] border-red-300 text-red-700 hover:bg-red-50",
                        hx_post=f"/food/recipe/{recipe_id}/ingredient/{portion_id}/delete",
                        hx_target="closest .food_entry",
                        hx_swap="outerHTML",
                        hx_push_url="false",
                        data_skip_page_loading="true",
                        data_no_open="true",
                    ),
                    cls="flex items-center justify-end gap-2",
                ),
                cls="ml-3 flex flex-col items-end gap-1",
            ),
            cls="flex items-start justify-between",
        ),
        Div(
            Form(
                Div(
                    Div(
                        _searchable_compact_input(
                            name="cooking",
                            options=COOKING_OPTIONS,
                            value=(portion.get("cooking") or ""),
                            placeholder="Cooking",
                            allow_add=False,
                            autosave=True,
                        ),
                        cls="flex flex-col gap-1 min-w-0",
                    ),
                    Div(
                        _searchable_compact_input(
                            name="final_state",
                            options=INITIAL_STATE_OPTIONS,
                            value=(portion.get("final_state") or ""),
                            placeholder="Final state",
                            allow_add=False,
                            autosave=True,
                        ),
                        cls="flex flex-col gap-1 min-w-0",
                    ),
                    Div(
                        _searchable_compact_input(
                            name="conservation",
                            options=CONSERVATION_OPTIONS,
                            value=(portion.get("conservation") or ""),
                            placeholder="Conservation",
                            allow_add=False,
                            autosave=True,
                            ),
                            cls="flex flex-col gap-1 min-w-0 col-span-2 xl:col-span-1",
                        ),
                    id=advanced_inner_id,
                    cls="grid grid-cols-2 xl:grid-cols-3 gap-2",
                ),
                Div(id=advanced_msg_id, cls="text-[10px] text-right text-gray-600"),
                hx_post=f"/food/recipe/{recipe_id}/ingredient/{portion_id}/advanced",
                hx_trigger="submit",
                hx_target=f"#{advanced_msg_id}",
                hx_swap="innerHTML",
                hx_push_url="false",
                data_skip_page_loading="true",
                id=advanced_content_id,
                cls="flex flex-col gap-0 w-full max-w-full min-w-0",
            ),
            id=advanced_id,
            data_open="0",
            cls="w-full max-w-full relative z-0 transition-all duration-300 ease-out overflow-hidden",
            style="max-height:0px;opacity:0;",
        ),
        cls="web_container food_entry flex flex-col gap-1",
    )


def RecipeIngredientsBlock(recipe_id: int, portions: list[dict]):
    content = [RecipeIngredientRow(recipe_id, portion) for portion in portions] if portions else [P("No ingredients yet.", cls="text-sm text-gray-500")]
    return Div(
        Div(
            H2("Ingredients", cls="font-semibold text-gray-900"),
            Button(
                "Add ingredient",
                type="button",
                cls="web_button px-3 py-2 text-xs",
                hx_get=f"/food/recipe/{recipe_id}/ingredients/form",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            cls="flex items-center justify-between gap-3",
        ),
        Div(*content, cls="flex flex-col gap-2"),
        cls="flex flex-col gap-2 w-full",
    )


def FoodDetailPage(
    connection,
    user_id: int,
    entry_type: str,
    entry: dict,
    summary: dict,
    recipe_portions: list[dict] | None = None,
    tags: list[dict] | list[str] | None = None,
    can_edit: bool = True,
    can_delete: bool = False,
    is_archived: bool = False,
):
    base_unit = _display_base_unit(entry_type, entry)
    default_amount = max(1.0, _float_or_zero(summary.get("default_amount_g")) or 100.0)
    amount_display = f"{default_amount:.2f}".replace(".", ",")
    per100 = summary.get("per100") or {}
    info_rows = summary.get("info_rows") or []
    subtitle = summary.get("subtitle") or ""
    edit_label = (
        {"catalog": "Edit food", "manual_intake": "Edit manual", "recipe": "Edit recipe"}.get(entry_type, "Edit")
        if can_edit
        else "Create editable copy"
    )
    edit_href = {
        "catalog": f"/food/edit/catalog/{entry['id']}/form",
        "manual_intake": f"/food/edit/manual_intake/{entry['id']}/form",
        "recipe": f"/food/edit/recipe/{entry['id']}/form",
    }.get(entry_type, "/food")
    copy_confirm_id = f"copy_confirm_{entry_type}_{entry['id']}"
    delete_confirm_id = f"delete_confirm_{entry_type}_{entry['id']}"
    delete_title = {
        "catalog": "Delete food",
        "manual_intake": "Delete manual intake",
        "recipe": "Delete recipe",
    }.get(entry_type, "Delete item")
    delete_question = {
        "catalog": "Are you sure you want to delete this food?",
        "manual_intake": "Are you sure you want to delete this manual intake?",
        "recipe": "Are you sure you want to delete this recipe?",
    }.get(entry_type, "Are you sure you want to delete this item?")

    root_id = f"food_detail_{entry_type}_{entry['id']}"
    display_id = f"{root_id}_display"
    grams_id = f"{root_id}_grams"
    select_id = f"{root_id}_select"
    side_unit_id = f"{root_id}_side_unit"
    plate_value_id = f"{root_id}_plate_value"
    plate_unit_id = f"{root_id}_plate_unit"
    plate_unit_btn_id = f"{root_id}_plate_unit_btn"
    plate_grams_id = f"{root_id}_plate_grams"
    plate_equivalent_id = f"{root_id}_plate_equivalent"
    leftovers_id = f"{root_id}_leftovers"
    msg_id = f"{root_id}_msg"
    advanced_id = f"{root_id}_advanced"
    advanced_inner_id = f"{root_id}_advanced_inner"
    form_id = f"{root_id}_form"
    persist_key = f"food_detail_amount_{entry_type}_{entry['id']}"

    recipe_mode = entry_type == "recipe"
    action_button_label = "Log recipe" if recipe_mode else "Log food"
    meal_selector = MealSelector(connection, user_id=user_id or 0) if not recipe_mode else ""
    recipe_ingredients = RecipeIngredientsBlock(int(entry.get("id") or 0), recipe_portions or []) if recipe_mode else ""
    action_button = (
        Button(
            action_button_label,
            type="button",
            cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-black text-white border-black",
            hx_post=f"/food/log/{entry_type}/{entry['id']}",
            hx_target=f"#{msg_id}",
            hx_swap="innerHTML",
            hx_push_url="false",
            hx_include=f"{'#meal_selector, ' if not recipe_mode else ''}#{form_id}",
            data_skip_page_loading="true",
        )
        if not is_archived
        else Button(
            "Archived: copy first",
            type="button",
            disabled=True,
            cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-gray-300 text-gray-600 border-gray-300 cursor-not-allowed",
        )
    )

    return Div(
        Div(_food_back_button(), cls="w-full flex justify-start"),
        Div(
            Div(
                Div(
                    H1(entry.get("name") or "-", cls="text-2xl font-bold text-gray-900"),
                    P(subtitle, cls="text-sm text-gray-600"),
                    P("Archived food: create a copy to use it.", cls="text-xs font-semibold text-amber-700") if is_archived else "",
                    (
                        Div(
                            *[
                                Span(
                                    (tag.get("name") if isinstance(tag, dict) else str(tag)),
                                    cls="inline-flex items-center rounded-full border px-2 py-1 text-xs font-semibold",
                                    style=(
                                        (
                                            f"background:{str(tag.get('color') or '')};"
                                            if isinstance(tag, dict) and str(tag.get("color") or "").strip()
                                            else _tag_badge_style(str(tag.get("name") if isinstance(tag, dict) else tag))
                                        )
                                        + "border-color:rgba(0,0,0,0.2);color:rgba(17,24,39,0.95);"
                                    ),
                                )
                                for tag in (tags or [])
                            ],
                            cls="flex flex-wrap gap-1.5 pt-1",
                        )
                        if tags
                        else ""
                    ),
                    cls="flex flex-col gap-1",
                ),
                (
                    Button(
                        Img(src="/images/content/delete.svg", alt="", cls="w-4 h-4"),
                        type="button",
                        aria_label=delete_title,
                        title=delete_title,
                        cls="""
                            web_button p-2
                            border-red-600/40 shadow-none
                            w-9 h-9
                            flex items-center justify-center
                            hover:bg-red-50
                        """,
                        style="color:#b91c1c;",
                        onclick=_open_modal_js(delete_confirm_id),
                    )
                    if can_delete
                    else ""
                ),
                cls="flex items-start justify-between gap-3",
            ),
            cls="flex flex-col gap-1 w-full",
        ),
        meal_selector,
        Div(
            Form(
                Div(
                    Label(
                        "Food amount",
                        **{"for": display_id},
                        style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;",
                    ),
                    Input(
                        type="text",
                        id=display_id,
                        inputmode="decimal",
                        value=amount_display,
                        aria_label="Food amount",
                        cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 w-24 text-base",
                        onchange=f"dbFoodDetailRefresh('{root_id}')",
                        onclick="this.select()",
                    ),
                    Span("serving", id=side_unit_id, cls="text-xs text-gray-600"),
                    Label(
                        "Food unit selector",
                        **{"for": select_id},
                        style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;",
                    ),
                    Select(
                        *_detail_unit_options(default_amount, base_unit),
                        id=select_id,
                        data_display_id=display_id,
                        data_grams_id=grams_id,
                        data_side_unit_id=side_unit_id,
                        data_persist_key=f"food_detail_unit_{entry_type}_{entry['id']}",
                        aria_label="Food unit selector",
                        cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-xs md:text-sm justify-self-end",
                        onchange=f"dbFoodDetailOnUnitChange('{root_id}')",
                    ),
                    Input(type="hidden", name="total_amount_g", id=grams_id, value=f"{default_amount:.6f}"),
                    cls="flex items-center gap-2",
                ),
                Div(
                    Span("To plate", cls="text-xs text-gray-600"),
                    Label(
                        "Amount to plate",
                        **{"for": plate_value_id},
                        style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;",
                    ),
                    Input(
                        type="text",
                        id=plate_value_id,
                        inputmode="decimal",
                        value="100",
                        aria_label="Amount to plate",
                        cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 w-16 md:w-20 text-base",
                        oninput=f"dbFoodDetailPlateRefresh('{root_id}')",
                        onchange=f"dbFoodDetailPlateRefresh('{root_id}')",
                        onclick="this.select()",
                    ),
                    Button(
                        "%",
                        type="button",
                        id=plate_unit_btn_id,
                        aria_label="Toggle to plate unit",
                        onclick=f"dbFoodDetailTogglePlateUnit('{root_id}')",
                        cls="""
                            web_button px-2 py-1 text-sm min-w-10
                            border border-gray-300 bg-white/85
                        """,
                    ),
                    Input(type="hidden", id=plate_unit_id, value="%"),
                    Input(type="hidden", name="amount_g", id=plate_grams_id, value=f"{default_amount:.6f}"),
                    cls="flex items-center gap-2",
                ),
                P(
                    f"Total amount (plate amount): {default_amount:.1f} ({default_amount:.1f}) {base_unit}",
                    id=plate_equivalent_id,
                    data_detail_plate_equivalent="true",
                    cls="text-xs text-gray-600",
                ),
                P(
                    f"Will be saved in fridge: {0.0:.1f} {base_unit}",
                    id=leftovers_id,
                    data_detail_leftovers="true",
                    cls="text-xs text-gray-600",
                ),
                Div(
                    Button(
                        "Advanced",
                        type="button",
                        cls="web_button px-2 py-1 text-[11px] w-fit",
                        onclick=(
                            f"const el=document.getElementById('{advanced_id}');"
                            f"const inner=document.getElementById('{advanced_inner_id}');"
                            "if(!el) return;"
                            "const isOpen = el.getAttribute('data-open') === '1';"
                            "if(!isOpen){"
                            "el.setAttribute('data-open','1');"
                            "el.style.overflow='hidden';"
                            "el.style.maxHeight = (inner ? (inner.scrollHeight + 8) : 220) + 'px';"
                            "el.style.opacity = '1';"
                            "setTimeout(function(){ if(el.getAttribute('data-open')==='1'){ el.style.overflow='visible'; } }, 320);"
                            "} else {"
                            "el.setAttribute('data-open','0');"
                            "el.style.overflow='hidden';"
                            "el.style.maxHeight = '0px';"
                            "el.style.opacity = '0';"
                            "}"
                        ),
                    ),
                    cls=f"{'hidden ' if recipe_mode else ''}flex justify-end",
                ),
                Div(
                    Div(
                        Div(
                            _searchable_compact_input(
                                name="cooking",
                                options=COOKING_OPTIONS,
                                value="",
                                placeholder="Cooking",
                                allow_add=False,
                            ),
                            cls="flex flex-col gap-1",
                        ),
                        Div(
                            _searchable_compact_input(
                                name="final_state",
                                options=INITIAL_STATE_OPTIONS,
                                value="",
                                placeholder="Final state",
                                allow_add=False,
                            ),
                            cls="flex flex-col gap-1",
                        ),
                        Div(
                            _searchable_compact_input(
                                name="conservation",
                                options=CONSERVATION_OPTIONS,
                                value="",
                                placeholder="Conservation",
                                allow_add=False,
                            ),
                            cls="flex flex-col gap-1",
                        ),
                        id=advanced_inner_id,
                        cls="grid grid-cols-2 md:grid-cols-3 gap-2",
                    ),
                    id=advanced_id,
                    data_open="0",
                    cls=f"{'hidden ' if recipe_mode else ''}w-full relative z-0 transition-all duration-300 ease-out overflow-hidden",
                    style="max-height:0px;opacity:0;",
                ),
                id=form_id,
                cls="web_container p-3 rounded-2xl flex flex-col gap-2",
            ),
            cls="w-full",
        ),
        Div(
            H2("Macros Summary", cls="font-semibold text-gray-900"),
            (
                RecipeMacrosGrid(int(entry.get("id") or 0), per100, default_amount)
                if recipe_mode
                else Div(*_detail_macro_tiles(per100, default_amount), id=f"{root_id}_macros", cls="grid grid-cols-2 md:grid-cols-3 gap-2")
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            H2("Details", cls="font-semibold text-gray-900"),
            _detail_info_rows(info_rows),
            cls="flex flex-col gap-2 w-full",
        ),
        recipe_ingredients,
        Div(
            Button(
                edit_label,
                type="button",
                cls="""
                    web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl
                    bg-white/85 text-gray-800 border border-gray-300
                    shadow-[0_6px_20px_rgba(17,24,39,0.08)]
                """,
                **(
                    {
                        "hx_get": edit_href,
                        "hx_target": "#main_content",
                        "hx_swap": "innerHTML",
                        "hx_push_url": "true",
                    }
                    if can_edit
                    else
                    {
                        "onclick": _open_modal_js(copy_confirm_id),
                    }
                ),
            ),
            action_button,
            cls="w-full grid grid-cols-2 gap-3",
        ),
        (
            ConfirmActionModal(
                modal_id=copy_confirm_id,
                title="Create editable copy",
                question="You are editing another user's item. A personal copy will be created and opened for editing. Continue?",
                yes_button=Button(
                    "Yes",
                    type="button",
                    cls="web_button px-4 py-2 text-sm text-white border-black bg-black",
                    hx_post=f"/food/copy/{entry_type}/{entry['id']}",
                    hx_target="#main_content",
                    hx_swap="innerHTML",
                    hx_push_url="false",
                    data_skip_page_loading="true",
                    onclick=_close_modal_js(copy_confirm_id),
                ),
            )
            if not can_edit
            else ""
        ),
        (
            ConfirmActionModal(
                modal_id=delete_confirm_id,
                title=delete_title,
                question=delete_question,
                yes_button=Button(
                    "Yes",
                    type="button",
                    cls="web_button px-4 py-2 text-sm text-white",
                    style="background-color:#b91c1c;border-color:#b91c1c;",
                    hx_post=f"/food/delete/{entry_type}/{entry['id']}",
                    hx_target="#main_content",
                    hx_swap="innerHTML",
                    hx_push_url="false",
                    data_skip_page_loading="true",
                    onclick=_close_modal_js(delete_confirm_id),
                ),
            )
            if can_delete
            else ""
        ),
        Div(id=msg_id, cls="min-h-6 text-xs"),
        _searchable_autocomplete_bootstrap_script(),
        Script(src="/js/cart_units.js", defer="defer"),
        Script(src="/js/food_detail.js", defer="defer"),
        data_food_detail="true",
        data_detail_display_id=display_id,
        data_detail_select_id=select_id,
        data_detail_grams_id=grams_id,
        data_detail_side_unit_id=side_unit_id,
        data_detail_plate_value_id=plate_value_id,
        data_detail_plate_unit_id=plate_unit_id,
        data_detail_plate_unit_btn_id=plate_unit_btn_id,
        data_detail_plate_grams_id=plate_grams_id,
        data_detail_plate_equivalent_id=plate_equivalent_id,
        data_detail_leftovers_id=leftovers_id,
        data_detail_base_unit=base_unit,
        data_detail_persist_key=persist_key,
        data_hide_cart="true",
        id=root_id,
        cls="""
            flex flex-col items-center
            gap-4
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-xs
            w-full mx-auto
            md:mb-28 lg:mb-28 mb-24
        """,
    )


def RecipeIngredientPickerCard(food: dict, recipe_id: int):
    add_path = f"/food/recipe/{recipe_id}/ingredients/add/{food['entry_type']}/{food['id']}"
    subtitle = ""
    if food.get("entry_type") == "catalog":
        subtitle = (food.get("brand") or "").strip()
    elif food.get("entry_type") == "manual_intake":
        subtitle = (food.get("origin") or "").strip()

    title_node = H1(
        Span(food["name"]),
        Span(f"({subtitle})", cls="text-xs text-gray-500 font-medium") if subtitle else "",
        cls="text-left font-semibold flex flex-wrap items-baseline gap-1",
    )
    return Div(
        Div(
            title_node,
            Div(_entry_meta(food), cls="text-sm text-gray-700"),
            cls="flex flex-col gap-0.5 min-w-0",
        ),
        Div(
            AddButton(
                label="Add food",
                include_meal_selector=False,
                hx_post=add_path,
                cls="""
                    web_button
                    rounded-lg
                    border-gray-500/30 shadow-none
                    hover:bg-gray-500/20
                    px-3 h-8
                    flex items-center justify-center
                    transition-colors duration-300
                    text-xs
                """,
            ),
            cls="flex items-center gap-2 ml-3",
        ),
        cls="web_container food_entry flex items-center justify-between",
    )


def RecipeIngredientPickerList(recipe_id: int, foods: list[dict]):
    grouped = {"catalog": [], "manual_intake": []}
    for food in foods:
        entry_type = food.get("entry_type")
        if entry_type in grouped:
            grouped[entry_type].append(food)

    nodes = []
    for entry_type, title in (("catalog", "Food"), ("manual_intake", "Manual intake")):
        if not grouped[entry_type]:
            continue
        nodes.append(H2(title, cls="text-gray-700"))
        nodes.extend(RecipeIngredientPickerCard(item, recipe_id) for item in grouped[entry_type])

    if not nodes:
        return Div(H2("No items", cls="text-gray-600"), cls="flex flex-col items-center")
    return Div(*nodes, cls="flex flex-col items-center md:gap-3 lg:gap-3 gap-2 mt-4")


def RecipeIngredientPickerPage(recipe_entry: dict, foods: list[dict]):
    recipe_id = int(recipe_entry.get("id") or 0)
    return Div(
        Div(
            H1(f"Add ingredient to {recipe_entry.get('name') or 'recipe'}", cls="text-xl font-bold text-gray-900"),
            P("Search in your Food and Manual intake lists.", cls="text-sm text-gray-600"),
            cls="flex flex-col gap-1 w-full",
        ),
        RecipeIngredientSearchInput(recipe_id),
        Div(
            RecipeIngredientPickerList(recipe_id, foods),
            id="recipe-ingredient-list",
            cls="w-full",
        ),
        Div(
            Button(
                "Back to recipe",
                type="button",
                cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-white/85 text-gray-800 border border-gray-300",
                hx_get=f"/food/item/recipe/{recipe_id}",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            cls="w-full",
        ),
        data_hide_cart="true",
        cls="""
            flex flex-col items-center
            gap-4
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-xs
            w-full mx-auto
            md:mb-28 lg:mb-28 mb-24
        """,
    )


def FoodCard(food):
    add_path = f"/add_food/{food['id']}"
    add_label = "+"
    if food["entry_type"] == "manual_intake":
        add_path = f"/add_manual_intake/{food['id']}"
    if food["entry_type"] == "recipe":
        add_path = f"/add_recipe/{food['id']}"
    if food["entry_type"] == "catalog" and food.get("deleted_at") is not None:
        add_path = f"/food/copy/catalog/{food['id']}"
        add_label = "Copy"

    owner_suffix = " *" if food.get("is_owned") else ""
    name_text = f"{food['name']}{owner_suffix}"
    archived_badge = (
        Span("Archived", cls="text-[10px] font-semibold text-amber-700")
        if food.get("entry_type") == "catalog" and food.get("deleted_at") is not None
        else ""
    )
    subtitle = ""
    if food.get("entry_type") == "catalog":
        subtitle = (food.get("brand") or "").strip()
    elif food.get("entry_type") == "manual_intake":
        subtitle = (food.get("origin") or "").strip()

    title_node = H1(
        Span(name_text),
        Span(f"({subtitle})", cls="text-xs text-gray-500 font-medium") if subtitle else "",
        archived_badge,
        cls="text-left font-semibold hover:underline flex flex-wrap items-baseline gap-1",
    )

    return Div(
        Div(
            title_node,
            Div(_entry_meta(food), cls="text-sm text-gray-700"),
            cls="flex flex-col gap-0.5 min-w-0",
        ),
        Div(
            (
                FavoriteButton(food["entry_type"], food["id"], bool(food.get("favorite")))
                if not (food.get("entry_type") == "catalog" and food.get("deleted_at") is not None)
                else ""
            ),
            AddButton(label=add_label, hx_post=add_path),
            cls="flex items-center gap-2 ml-3",
        ),
        hx_get=f"/food/item/{food['entry_type']}/{food['id']}",
        hx_target="#main_content",
        hx_swap="innerHTML",
        hx_push_url="true",
        hx_trigger="click[!event.target.closest('[data-no-open]')]",
        cls="web_button food_entry flex items-center justify-between cursor-pointer",
    )


def FoodSectionsContent(foods):
    grouped = {"catalog": [], "recipe": [], "manual_intake": []}
    for food in foods:
        entry_type = food.get("entry_type")
        if entry_type in grouped:
            grouped[entry_type].append(food)

    sections = []
    for entry_type, title in (
        ("catalog", "Food"),
        ("recipe", "Recipes"),
        ("manual_intake", "Manual intake"),
    ):
        items = grouped[entry_type]
        if not items:
            continue
        sections.append(H2(title, cls="text-gray-700"))
        sections.extend(FoodCard(item) for item in items)
    return sections


def FoodList(foods):
    if not foods:
        return Div(H2("No items", cls="text-gray-600"), cls="flex flex-col items-center")

    return Div(
        *FoodSectionsContent(foods),
        id="food-list",
        cls="flex flex-col items-center md:gap-3 lg:gap-3 gap-2 mt-4 transition-all duration-150 ease-out",
    )
