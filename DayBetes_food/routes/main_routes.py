from fasthtml.common import *
from DayBetes_food.components.menu.main_menu import main_menu
from DayBetes_food.components.scanner.scanner_main import scanner_main
from DayBetes_food.components.ui import render_page


def setup_main_routes(rt):
    @rt("/")
    def get():
        return RedirectResponse(url="/menu")

    @rt("/menu")
    def get(req):
        return render_page(req, main_menu)

    @rt("/scanner")
    def get(req):
        return render_page(req, lambda _: scanner_main())
