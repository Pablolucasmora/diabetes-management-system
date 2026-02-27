from fasthtml.common import *

def quick_actions():
    actions = Div(
        Div(
            Button("Search", cls="web_button"),
            Button("Food", cls="web_button"),
            Button("Log", cls="web_button"),
            cls="""
            web_container
            grid grid-cols-2 grid-rows-2 md:p-4 lg:p-4 p-3
            md:gap-y-3 lg:gap-y-3 gap-y-3
            md:gap-x-2 lg:gap-x-2 gap-x-1
            """
        ),
        Div(
            H1("Cart", cls="font-bold text-center"),
            cls="""
            web_container
            grid grid-cols-2 grid-rows-2 md:p-4 lg:p-4 p-3
            md:gap-y-3 lg:gap-y-3 gap-y-3
            md:gap-x-2 lg:gap-x-2 gap-x-1
            """
        ),
        cls="""
            transition-all
            md:w-md lg:w-md
            w-xs
            md:h-40
            h-32
            grid grid-cols-2 gap-6
        """
    )

    return actions