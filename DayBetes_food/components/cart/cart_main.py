from fasthtml.common import *

from DayBetes_food.components.cart.cart_components import CartCard


def cart_main(events, portions_by_event):
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
                    md:w-md lg:w-md w-xs
                    mt-5
                    flex flex-col items-center gap-3
                """
            ),
            cls="""
                flex flex-col items-center
                justify-center gap-6
                md:mt-7 lg:mt-7 mt-2
                transition-[width,margin,padding] duration-150
            """,
            data_hide_cart="true",
        )

    event_cards = [CartCard(event, portions_by_event.get(event.id, [])) for event in events]

    return Div(
        H1("Food cart", cls="text-xl font-bold"),
        *event_cards,
        Script(src="/js/cart_units.js", defer="defer"),
        data_hide_cart="true",
        cls="""
            flex flex-col items-center
            gap-6
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-xs
            w-full mx-auto
            md:mb-28 lg:mb-28 mb-24
            transition-[width,margin,padding] duration-150
        """
    )
