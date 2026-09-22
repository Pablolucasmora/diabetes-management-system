from fasthtml.common import *
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.menu.layout import IslandLogo
from DayBetes_food.components.menu.sections import quick_actions
from DayBetes_food.database.queries import list_planned_intake_events, list_portions_by_event


def main_menu(conexion):
    user_id = get_current_user_id()
    events = list_planned_intake_events(conexion, int(user_id)) if user_id else []
    latest_event = events[0] if events else None
    portions = list_portions_by_event(conexion, int(user_id), latest_event.id) if latest_event and user_id else []

    return Header(IslandLogo()
                  ,cls="""
                  flex items-center justify-center
                  """), Div(
                      quick_actions(latest_event, portions),
                      cls="""
                      md:mt-40 lg:mt-40 mt-36
                      flex flex-col items-center justify-center
                      gap-6
                      """)



