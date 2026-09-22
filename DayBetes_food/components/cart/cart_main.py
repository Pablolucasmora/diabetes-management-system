from fasthtml.common import *

from DayBetes_food.components.cart.cart_components import CartCard
from DayBetes_food.components.injection_zone import asset_busted


def cart_events_list(events, portions_by_event, plates_by_event=None):
    """
    Contenedor local de las tarjetas de evento (#cart_events_list). Es el
    target de las acciones que pueden reordenar la lista (p.ej. meal_hour,
    que cambia el orden `meal_time DESC`) sin necesidad de recargar el resto
    de la página (decisión 2026-09-10, refresco local del carrito).
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
    `oob=True` marca el Div raíz (#cart_body) como swap fuera de banda
    (hx-swap-oob), para que un endpoint que borra/confirma el último evento
    planificado pueda inyectar el estado "carrito vacío" sin recargar el
    resto de la página (decisión 2026-09-10, refresco local del carrito).
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
        # Con cache busting: /js/ se sirve con max-age de una semana
        # (main.py), así que sin el ?v= el navegador seguiría ejecutando la
        # versión anterior del fichero tras cada cambio.
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
