from fasthtml.common import *
from DayBetes_food.components.cart.cart_shared import (
    calculate_macro_summary_metrics,
    macro_color,
    parse_source_macro,
    portion_intake_amount,
    portion_macro_amount,
)
from DayBetes_food.components.injection_zone import (
    BASE_INJECTION_ZONE_IMAGE,
    INJECTION_ZONE_IMAGE_BY_ZONE,
    injection_zone_label,
    asset_busted,
)
from DayBetes_food.components.modal import (
    close_modal_js,
    modal_confirm_button,
    ModalLayer,
    open_modal_js,
)
from DayBetes_food.domain.constants import InjectionZone
from DayBetes_food.time_utils import local_now, to_local

def _meal_totals(portions) -> dict:
    """Totals of the meal as the cart shows them (live, measurement §6.9)."""
    totals = {"amount": sum(portion_intake_amount(p) for p in portions)}
    for key in ("carbs", "calories", "fats", "proteins", "fiber"):
        total = 0.0
        for portion in portions:
            value = parse_source_macro(portion, key)
            if value is not None:
                total += portion_macro_amount(portion) * float(value) / 100.0
        totals[key] = total
    return totals


def _current_meal_card(latest_event, portions):
    """What the user is eating now: the planned meal and its carbs, the number
    the insulin dose depends on. Tapping it opens the cart."""
    if not latest_event:
        return Div(
            P("Current meal", cls="web_section_label"),
            P("No meal in progress", cls="text-base font-semibold"),
            P("Add a food and a new meal starts.", cls="text-sm text-gray-600"),
            cls="web_container w-full p-5 flex flex-col gap-1",
        )

    totals = _meal_totals(portions)
    metrics = calculate_macro_summary_metrics(portions)
    amount_confidence = (
        latest_event.amount_confidence
        if latest_event.amount_confidence is not None
        else metrics["amount_confidence"]
    )
    reliability = macro_color(
        metrics["carbs_uncertainty"], amount_confidence, metrics["quality_confidence"]
    )
    meal_time = to_local(latest_event.meal_time)
    subtitle = " · ".join(
        part
        for part in (
            latest_event.meal_type.value.replace("_", " ").capitalize() if latest_event.meal_type else None,
            meal_time.strftime("%H:%M") if meal_time else None,
            f"{len(portions)} ingredient{'s' if len(portions) != 1 else ''}",
        )
        if part
    )
    secondary = (
        ("Fats", totals["fats"]),
        ("Proteins", totals["proteins"]),
        ("Fiber", totals["fiber"]),
    )
    return Div(
        Div(
            P("Current meal", cls="web_section_label"),
            Span("Open cart ›", cls="text-xs font-semibold text-gray-700"),
            cls="flex items-center justify-between",
        ),
        H2(latest_event.name or f"Meal #{latest_event.id}", cls="text-lg font-semibold truncate"),
        P(subtitle, cls="text-xs text-gray-600 -mt-1"),
        Div(
            Span(f"{totals['carbs']:.0f}", cls="text-4xl font-bold tabular-nums"),
            Span("g carbs", cls="text-sm font-medium text-gray-700"),
            Span(
                cls="ml-auto h-3 w-3 rounded-full self-center",
                style=f"background-color: {reliability};",
                title="Data reliability (green = reliable, red = uncertain)",
            ),
            cls="flex items-baseline gap-2 mt-2",
        ),
        P(
            f"{totals['amount']:.0f} g served · {totals['calories']:.0f} kcal",
            cls="text-xs text-gray-600",
        ),
        Div(
            *[
                Div(
                    P(label, cls="text-[11px] text-gray-600"),
                    P(f"{value:.1f} g", cls="text-sm font-semibold tabular-nums"),
                    cls="flex flex-col",
                )
                for label, value in secondary
            ],
            cls="grid grid-cols-3 gap-2 mt-2 pt-3 border-t border-white",
        ),
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
        cls="web_container w-full p-5 flex flex-col gap-1 cursor-pointer",
    )


