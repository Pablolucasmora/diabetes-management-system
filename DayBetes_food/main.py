from fasthtml.common import *

from DayBetes_food.database.db_init import init_db
from DayBetes_food.routes.food_routes import setup_food_routes
from DayBetes_food.routes.main_routes import setup_main_routes
from DayBetes_food.routes.cart_routes import setup_cart_routes
from DayBetes_food.routes.stats_routes import setup_stats_routes
from DayBetes_food.routes.settings_routes import setup_settings_routes


# 1. Header configuration
css = Link(rel="stylesheet", href="css/output.css")
loading_js = Script(src="js/page_loading.js")
island_indicator_js = Script(src="js/island_indicator.js")

# 2. Application title
title_tag = "DayBetes"

# 3. Favicon configuration (using an SVG file as favicon)
favicon_tag = Link(rel="icon", href="images/ui/Clock_Page.svg")

css_background = """
body, html {
    background-color: #f6f2eb;
    scrollbar-gutter: stable;
}
@keyframes dbspin {
    to { transform: rotate(360deg); }
}
"""

app, rt = fast_app(
    title=title_tag,
    hdrs=(
        css,
        loading_js,
        island_indicator_js,
        favicon_tag,
        Style(css_background),
        Meta(name="viewport", content="width=device-width, initial-scale=1.0")
    ),
    static_path='DayBetes_food/static',
    pico=False
)

# --- COMPONENT INITIALIZATION ---

def _init_db_on_startup():
    init_db()

if hasattr(app, "on_event"):
    app.on_event("startup")(_init_db_on_startup)
else:
    _init_db_on_startup()

setup_main_routes(rt)

setup_food_routes(rt)

setup_cart_routes(rt)

setup_stats_routes(rt)

setup_settings_routes(rt)
