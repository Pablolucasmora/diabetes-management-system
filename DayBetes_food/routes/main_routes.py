from fasthtml.common import * 
from DayBetes_food.components.menu.menu_main import menu_principal
from DayBetes_food.components.ui import render_page


def setup_main_routes(rt):
    @rt("/")
    def get():
        return RedirectResponse(url="/menu")

    @rt("/menu")
    def get(req):
        return render_page(req, menu_principal)