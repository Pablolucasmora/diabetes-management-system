from fasthtml.common import *

def quick_actions():
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
            h-auto
            grid grid-cols-2 gap-6
        """
    )

    return actions
