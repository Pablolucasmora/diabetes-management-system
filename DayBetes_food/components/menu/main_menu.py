from fasthtml.common import *
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.auth.service import get_user_by_id
from DayBetes_food.components.menu.layout import IslandLogo
from DayBetes_food.components.menu.sections import quick_actions
from DayBetes_food.database.queries import list_planned_intake_events, list_portions_by_event


def _greeting(user):
    return H1(
        f"Hi {user.username}" if user else "Hi",
        cls="w-xs md:w-md px-1 text-2xl font-bold text-gray-900 truncate",
    )


def main_menu(conexion):
    user_id = get_current_user_id()
    user = get_user_by_id(conexion, int(user_id)) if user_id else None
    events = list_planned_intake_events(conexion, int(user_id)) if user_id else []
    latest_event = events[0] if events else None
    portions = list_portions_by_event(conexion, int(user_id), latest_event.id) if latest_event and user_id else []

    return Header(IslandLogo()
                  ,cls="""
                  flex items-center justify-center
                  """), Div(
                      _greeting(user),
                      quick_actions(latest_event, portions),
                      cls="""
                      md:mt-36 lg:mt-36 mt-28 pb-40
                      flex flex-col items-center justify-center
                      gap-4
                      """)
