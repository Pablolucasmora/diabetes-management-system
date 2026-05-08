from fasthtml.common import *
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.cart.cart_components import MacrosSummary
from DayBetes_food.components.injection_zone import (
    BASE_INJECTION_ZONE_IMAGE,
    INJECTION_ZONE_IMAGE_BY_KEY,
    INJECTION_ZONE_LABEL_BY_KEY,
    asset_busted,
)
from DayBetes_food.database.queries.crud import (
    get_cart_events,
    get_portion_detail_by_event,
)
from DayBetes_food.time_utils import local_now

def _menu_cart_summary(connection):
    user_id = get_current_user_id()
    if not user_id:
        return P("No hay carrito", cls="text-xs md:text-sm text-gray-600 text-center")

    events = get_cart_events(connection, user_id)
    if not events:
        return P("No hay carrito", cls="text-xs md:text-sm text-gray-600 text-center")

    latest = events[0]
    portions = get_portion_detail_by_event(connection, int(latest["id"]))
    meal_name = latest.get("name") or f"Meal #{latest['id']}"

    return Div(
        P("Último carrito", cls="text-[11px] md:text-xs uppercase tracking-wide text-gray-600"),
        H2(meal_name, cls="font-semibold text-sm md:text-base truncate w-full"),
        Div(MacrosSummary(latest, portions, compact=True), cls="w-full"),
        cls="w-full flex flex-col gap-2"
    )


