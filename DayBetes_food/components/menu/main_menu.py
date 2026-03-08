from fasthtml.common import *
from DayBetes_food.components.menu.layout import IslandLogo
from DayBetes_food.components.menu.sections import quick_actions


def main_menu(conexion):
    return Header(IslandLogo()
                  ,cls="""
                  flex items-center justify-center
                  """), Div(
                      quick_actions(conexion),
                      cls="""
                      md:mt-40 lg:mt-40 mt-36
                      flex flex-col items-center justify-center
                      gap-6
                      """)



