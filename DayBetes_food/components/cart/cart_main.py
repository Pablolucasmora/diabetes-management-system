from fasthtml.common import *
from DayBetes_food.database.queries.crud import get_cart_events, get_all_users


def CartCard(event):
    """Card for planned event"""
    return Div(
        H3(f"Event #{event['id']}", cls="font-bold"),
        P(f"State: {event['state']}"),
        P(f"Time: {event['meal_time']}"),
        cls="border p-2 rounded mb-2 bg-white"
    )


def cart_main(connection):
    users = get_all_users(connection)
    if not users:
        return Div(H2("No users"), cls="flex flex-col items-center")
    
    user_id = users[0]["id"]
    events = get_cart_events(connection, user_id)
    
    if not events:
        return Div(
            H1("Empty cart", cls="text-gray-500"),
            P("Add foods from Food"),
            cls="""
                flex flex-col items-center 
                justify-center gap-6 
                md:mt-7 lg:mt-7 mt-2
            """
        )
    
    return Div(
        H1("Food cart", cls="text-xl font-bold mb-4"),
        *[CartCard(event) for event in events],
        cls="""
            flex flex-col items-center 
            justify-center gap-6 
            md:mt-7 lg:mt-7 mt-2
        """
    )
