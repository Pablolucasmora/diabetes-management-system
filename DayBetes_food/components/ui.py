from fasthtml.common import *
from fastcore.xml import to_xml
from starlette.responses import HTMLResponse
from DayBetes_food.database.connection import get_connection
from DayBetes_food.components.menu.layout import FloatingIsland, Cart
from DayBetes_food.config import CSRF_COOKIE_NAME
from DayBetes_food.components.injection_zone import asset_busted

# ============================================
# BASE COMPONENTS
# ============================================

def PageLoadingOverlay():
    return Div(
        Div(
            Div(
                cls="h-8 w-8 rounded-full",
                style="border:2px solid #d1d5db; border-top-color:#4b5563; animation: dbspin .8s linear infinite;",
            ),
            P("Loading...", cls="text-sm text-gray-700"),
            cls="web_container px-4 py-3 rounded-2xl flex items-center gap-3"
        ),
        id="page_loading_overlay",
        cls="""
            fixed inset-0 z-40
            flex items-center justify-center
            bg-[#f6f2eb]/35 backdrop-blur-[1px]
            pointer-events-none opacity-0 invisible
            transition-opacity duration-200
        """
    )

def AppToast():
    """
    Canal único de avisos de error de la web (decisión 2026-09-10, hallazgo 37
    de audit/audit_intake_event.md).

    Las rutas HTMX conservan su status semántico (`422`/`404`/`409`, §3.2 y
    §3.6 de error_conventions.md) y devuelven cuerpo vacío —htmx no hace swap
    ante un `4xx`—, pero acompañan la respuesta con el código y el mensaje
    público del catálogo de errores. `static/js/app_toast.js` los pinta aquí,
    de modo que un error deja de ser invisible sin que ninguna ruta tenga que
    reconstruir su fragmento (error_conventions.md §7: "no devolver un cuerpo
    vacío para un error que el usuario necesita ver").
    """
    return Div(
        Div(
            id="app_toast_message",
            cls="text-sm md:text-base",
        ),
        id="app_toast",
        role="status",
        aria_live="polite",
        cls="""
            fixed inset-x-0 bottom-24 z-[80]
            mx-auto w-[92vw] max-w-md
            web_container px-4 py-3 rounded-2xl
            border border-red-200 bg-red-50 text-red-700
            opacity-0 invisible pointer-events-none
            transition-opacity duration-200
        """,
    )


def _clean_fragment(fragment):
    if fragment is None or isinstance(fragment, bool):
        return None
    if isinstance(fragment, tuple):
        cleaned = tuple(item for item in (_clean_fragment(x) for x in fragment) if item is not None)
        return cleaned
    if isinstance(fragment, list):
        cleaned = [item for item in (_clean_fragment(x) for x in fragment) if item is not None]
        return cleaned
    return fragment

def _safe_fragment_to_html(fragment) -> str:
    fragment = _clean_fragment(fragment)
    if fragment is None:
        return ""
    try:
        return str(to_xml(fragment))
    except TypeError:
        if isinstance(fragment, tuple):
            cleaned = tuple(item for item in fragment if not isinstance(item, bool))
            return str(to_xml(cleaned))
        raise

def render_fragment(fragment, status_code: int = 200):
    return HTMLResponse(_safe_fragment_to_html(fragment), status_code=status_code)

def _base_html_shell(content_html: str) -> str:
    return f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="DayBetes Food: plan meals, track ingredients, and manage macros for diabetes nutrition.">
    <title>DayBetes</title>
    <link rel="icon" href="/images/ui/Clock_Page.svg">
    <link rel="stylesheet" href="{asset_busted("/css/output.css")}">
    <meta name="csrf-cookie-name" content="{CSRF_COOKIE_NAME}">
    <script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.7/dist/htmx.min.js" defer></script>
    <script src="https://cdn.jsdelivr.net/gh/answerdotai/fasthtml-js@1.0.12/fasthtml.js" defer></script>
    <script src="https://cdn.jsdelivr.net/gh/answerdotai/surreal@main/surreal.js" defer></script>
    <script src="https://cdn.jsdelivr.net/gh/gnat/css-scope-inline@main/script.js" defer></script>
    <script src="/js/csrf.js" defer></script>
    <script src="/js/page_loading.js" defer></script>
    <script src="/js/app_toast.js" defer></script>
    <script src="/js/island_indicator.js" defer></script>
    <script src="/js/browser_tweaks.js" defer></script>
    <script src="/js/food_quick_create.js?v=18" defer></script>
    <script src="/js/rescue_power_panel.js?v=1" defer></script>
    <script src="/js/cart_units.js" defer></script>
    <script src="/js/food_detail.js" defer></script>
    <script src="/js/scanner.js" defer></script>
    <style>
      body, html {{
        background-color: #f6f2eb;
        scrollbar-gutter: stable;
      }}
      @keyframes dbspin {{
        to {{ transform: rotate(360deg); }}
      }}
    </style>
  </head>
  <body>
    {content_html}
  </body>
</html>"""

def render_page(request, content_fn, show_cart=True):
    """
    Helper to render pages with a common structure.
    """
    with get_connection() as connection:
        if request.headers.get("HX-Request") == "true":
            fragment = content_fn(connection)
            return render_fragment(fragment)

        page_fragment = Div(
            Main(
                content_fn(connection),
                id="main_content",
                style="transition: opacity 220ms ease;",
            ),
            FloatingIsland(),
            Cart(display=show_cart),
            PageLoadingOverlay(),
            AppToast(),
        )
        return HTMLResponse(_base_html_shell(_safe_fragment_to_html(page_fragment)))
