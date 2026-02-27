from fasthtml.common import *
from DayBetes_food.database.connection import get_connection
from DayBetes_food.components.menu.layout import IslaFlotante, carrito

# ============================================
# COMPONENTES BASE
# ============================================



def render_page(req, contenido_fn, mostrar_carrito=True):
    """
    Helper para renderizar páginas con estructura común.
    """
    
    
    conexion = get_connection()
    
    if "hx-request" in req.headers:
        return contenido_fn(conexion)
    else:
        return Div(
            Div(contenido_fn(conexion), id="main_content"), 
            IslaFlotante(), 
            carrito(display=mostrar_carrito)
        )