def _section_title(text: str):
    return P(text, cls="web_section_label px-1")


def quick_actions(latest_event, portions):
    now = local_now()
    modal_id = "menu_injection_modal"
    open_js = open_modal_js(modal_id)
    close_js = close_modal_js(modal_id)
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
            injection_zone_label(zone),
            type="button",
            cls="web_button px-3 py-2 text-xs",
            **{
                "data-zone": zone.value,
                "data-zone-img": asset_busted(INJECTION_ZONE_IMAGE_BY_ZONE[zone]),
                "onclick": selector_js,
            },
        )
        for zone in InjectionZone
    ]

    create_button_cls = "web_button w-full py-3 text-sm font-medium flex flex-col items-center gap-1"
    quick_grid = Div(
        _current_meal_card(latest_event, portions),
        Div(
            _section_title("Add to your meal"),
            Div(
                Button(
                    "What did you eat?",
                    type="button",
                    cls="web_button bg-white flex-1 text-left text-sm text-gray-500 px-4 py-3",
                    hx_get="/food",
                    hx_target="#main_content",
                    hx_push_url="true",
                ),
                Button(
                    Img(src="/images/ui/bar_code.svg", alt="Scan a barcode", cls="w-7 h-7"),
                    type="button",
                    cls="web_button px-3 py-2 flex items-center justify-center",
                    hx_get="/scanner",
                    hx_target="#main_content",
                    hx_push_url="true",
                ),
                cls="flex gap-3",
            ),
            Div(
                Button(
                    Span("Quick add"),
                    Span("only carbs", cls="text-[11px] text-gray-500 font-normal"),
                    type="button",
                    cls=create_button_cls,
                    hx_get="/food/quick_add/form",
                    hx_target="#main_content",
                    hx_push_url="true",
                    **{"hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });"},
                ),
                Button(
                    Span("New food"),
                    Span("packaged", cls="text-[11px] text-gray-500 font-normal"),
                    type="button",
                    cls=create_button_cls,
                    hx_get="/food/create/catalog/form",
                    hx_target="#main_content",
                    hx_push_url="true",
                ),
                Button(
                    Span("New dish"),
                    Span("homemade / out", cls="text-[11px] text-gray-500 font-normal"),
                    type="button",
                    cls=create_button_cls,
                    hx_get="/food/create/manual_intake/form",
                    hx_target="#main_content",
                    hx_push_url="true",
                ),
                cls="grid grid-cols-3 gap-3",
            ),
            cls="web_container w-full p-4 flex flex-col gap-3",
        ),
        Div(
            _section_title("Insulin"),
            Button(
                "Log injection",
                type="button",
                cls="web_button web_button_primary w-full py-3 text-sm",
                onclick=open_js,
            ),
            cls="web_container w-full p-4 flex flex-col gap-3",
        ),
        cls="w-xs md:w-md flex flex-col gap-5",
    )

    injection_modal = ModalLayer(
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
                    name="units",
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
                    modal_confirm_button(
                        "OK",
                        cls="ml-auto",
                        hx_post="/menu/injection_log",
                        hx_include="closest form",
                        hx_target="#main_content",
                    hx_swap="innerHTML",
                    onclick=(
                        "const form=this.form;"
                        "const z=form?form.querySelector('[data-menu-injection-zone-input]'):null;"
                        "if(!z||!z.value){alert('Select a zone first.');return false;}"
                        "const t=form?form.querySelector('[data-menu-insulin-type]'):null;"
                        "const b=form?form.querySelector('input[name=units]'):null;"
                        "if(t&&t.value==='basal'&&(!b||!b.value)){alert('Enter basal dose.');return false;}"
                        + close_js
                    ),
                ),
            ),
            cls="flex flex-col gap-3",
        ),
        modal_id=modal_id,
        card_cls="gap-3",
    )

    actions = Div(
        quick_grid,
        injection_modal,
        cls="relative"
    )

    return actions
