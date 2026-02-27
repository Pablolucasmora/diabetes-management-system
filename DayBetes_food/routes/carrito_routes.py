from fasthtml.common import *
from DayBetes_food.components.carrito.carrito_main import carrito_main
from DayBetes_food.components.ui import render_page


def setup_carrito_routes(rt):
    @rt("/carrito")
    def get(req):
        return render_page(req, carrito_main, mostrar_carrito=False)