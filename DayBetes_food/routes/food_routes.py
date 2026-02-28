from fasthtml.common import *
from datetime import datetime
from DayBetes_food.components.food.food_main import food_main
from DayBetes_food.components.ui import render_page
from DayBetes_food.database.queries.crud import (
    get_all_catalog,
    add_intake_event,
    add_portion_detail,
    get_catalog_item,
    get_default_user_id,
    get_intake_event,
)
from DayBetes_food.components.food.foods import FoodCard, on_after
from DayBetes_food.database.connection import get_connection


def setup_food_routes(rt):
    
    @rt("/food")
    def get(request):
        return render_page(request, food_main)
    
    @rt("/search_food")
    def get(request: Request, search: str):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            results = get_all_catalog(connection, search)
        
        if not results:
            return ""

        html_list = [FoodCard(food) for food in results]

        return H2("Catalog", cls="text-gray-500/50"), *html_list

    @rt("/add_food/{food_id}")
    def post(request: Request, food_id: int, intake_event_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return HTMLResponse("No users", status_code=400)

            event_id = None
            if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                event_id = int(intake_event_id)
            else:
                event_id = add_intake_event(
                    connection,
                    users_id=user_id,
                    state="planned",
                )

            catalog_item = get_catalog_item(connection, food_id)
            portion_amount = 100
            if catalog_item and catalog_item.get("default_portion"):
                portion_amount = catalog_item["default_portion"]

            portion_id = None
            if event_id:
                event_data = get_intake_event(connection, event_id)
                offset_minutes = 0
                if event_data and event_data.get("meal_time"):
                    delta = datetime.now() - event_data["meal_time"]
                    offset_minutes = int(delta.total_seconds() // 60)

                portion_id = add_portion_detail(
                    connection,
                    origin="catalog",
                    origin_id=food_id,
                    destination="intake_event",
                    destination_id=event_id,
                    amount_g=portion_amount,
                    offset_minutes=offset_minutes,
                )

            headers = {"HX-Trigger": "addSuccess" if portion_id else "addError"}
            return HTMLResponse("", headers=headers)
    
    @rt("/meal_selector_input")
    def get(request: Request, intake_event_id: str):
        if intake_event_id != "0":
            return ""
        
        return Div(
            Input(
                placeholder="Meal name",
                name="meal_name",
                id="meal_name_input_text",
                autofocus=True,
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
                hx_include="this",
                **on_after("add_meal_btn")
            ),
            Button(
                "Add",
                id="add_meal_btn",
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
                hx_include="#meal_name_input_text",
                **on_after()
            ),
            cls="flex gap-2 w-full"        
            )

    @rt("/create_named_event")
    def post(request: Request, meal_name: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return HTMLResponse("No users", status_code=400)

            event_id = add_intake_event(
                connection,
                users_id=user_id,
                state="planned",
                name=meal_name or None,
            )

            headers = {"HX-Trigger": "addSuccess" if event_id else "addError"}
            return HTMLResponse("", headers=headers)
