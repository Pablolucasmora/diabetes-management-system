from fasthtml.common import *

from DayBetes_food.components.cart.cart_components import CartCard
from DayBetes_food.database.queries.crud import (
    get_cart_events,
    get_default_user_id,
    get_portion_detail_by_events,
)


def cart_main(connection):
    user_id = get_default_user_id(connection)
    if not user_id:
        return Div(H2("No users"), cls="flex flex-col items-center")

    events = get_cart_events(connection, user_id)
    if not events:
        return Div(
            H1("Empty cart", cls="text-gray-500"),
            P("Add foods from Food"),
            cls="""
                flex flex-col items-center
                justify-center gap-6
                md:mt-7 lg:mt-7 mt-2
                transition-[width,margin,padding] duration-150
            """
        )

    event_ids = [event["id"] for event in events]
    all_portions = get_portion_detail_by_events(connection, event_ids)
    portions_by_event = {event_id: [] for event_id in event_ids}
    for portion in all_portions:
        portions_by_event.setdefault(portion["intake_event_id"], []).append(portion)

    event_cards = [CartCard(event, portions_by_event.get(event["id"], [])) for event in events]

    return Div(
        H1("Food cart", cls="text-xl font-bold"),
        *event_cards,
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
