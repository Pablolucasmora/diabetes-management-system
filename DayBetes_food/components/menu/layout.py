from fasthtml.common import *
from DayBetes_food.config import ASSISTANT_ENABLED

def BlockIsland(text, icon="/images/ui/menu.svg", name="nav", value="home", **hx):
    # Put network-triggering htmx attrs on the radio input to avoid
    # duplicate requests caused by label click forwarding to its control.
    input_hx = {}
    for key in ("hx_get", "hx_target", "hx_swap", "hx_push_url", "hx_trigger", "data_preload"):
        if key in hx:
            input_hx[key] = hx.pop(key)
    input_hx.setdefault("hx_trigger", "click")
    input_hx.setdefault("hx_params", "none")

    return Label(
        Input(
            type="radio",
            name=name,
            value=value,
            cls="hidden peer",
            **input_hx,
        ),

        Img(id=value, src=icon, alt="", cls="""
            w-6 h-6
            text-lg md:text-xl 
            transition-all duration-300
            group-has-[:checked]:scale-110
        """),

        P(text, cls="""
            hidden md:block mt-1
            text-[10px] font-bold uppercase tracking-tighter
        """),

        cls="""
            relative z-10
            flex flex-col items-center justify-center
            p-2 md:p-3 
            rounded-full
            cursor-pointer
            transition-all duration-300 ease-in-out
            w-14 md:w-24
            border-none
            group

            bg-transparent
            hover:shadow-md
        """,
        data_nav_item=value,
        **hx
    )

def DiaBotIsland():
    """DiaBot in the middle of the island, reachable from every page (frontend
    §9.11, decisions 2026-11-21): an item like the others, larger, with its face
    centred (diabot_island.svg is cropped to the drop) and, at rest, nothing
    under it, as the others. Chosen, the island's indicator slides under it as under any
    other item, round because the item is square, as big as the circle at rest:
    chosen, the circle and the face shrink into the island, which keeps its width, while the indicator slides in and
    fills the whole circle (.island_bump in input.css). Negative vertical margins:
    it sticks out of the island a little instead of making it taller."""
    return Div(_diabot_item(), cls="relative flex items-center md:mx-1 -my-[calc(var(--bump-rest)/2-12px)] md:-my-[calc(var(--bump-rest)/2-16px)]")


def _diabot_item():
    return Label(
        Input(
            type="radio",
            name="nav",
            value="assistant",
            cls="hidden peer",
            hx_get="/assistant",
            hx_target="#main_content",
            hx_push_url="true",
            hx_trigger="click",
            hx_params="none",
            # A preload writes nothing (code_conventions.md §9.2): the page marks
            # its turns seen once shown.
            data_preload="true",
        ),
        Img(
            src="/images/diabot/diabot_island.svg",
            alt="",
            cls="relative z-10 w-11 h-11 md:w-14 md:h-14 transition-transform duration-300 group-has-[:checked]:scale-[0.7]",
        ),
        aria_label="DiaBot",
        cls="""
            relative z-10 group
            flex items-center justify-center
            w-[var(--bump-rest)] h-[var(--bump-rest)]
            rounded-full cursor-pointer
            bg-transparent
            transition-shadow duration-300 ease-in-out
        """,
        data_nav_item="assistant",
        **{"hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });"},
    )


def ReviewDot(count: int):
    """The dot over Food while there are provisional foods (frontend §9.3)."""
    if not count:
        return Span(aria_hidden="true", cls="hidden")
    return Span(
        Span(f"{count} foods to review", cls="sr-only"),
        cls="block h-2.5 w-2.5 rounded-full bg-amber-500 ring-2 ring-white",
    )


