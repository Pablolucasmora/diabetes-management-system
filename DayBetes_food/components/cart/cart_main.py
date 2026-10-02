from fasthtml.common import *

from DayBetes_food.components.cart.cart_components import CartCard
from DayBetes_food.components.injection_zone import asset_busted


def cart_events_list(events, portions_by_event, plates_by_event=None):
    """
    Local container of the event cards (#cart_events_list). It is the target
    of the actions that can reorder the list (e.g. meal_hour, which changes
    the `meal_time DESC` order) without reloading the rest of the page
    (decision 2026-09-10, local cart refresh).
    """
    plates_by_event = plates_by_event or {}
    return Div(
        *[
            CartCard(
                event,
                portions_by_event.get(event.id, []),
                plates_by_event.get(event.id, []),
            )
            for event in events
        ],
        id="cart_events_list",
        cls="flex flex-col items-center gap-6 w-full",
    )


def cart_main(events, portions_by_event, plates_by_event=None, oob: bool = False):
    """
    `oob=True` marks the root Div (#cart_body) as an out-of-band swap
    (hx-swap-oob), so that an endpoint that deletes/confirms the last planned
    event can inject the "empty cart" state without reloading the rest of
    the page (decision 2026-09-10, local cart refresh).
    """
    oob_attrs = {"hx_swap_oob": "true"} if oob else {}

    if not events:
        return Div(
            Div(
                Img(src="/images/ui/cart.svg", alt="", cls="w-10 h-10 opacity-70"),
                H1("Your cart is empty", cls="text-lg font-semibold text-gray-700"),
                P("Add ingredients from Food to start planning your meal.", cls="text-sm text-gray-500 text-center"),
                Button(
                    "Go to Food",
                    cls="web_button px-4 py-2 text-sm",
                    hx_get="/food",
                    hx_target="#main_content",
                    hx_swap="innerHTML",
                    hx_push_url="true",
                    **{
                        "hx-on:click": (
                            "var b=document.querySelector('#cart_button');"
                            "if(!b) return;"
                            "b.style.visibility='';"
                            "b.style.opacity='';"
                            "b.style.pointerEvents='';"
                            "b.classList.remove('invisible','opacity-0','pointer-events-none');"
                            "requestAnimationFrame(function(){ b.classList.add('opacity-100'); });"
                        )
                    },
                ),
                cls="""
                    web_container p-6 rounded-3xl
                    md:w-md lg:w-md w-[90vw]
                    mt-5
                    flex flex-col items-center gap-3
                """
            ),
            id="cart_body",
            cls="""
                flex flex-col items-center
                justify-center gap-6
                md:mt-7 lg:mt-7 mt-2
                transition-[width,margin,padding] duration-150
            """,
            data_hide_cart="true",
            **oob_attrs,
        )

    return Div(
        H1("Food cart", cls="text-xl font-bold"),
        cart_events_list(events, portions_by_event, plates_by_event),
        # With cache busting: /js/ is served with a one-week max-age
        # (main.py), so without the ?v= the browser would keep running the
        # previous version of the file after every change.
        Script(src=asset_busted("/js/cart_units.js"), defer="defer"),
        id="cart_body",
        data_hide_cart="true",
        cls="""
            flex flex-col items-center
            gap-6
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-[90vw]
            mx-auto
            md:mb-28 lg:mb-28 mb-24
            transition-[width,margin,padding] duration-150
        """,
        **oob_attrs,
    )
