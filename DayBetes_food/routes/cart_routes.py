from fasthtml.common import *
from DayBetes_food.components.cart.cart_main import cart_main
from DayBetes_food.components.ui import render_page


def setup_cart_routes(rt):
    @rt("/cart")
    def get(req):
        return render_page(req, cart_main, show_cart=False)
