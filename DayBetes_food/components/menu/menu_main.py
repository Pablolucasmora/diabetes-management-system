from fasthtml.common import *
from DayBetes_food.components.menu.layout import isla_logo
from DayBetes_food.components.menu.sections import quick_actions


def menu_principal(conexion):
    return Header(isla_logo()
                  ,cls="""
                  flex items-center justify-center
                  """), Div(
                      quick_actions(),
                      cls="""
                      md:mt-40 lg:mt-40 mt-36
                      flex flex-col items-center justify-center
                      gap-6
                      """)




