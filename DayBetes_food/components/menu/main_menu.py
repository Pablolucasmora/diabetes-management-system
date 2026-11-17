from fasthtml.common import *
from DayBetes_food.config import ASSISTANT_ENABLED
from DayBetes_food.components.menu.layout import IslandLogo
from DayBetes_food.components.menu.sections import quick_actions


def _greeting(user):
    return H1(
        f"Hi {user.username}" if user else "Hi",
        cls="w-xs md:w-md px-1 text-2xl font-bold text-gray-900 truncate",
    )


def main_menu(user, latest_event, portions, pens, brands):
    """The home page from the data the route read (code_conventions.md §1.4)."""

    return Header(IslandLogo()
                  ,cls="""
                  flex items-center justify-center
                  """), Div(
                      _greeting(user),
                      quick_actions(latest_event, portions, pens, brands, assistant_enabled=ASSISTANT_ENABLED),
                      cls="""
                      md:mt-36 lg:mt-36 mt-28 pb-40
                      flex flex-col items-center justify-center
                      gap-4
                      """)
