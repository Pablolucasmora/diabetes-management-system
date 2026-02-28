from fasthtml.common import *
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

def render_page(request, content_fn, show_cart=True):
    """
    Helper to render pages with a common structure.
    """
    with get_connection() as connection:
        if request.headers.get("HX-Request") == "true":
            return content_fn(connection)

        return Div(
            Div(
                content_fn(connection),
                id="main_content",
                style="transition: opacity 280ms ease, filter 280ms ease;",
            ),
            FloatingIsland(),
            Cart(display=show_cart),
            PageLoadingOverlay(),
        )
