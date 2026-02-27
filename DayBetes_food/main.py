from fasthtml.common import *

from DayBetes_food.database.db_init import init_db
from DayBetes_food.routes.food_routes import setup_food_routes
from DayBetes_food.routes.main_routes import setup_main_routes
from DayBetes_food.routes.carrito_routes import setup_carrito_routes


# 1. Configuración de cabeceras (Tu diseño original)
css = Link(rel="stylesheet", href="css/output.css")

# 1. Definimos el título con el emoji integrado
title_tag = "DayBetes"

# 2. Truco pro: Usar un emoji como Favicon oficial sin archivos externos
# Esto le dice al navegador: "mi icono es este texto SVG"
favicon_tag = Link(rel="icon", href="images/ui/Clock_Page.svg")

css_background = """
body, html {
    background-color: #f6f2eb;
}
"""

app, rt = fast_app(
    title=title_tag,
    hdrs=(css, 
          favicon_tag, 
          Style(css_background),
          Meta(name="viewport", content="width=device-width, initial-scale=1.0")
), 
    static_path='DayBetes_food/static', 
    pico=False
)

# --- TUS COMPONENTES (Estética original recuperada) ---


init_db()

setup_main_routes(rt)

setup_food_routes(rt)

setup_carrito_routes(rt)