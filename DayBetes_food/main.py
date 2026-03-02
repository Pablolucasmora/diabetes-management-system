from fasthtml.common import *
from starlette.middleware.gzip import GZipMiddleware

from DayBetes_food.database.db_init import init_db
from DayBetes_food.routes.food_routes import setup_food_routes
from DayBetes_food.routes.main_routes import setup_main_routes
from DayBetes_food.routes.cart_routes import setup_cart_routes
from DayBetes_food.routes.stats_routes import setup_stats_routes
from DayBetes_food.routes.settings_routes import setup_settings_routes


# 1. Header configuration
css = Link(rel="stylesheet", href="/css/output.css")
jsdelivr_preconnect = Link(rel="preconnect", href="https://cdn.jsdelivr.net", crossorigin="anonymous")
jsdelivr_dns_prefetch = Link(rel="dns-prefetch", href="//cdn.jsdelivr.net")
htmx_js = Script(src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.7/dist/htmx.min.js", defer=True)
fasthtml_js = Script(src="https://cdn.jsdelivr.net/gh/answerdotai/fasthtml-js@1.0.12/fasthtml.js", defer=True)
surreal_js = Script(src="https://cdn.jsdelivr.net/gh/answerdotai/surreal@main/surreal.js", defer=True)
css_scope_inline_js = Script(src="https://cdn.jsdelivr.net/gh/gnat/css-scope-inline@main/script.js", defer=True)
loading_js = Script(src="/js/page_loading.js", defer=True)
island_indicator_js = Script(src="/js/island_indicator.js", defer=True)
browser_tweaks_js = Script(src="/js/browser_tweaks.js", defer=True)

# 2. Application title
title_tag = "DayBetes"

# 3. Favicon configuration (using an SVG file as favicon)
favicon_tag = Link(rel="icon", href="/images/ui/Clock_Page.svg")

css_background = """
body, html {
    background-color: #f6f2eb;
    scrollbar-gutter: stable;
}
@keyframes dbspin {
    to { transform: rotate(360deg); }
}

/* iOS Safari compatibility mode */
.ios-safari #food_top_bar {
    -webkit-transform: translateZ(0);
    transform: translateZ(0);
    -webkit-backface-visibility: hidden;
    backface-visibility: hidden;
}
.ios-safari #page_loading_overlay {
    -webkit-backdrop-filter: none !important;
    backdrop-filter: none !important;
    background-color: rgba(246, 242, 235, 0.62) !important;
}
.ios-safari #island_active_indicator,
.ios-safari label[data-nav-item],
.ios-safari label[data-nav-item] img {
    transition-duration: 250ms !important;
}
"""

shared_hdrs = (
    css,
    loading_js,
    island_indicator_js,
    browser_tweaks_js,
    favicon_tag,
    Style(css_background),
    Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
    Meta(
        name="description",
        content="DayBetes Food: plan meals, track ingredients, and manage macros for diabetes nutrition."
    ),
)

optimized_hdrs = (
    jsdelivr_preconnect,
    jsdelivr_dns_prefetch,
    htmx_js,
    fasthtml_js,
    surreal_js,
    css_scope_inline_js,
    *shared_hdrs,
)

app_kwargs = dict(
    title=title_tag,
    htmlkw={"lang": "es"},
    static_path='DayBetes_food/static',
    pico=False,
)

try:
    app, rt = fast_app(
        **app_kwargs,
        default_hdrs=False,
        hdrs=optimized_hdrs,
    )
except TypeError:
    app, rt = fast_app(
        **app_kwargs,
        hdrs=shared_hdrs,
    )

app.add_middleware(GZipMiddleware, minimum_size=512)

STATIC_CACHE_CONTROL = "public, max-age=604800"
ASSET_PREFIXES = ("/css/", "/js/", "/images/")

@app.middleware("http")
async def add_asset_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith(ASSET_PREFIXES):
        response.headers.setdefault("Cache-Control", STATIC_CACHE_CONTROL)
    return response

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
