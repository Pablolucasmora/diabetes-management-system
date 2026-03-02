from fasthtml.common import *
from fastcore.xml import to_xml
from starlette.responses import HTMLResponse
from DayBetes_food.database.connection import get_connection
from DayBetes_food.components.menu.layout import FloatingIsland, Cart

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

def _safe_fragment_to_html(fragment) -> str:
    try:
        return str(to_xml(fragment))
    except TypeError:
        if isinstance(fragment, tuple):
            cleaned = tuple(item for item in fragment if not isinstance(item, bool))
            return str(to_xml(cleaned))
        raise

def _base_html_shell(content_html: str) -> str:
    return f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="DayBetes Food: plan meals, track ingredients, and manage macros for diabetes nutrition.">
    <title>DayBetes</title>
    <link rel="icon" href="/images/ui/Clock_Page.svg">
    <link rel="stylesheet" href="/css/output.css">
    <script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.7/dist/htmx.min.js" defer></script>
    <script src="https://cdn.jsdelivr.net/gh/answerdotai/fasthtml-js@1.0.12/fasthtml.js" defer></script>
    <script src="https://cdn.jsdelivr.net/gh/answerdotai/surreal@main/surreal.js" defer></script>
    <script src="https://cdn.jsdelivr.net/gh/gnat/css-scope-inline@main/script.js" defer></script>
    <script src="/js/csrf.js" defer></script>
    <script src="/js/page_loading.js" defer></script>
    <script src="/js/island_indicator.js" defer></script>
    <script src="/js/browser_tweaks.js" defer></script>
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
            return HTMLResponse(_safe_fragment_to_html(fragment))

        page_fragment = Div(
            Main(
                content_fn(connection),
                id="main_content",
                style="transition: opacity 220ms ease;",
            ),
            FloatingIsland(),
            Cart(display=show_cart),
            PageLoadingOverlay(),
        )
        return HTMLResponse(_base_html_shell(_safe_fragment_to_html(page_fragment)))
