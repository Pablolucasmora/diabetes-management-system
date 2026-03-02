from fasthtml.common import *


def settings_main(connection):
    return Div(
        Div(
            H1("Settings", cls="text-xl font-bold text-center"),
            P(
                "Configure profile, targets, and app preferences.",
                cls="text-sm text-gray-600 text-center",
            ),
            Form(
                Input(type="hidden", name="csrf_token", value=""),
                Button(
                    "Cerrar sesion",
                    type="submit",
                    cls="web_button px-4 py-2 text-sm text-white",
                    style="background-color:#b91c1c;border-color:#b91c1c;",
                ),
                action="/auth/logout",
                method="post",
                cls="mt-3",
                onsubmit=(
                    "var m=document.cookie.match(/(?:^|; )daybetes_csrf=([^;]+)/);"
                    "if(m){this.querySelector(\"input[name='csrf_token']\").value=decodeURIComponent(m[1]);}"
                ),
            ),
            cls="web_container p-6 flex flex-col items-center gap-2",
        ),
        cls="flex flex-col items-center justify-center gap-6 md:mt-7 lg:mt-7 mt-2",
    )