def quick_actions(connection):
    now = local_now()
    modal_id = "menu_injection_modal"
    open_modal_js = (
        f"const m=document.getElementById('{modal_id}');"
        "if(!m) return;"
        "m.classList.remove('invisible','opacity-0','pointer-events-none');"
        "m.classList.add('opacity-100');"
    )
    close_modal_js = (
        f"const m=document.getElementById('{modal_id}');"
        "if(!m) return;"
        "m.classList.remove('opacity-100');"
        "m.classList.add('opacity-0','invisible','pointer-events-none');"
    )
    selector_js = (
        f"const box=document.getElementById('{modal_id}');"
        "if(!box) return;"
        "const zone=this.getAttribute('data-zone')||'';"
        "const img=box.querySelector('[data-menu-injection-image]');"
        "const hidden=box.querySelector('[data-menu-injection-zone-input]');"
        "if(hidden){hidden.value=zone;}"
        "if(img){img.src=this.getAttribute('data-zone-img')||img.src;}"
        "box.querySelectorAll('[data-zone]').forEach(function(el){"
        "el.classList.remove('ring-2','ring-cyan-500','bg-cyan-50');"
        "});"
        "this.classList.add('ring-2','ring-cyan-500','bg-cyan-50');"
    )
    switch_insulin_js = (
        f"const box=document.getElementById('{modal_id}');"
        "if(!box) return;"
        "const sel=box.querySelector('[data-menu-insulin-type]');"
        "const basal=box.querySelector('[data-menu-basal-wrap]');"
        "if(!sel||!basal) return;"
        "if(sel.value==='basal'){basal.classList.remove('hidden');}"
        "else{basal.classList.add('hidden');}"
    )
    zone_buttons = [
        Button(
            INJECTION_ZONE_LABEL_BY_KEY[zone_key],
            type="button",
            cls="web_button px-3 py-2 text-xs",
            **{
                "data-zone": zone_key,
                "data-zone-img": asset_busted(INJECTION_ZONE_IMAGE_BY_KEY[zone_key]),
                "onclick": selector_js,
            },
        )
        for zone_key in INJECTION_ZONE_IMAGE_BY_KEY.keys()
    ]

    quick_grid = Div(
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
            Button(
                "Injection",
                cls="web_button w-full text-xs md:text-sm px-2 py-1.5 md:px-3 md:py-2",
                onclick=open_modal_js,
            ),
            cls="""
            web_container
            grid grid-cols-2 md:p-4 lg:p-4 p-3
            md:gap-y-4 lg:gap-y-4 gap-y-4
            md:gap-x-4 lg:gap-x-4 gap-x-3
            """
        ),
        Div(
            _menu_cart_summary(connection),
            role="button",
            tabindex="0",
            hx_get="/cart",
            hx_target="#main_content",
            hx_push_url="true",
            **{
                "hx-on:keydown": (
                    "if(event.key==='Enter' || event.key===' '){"
                    "event.preventDefault();"
                    "this.click();"
                    "}"
                )
            },
            cls="""
            web_container
            md:p-4 lg:p-4 p-3
            flex flex-col items-start justify-start
            md:gap-3 lg:gap-3 gap-2
            cursor-pointer
            """
        ),
        cls="""
            transition-all
            md:w-md lg:w-md
            w-xs
            md:h-auto
            h-auto
            grid grid-cols-2 gap-6
        """
    )

    injection_modal = Div(
        Div(
            P("Insulin injection", cls="text-lg font-semibold"),
            Form(
                Div(
                    Div(
                        Label("Type", cls="text-xs text-gray-600"),
                        Select(
                            Option("Rapid", value="rapid", selected=True),
                            Option("Basal", value="basal"),
                            name="insulin_type",
                            cls="web_input border border-white rounded-lg px-2 py-1 text-base",
                            data_menu_insulin_type="true",
                            onchange=switch_insulin_js,
                        ),
                        cls="flex flex-col gap-1 flex-1 min-w-0",
                    ),
                    Div(
                        Label("Injection hour", cls="text-xs text-gray-600"),
                        Div(
                            Input(
                                type="time",
                                name="shot_hour",
                                value=now.strftime("%H:%M"),
                                aria_label="Injection hour",
                                cls="web_input border border-white rounded-lg px-2 py-1 text-base",
                            ),
                            Button(
                                "Date",
                                type="button",
                                cls="web_button px-2 py-1 text-xs",
                                onclick=(
                                    f"const el=document.getElementById('menu_shot_date_wrap');"
                                    "if(el){el.classList.toggle('hidden');}"
                                ),
                            ),
                            cls="flex items-center gap-2",
                        ),
                        Div(
                            Label("Injection date", cls="text-xs text-gray-600"),
                            Input(
                                type="date",
                                name="shot_date",
                                value=now.strftime("%Y-%m-%d"),
                                aria_label="Injection date",
                                cls="web_input border border-white rounded-lg px-2 py-1 text-base",
                            ),
                            id="menu_shot_date_wrap",
                            cls="hidden flex-col gap-1 mt-1",
                        ),
                        cls="flex flex-col gap-1 flex-1 min-w-0",
                    ),
                    cls="grid grid-cols-2 gap-3",
                ),
                Div(
                    Label("Basal dose", cls="text-xs text-gray-600"),
                    Input(
                        type="number",
                        name="basal_units",
                        step="0.5",
                        min="0.5",
                        inputmode="decimal",
                        pattern="[0-9]+([\\.,][0-9]+)?",
                        placeholder="e.g. 8.5",
                        cls="web_input border border-white rounded-lg px-2 py-1 text-base",
                    ),
                    data_menu_basal_wrap="true",
                    cls="hidden flex-col gap-1",
                ),
                Div(
                    Img(
                        src=asset_busted(BASE_INJECTION_ZONE_IMAGE),
                        alt="Injection zones map",
                        cls="w-full max-h-[38vh] md:max-h-[46vh] object-contain rounded-2xl border border-gray-200 bg-white",
                        data_menu_injection_image="true",
                    ),
                    cls="w-full",
                ),
                Div(*zone_buttons, cls="flex flex-wrap gap-2"),
                Input(type="hidden", name="zone", value="", data_menu_injection_zone_input="true"),
                    Div(
                        Button(
                            "OK",
                            type="button",
                            cls="web_button px-4 py-2 text-sm text-white ml-auto",
                            style="background-color:#111111;border-color:#111111;",
                            hx_post="/menu/injection_log",
                            hx_include="closest form",
                            hx_target="#main_content",
                        hx_swap="innerHTML",
                        onclick=(
                            "const form=this.form;"
                            "const z=form?form.querySelector('[data-menu-injection-zone-input]'):null;"
                            "if(!z||!z.value){alert('Select a zone first.');return false;}"
                            "const t=form?form.querySelector('[data-menu-insulin-type]'):null;"
                            "const b=form?form.querySelector('input[name=basal_units]'):null;"
                            "if(t&&t.value==='basal'&&(!b||!b.value)){alert('Enter basal dose.');return false;}"
                            + close_modal_js
                        ),
                    ),
                ),
                cls="flex flex-col gap-3",
            ),
            onclick="event.stopPropagation()",
            cls="web_container p-4 md:p-5 rounded-3xl w-72 md:w-[88vw] max-w-md flex flex-col gap-3",
        ),
        id=modal_id,
        onclick=close_modal_js,
        cls="""
            fixed inset-0 z-[70]
            flex items-center justify-center
            bg-slate-800/30 backdrop-blur-lg
            px-4
            opacity-0 invisible pointer-events-none
            transition-opacity duration-200
        """,
    )

    actions = Div(
        quick_grid,
        injection_modal,
        cls="relative"
    )

    return actions