def FloatingIsland():
    show_cart_js = """
        var b = document.querySelector('#cart_button');
        if(!b) return;
        b.style.visibility = '';
        b.style.opacity = '';
        b.style.pointerEvents = '';
        b.classList.remove('invisible','opacity-0','pointer-events-none');
        requestAnimationFrame(function(){ b.classList.add('opacity-100'); });
    """
    scroll_top_js = "window.scrollTo({ top: 0, behavior: 'auto' });"

    return Div(
        # With DiaBot the island bulges around it, in one glass with no seam
        # (frontend_conventions.md §9.11; .island_* in input.css): its shadow,
        # then a single glass layer cut to the island plus a circle, then the
        # caps' rim, and the island on top with only its own rim (holed there).
        # One layer and not two: two glasses never look the same. DiaBot is
        # always the middle item, so the circle is centred by CSS alone;
        # island_indicator.js only gives the island's height (--island-h).
        *(
            (
                Span(aria_hidden="true", cls="island_shadow"),
                Span(aria_hidden="true", cls="island_fill"),
                Span(aria_hidden="true", cls="island_bump_rim"),
            )
            if ASSISTANT_ENABLED
            else ()
        ),
        Div(
            Div(
                id="island_active_indicator",
                cls="""
                    absolute left-0 top-0 z-0
                    rounded-full bg-line-soft
                    ring-1 ring-white/50 shadow-inner
                    transition-[left,top,width,height,opacity] duration-300 ease-in-out
                    pointer-events-none
                    opacity-0
                """,
            ),
            BlockIsland("Menu", icon="/images/ui/menu.svg", value="menu", hx_get="/menu", data_preload="true", hx_target="#main_content", hx_swap="innerHTML", hx_push_url="true", **{"hx-on:click": show_cart_js}),
            BlockIsland("Stats", icon="/images/ui/stats.svg", value="stats", hx_get="/stats", data_preload="true", hx_target="#main_content", hx_push_url="true", **{"hx-on:click": scroll_top_js}),
            DiaBotIsland() if ASSISTANT_ENABLED else "",
            Div(
                BlockIsland("Food", icon="/images/ui/food.svg", value="food", hx_get="/food", data_preload="true", hx_target="#main_content", hx_push_url="true", **{"hx-on:click": show_cart_js}),
                # Asked for apart: render_page never reads the database (§1.4).
                Div(
                    id="island_review_dot",
                    hx_get="/menu/review_dot",
                    hx_trigger="load, dbReviewChanged from:body",
                    hx_swap="innerHTML",
                    data_skip_page_loading="true",
                    cls="absolute top-1.5 right-3 md:right-5 z-20 pointer-events-none",
                ),
                cls="relative",
            ),
            BlockIsland("Settings", icon="/images/ui/settings.svg", value="settings", hx_get="/settings", data_preload="true", hx_target="#main_content", hx_push_url="true", **{"hx-on:click": scroll_top_js}),
            cls="""
                relative
                flex items-center justify-center
                gap-2 md:gap-3
                p-2
                rounded-full
            """ + (" island_glass" if ASSISTANT_ENABLED else " web_glass overflow-hidden")
        ),
        cls="""
            fixed bottom-[max(2.5rem,calc(env(safe-area-inset-bottom)+0.5rem))] left-1/2 -translate-x-1/2
            z-50
            island_bump
        """,
        id="floating_island",
    )

def IslandLogo():
    return Div(
        Img(id="logo", src="/images/ui/Logo_DayBetes.webp", alt="DayBetes logo",
            cls="""
                lg:w-52 md:w-52
                w-36 
                transition-all 
            """
        ),
        cls="""
            web_glass
            rounded-4xl
            px-10 py-3 md:mt-2 lg:mt-2 mt-0 m-6 z-50
            fixed top-[calc(env(safe-area-inset-top)+0.75rem)]
        """
    )

def Cart(display=True):
    base_classes="""
        fixed md:bottom-35 lg:bottom-35 bottom-32
        left-1/2 -translate-x-1/2 md:translate-x-29
        lg:translate-x-29 translate-x-20
        transition-opacity duration-[100ms] ease-out
        web_button
        md:p-4 lg:p-4 p-3
        rounded-3xl md:rounded-4xl lg:rounded-4xl md:w-22 lg:w-22
        opacity-100
    """

    if not display:
        base_classes += " invisible opacity-0 pointer-events-none"

    return Div(
        Img(src="/images/ui/cart.svg", alt="", cls="w-6 h-6 justify-self-center"),
        P("Cart", cls="""
            hidden md:block mt-1
            text-[10px] text-center font-bold uppercase tracking-tighter
        """),
        cls=base_classes,
        id="cart_button",
        hx_get="/cart",
        hx_target="#main_content",
        hx_push_url="true"
    )
