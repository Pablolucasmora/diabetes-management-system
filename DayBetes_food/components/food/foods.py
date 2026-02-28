from fasthtml.common import *
from DayBetes_food.database.queries.crud import get_cart_events
from datetime import datetime

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

BTN_FILTER_CLS = """
    web_button md:text-[16px] md:p-1 lg:text-[16px] lg:p-1 
    text-sm rounded-xl p-1 w-10/12 p-2
"""


def MealSelector(connection, user_id: int, selected_id: int = None):
    events = get_cart_events(connection, user_id)

    options = [
        Option(
            event["name"] or f"Meal {event['meal_time'].strftime('%H:%M')}",
            value=str(event["id"]),
            selected=(event["id"] == selected_id)
        )
        for event in events
    ]

    if not options:
        options = [Option("- No meals yet -", value="", cls="text-gray-500/50" )]

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
            """
        ),
        Div(id="meal_name_input", cls="lg:w-40 md:w-40 w-32 bg-transparent"),
        cls="flex flex-col gap-2 items-end md:w-md lg:w-md w-xs"
    )


def Filters():
    """Filter bar for foods"""
    filters = [
        ("All", "col-start-1 col-span-1"),
        ("Foods", "col-start-2 col-span-1"),
        ("Recipes", "col-start-3 col-span-1"),
        ("Favs", "col-start-4 col-span-1"),
    ]

    buttons = [
        Button(text, cls=f"{BTN_FILTER_CLS} {classes}")
        for text, classes in filters
    ]

    return Div(
        *buttons,
        cls="md:w-md lg:w-md w-xs grid grid-cols-4 grid-rows-1 justify-center md:gap-3 lg:gap-3 gap-1 transition-all"
    )


def SearchInput():
    """Search input with HTMX"""
    return Input(
        inputmode="text",
        placeholder="What did you eat?",
        name="search",
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
        hx_get="/search_food",
        hx_target="#food-list",
        hx_trigger="keyup changed delay:300ms",
        hx_swap="innerHTML"
    )


def FoodCard(food):
    """Individual food card"""
    return Div(
        H1(food["name"], cls="col-start-1 col-span-4"),
        Div(f"{food['carbs_100g']} CH", cls="text-sm col-start-1 col-span-2"),
        AddButton(hx_post=f"/add_food/{food['id']}"),
        cls="web_button food_entry grid grid-cols-5 grid-rows-2 items-center"
    )


def AddButton(**attrs):
    """Add food button"""
    attrs.setdefault("hx_include", "#meal_selector")
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
        **on_after(),
        **attrs
    )


def FoodList(foods):
    """Food list"""
    if not foods:
        return Div(H2("No foods", cls="text-gray-500/50"), cls="flex flex-col items-center")

    return Div(
        H2("Catalog", cls="text-gray-500/50"),
        *[FoodCard(food) for food in foods],
        id="food-list",
        cls="flex flex-col items-center md:gap-3 lg:gap-3 gap-2 mt-4"
    )
