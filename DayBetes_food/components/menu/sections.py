from fasthtml.common import *
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.cart.cart_components import MacrosSummary
from DayBetes_food.database.queries.crud import (
    get_cart_events,
    get_portion_detail_by_event,
)

def _menu_cart_summary(connection):
    user_id = get_current_user_id()
    if not user_id:
        return P("No hay carrito", cls="text-xs md:text-sm text-gray-600 text-center")

    events = get_cart_events(connection, user_id)
    if not events:
        return P("No hay carrito", cls="text-xs md:text-sm text-gray-600 text-center")

    latest = events[0]
    portions = get_portion_detail_by_event(connection, int(latest["id"]))
    meal_name = latest.get("name") or f"Meal #{latest['id']}"

    return Div(
        P("Último carrito", cls="text-[11px] md:text-xs uppercase tracking-wide text-gray-600"),
        H2(meal_name, cls="font-semibold text-sm md:text-base truncate w-full"),
        Div(MacrosSummary(latest, portions, compact=True), cls="w-full"),
        cls="w-full flex flex-col gap-2"
    )


def quick_actions(connection):
    actions = Div(
        Div(
            Button(
                "Add catalog",
                cls="web_button w-full text-xs md:text-sm px-2 py-1.5 md:px-3 md:py-2",
                hx_get="/food/create/catalog/form",
                hx_target="#main_content",
                hx_push_url="true",
            ),
            Button(
                "Add manual",
                cls="web_button w-full text-xs md:text-sm px-2 py-1.5 md:px-3 md:py-2",
                hx_get="/food/create/manual/form",
                hx_target="#main_content",
                hx_push_url="true",
            ),
            Button(
                Img(src="/images/ui/bar_code.svg", alt="Scanner", cls="w-10 h-10 md:w-12 md:h-12"),
                cls="web_button w-full flex items-center justify-center p-0.5 md:p-1",
                hx_get="/scanner",
                hx_target="#main_content",
                hx_push_url="true",
            ),
            Button(
                "...",
                cls="web_button w-full text-xs md:text-sm px-2 py-1.5 md:px-3 md:py-2",
                hx_get="/food",
                hx_target="#main_content",
                hx_push_url="true",
            ),
            cls="""
            web_container
            grid grid-cols-2 grid-rows-2 md:p-4 lg:p-4 p-3
            md:gap-y-4 lg:gap-y-4 gap-y-4
            md:gap-x-4 lg:gap-x-4 gap-x-3
            """
        ),
        Div(
            _menu_cart_summary(connection),
            role="button",
            tabindex="0",
            hx_get="/cart",
            hx_target="#main_content",
            hx_push_url="true",
            **{
                "hx-on:keydown": (
                    "if(event.key==='Enter' || event.key===' '){"
                    "event.preventDefault();"
                    "this.click();"
                    "}"
                )
            },
            cls="""
            web_container
            md:p-4 lg:p-4 p-3
            flex flex-col items-start justify-start
            md:gap-3 lg:gap-3 gap-2
            cursor-pointer
            """
        ),
        cls="""
            transition-all
            md:w-md lg:w-md
            w-xs
            md:h-40
            h-auto
            grid grid-cols-2 gap-6
        """
    )

    return actions
