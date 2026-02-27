from fasthtml.common import *
from DayBetes_food.components.food.food_main import food_main
from DayBetes_food.components.ui import render_page
from DayBetes_food.database.queries.crud import get_all_catalog, add_intake_event, get_all_users
from DayBetes_food.components.food.foods import FoodCard, AddButton
from DayBetes_food.database.connection import get_connection


def setup_food_routes(rt):
    
    @rt("/food")
    def get(request):
        return render_page(request, food_main)
    
    @rt("/search_food")
    def get(request: Request, search: str):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        connection = get_connection()
        results = get_all_catalog(connection, search)
        
        if not results:
            return ""

        html_list = [FoodCard(food) for food in results]

        return H2("Catalog", cls="text-gray-500/50"), *html_list

    @rt("/add_food/{food_id}")
    def post(request: Request, food_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        
        connection = get_connection()
        
        users = get_all_users(connection)
        if not users:
            return HTMLResponse("No users", status_code=400)
        
        user_id = users[0]["id"]
        
        event_id = add_intake_event(
            connection,
            users_id=user_id,
            state="planned"
        )
        
        headers = {"HX-Trigger": "addSuccess" if event_id else "addError"}
        return HTMLResponse("", headers=headers)
    
    @rt("/meal_selector_input")
    def get(request: Request, intake_event_id: str):
        if intake_event_id != "0":
            return ""
        
        on_after = {"hx-on::after-request": """
            var trigger = event.detail.xhr.getResponseHeader('HX-Trigger');
            var btn = this;
            if(trigger === 'addSuccess') {
                btn.classList.add('bg-green-400');
                setTimeout(function() { btn.classList.remove('bg-green-400'); }, 300);
            } else {
                btn.classList.add('bg-red-400');
                setTimeout(function() { btn.classList.remove('bg-red-400'); }, 300);
            }
        """}
        
        return Div(
            Input(
                placeholder="Meal name",
                name="meal_name",
                id="meal_name_input_text",
                autofocus=True,
                cls="""
                border-[1px] px-2 py-1
                md:text-sm lg:text-sm text-xs
                shadow-sm rounded-md focus:outline-none
                border-gray-300 w-full
                """,
                hx_post="/create_named_event",
                hx_trigger="keyup[keyCode==13]",
                hx_target="#meal_name_input",
                hx_swap="none",
                hx_include="this"
            ),
            Button(
                "Add",
                cls="""
                border-[1px] px-2 py-1
                md:text-sm lg:text-sm text-xs
                shadow-sm rounded-md cursor-pointer
                border-gray-300 hover:bg-gray-200
                transition-colors duration-300
                """,
                hx_post="/create_named_event",
                hx_target="#meal_selector_input_wrapper",
                hx_swap="none",
                hx_include="#meal_name_input_text",
                **on_after
            ),
            cls="flex gap-2 w-full"
        )

    @rt("/create_named_event")
    def post(request: Request, meal_name: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        
        connection = get_connection()
        
        users = get_all_users(connection)
        if not users:
            return HTMLResponse("No users", status_code=400)
        
        user_id = users[0]["id"]
        
        event_id = add_intake_event(
            connection,
            users_id=user_id,
            state="planned",
            name=meal_name or None
        )
        
        headers = {"HX-Trigger": "addSuccess" if event_id else "addError"}
        return HTMLResponse("", headers=headers)