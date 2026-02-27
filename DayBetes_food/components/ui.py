from fasthtml.common import *
from DayBetes_food.database.connection import get_connection
from DayBetes_food.components.menu.layout import FloatingIsland, Cart

# ============================================
# BASE COMPONENTS
# ============================================

def render_page(request, content_fn, show_cart=True):
    """
    Helper to render pages with a common structure.
    """
    
    connection = get_connection()
    
    if "hx-request" in request.headers:
        return content_fn(connection)
    else:
        return Div(
            Div(content_fn(connection), id="main_content"),
            FloatingIsland(),
            Cart(display=show_cart)
        )