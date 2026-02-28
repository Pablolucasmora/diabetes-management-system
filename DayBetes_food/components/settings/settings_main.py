from fasthtml.common import *


def settings_main(connection):
    return Div(
        Div(
            H1("Settings", cls="text-xl font-bold text-center"),
            P(
                "Configure profile, targets, and app preferences.",
                cls="text-sm text-gray-600 text-center",
            ),
            cls="web_container p-6 flex flex-col items-center gap-2",
        ),
        cls="flex flex-col items-center justify-center gap-6 md:mt-7 lg:mt-7 mt-2",
    )
