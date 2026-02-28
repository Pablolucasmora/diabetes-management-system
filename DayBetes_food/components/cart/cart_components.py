from datetime import datetime
from fasthtml.common import *

from DayBetes_food.components.cart.cart_shared import (
    CHECKBOX_CLS,
    MACRO_KEYS,
    MEAL_TYPES,
    display_unit,
    group_portions,
    macro_color,
    parse_source_macro,
    portion_name,
    unit_amount,
)


def _check_icon():
    return Span(
        Svg(
            Path(
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z",
                fill_rule="evenodd",
                clip_rule="evenodd",
            ),
            xmlns="http://www.w3.org/2000/svg",
            cls="h-3.5 w-3.5",
            viewBox="0 0 20 20",
            fill="currentColor",
            stroke="currentColor",
            stroke_width="1",
        ),
        cls="""
            absolute text-white opacity-0 peer-checked:opacity-100
            top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2
            pointer-events-none
        """,
    )


def _checkbox(name: str, checked: bool, hx_post: str):
    return Label(
        Input(
            type="checkbox",
            name=name,
            value="true",
            checked=checked,
            cls=CHECKBOX_CLS,
            hx_post=hx_post,
            hx_trigger="change",
            hx_swap="none",
        ),
        _check_icon(),
        cls="flex items-center cursor-pointer relative h-5 w-5",
    )


def EventHeader(event):
    meal_time = event.get("meal_time") or datetime.now()
    return Div(
        Div(
            H2(event.get("name") or f"Intake event #{event['id']}", cls="font-bold text-lg"),
            Form(
                Label("Meal hour", cls="text-xs text-gray-600"),
                Div(
                    Input(
                        type="time",
                        value=meal_time.strftime("%H:%M"),
                        name="meal_hour",
                        cls="web_input border border-white rounded-lg px-2 py-1 text-sm",
                        hx_post=f"/cart/event/{event['id']}/meal_hour",
                        hx_trigger="change",
                        hx_include="closest form",
                        hx_swap="none",
                    ),
                    Button(
                        "Date",
                        type="button",
                        cls="web_button px-2 py-1 text-xs",
                        onclick=(
                            f"const el=document.getElementById('meal_date_wrap_{event['id']}');"
                            "el.classList.toggle('hidden');"
                        ),
                    ),
                    cls="flex items-center justify-end gap-2 w-full"
                ),
                Div(
                    Label("Meal date", cls="text-xs text-gray-600"),
                    Input(
                        type="date",
                        value=meal_time.strftime("%Y-%m-%d"),
                        name="meal_date",
                        cls="web_input border border-white rounded-lg px-2 py-1 text-sm",
                        hx_post=f"/cart/event/{event['id']}/meal_hour",
                        hx_trigger="change",
                        hx_include="closest form",
                        hx_swap="none",
                    ),
                    id=f"meal_date_wrap_{event['id']}",
                    cls="hidden flex-col gap-1 w-full items-end"
                ),
                cls="flex flex-col gap-2 w-full items-end ml-auto",
            ),
            cls="flex items-start justify-between gap-3 w-full"
        ),
        Form(
            Label("Meal type", cls="text-xs text-gray-600"),
            Select(
                *[Option(m, value=m, selected=(event.get("meal_type") == m)) for m in MEAL_TYPES],
                name="meal_type",
                cls="web_input border border-white rounded-lg px-2 py-1 text-sm",
                hx_post=f"/cart/event/{event['id']}/meal_type",
                hx_trigger="change",
                hx_swap="none",
            ),
            cls="flex flex-col gap-1"
        ),
        cls="flex flex-col gap-3"
    )


def MacrosSummary(event, portions):
    total_amount = sum(float(p.get("amount_g") or 0.0) for p in portions)
    pills = []
    for macro_key, label, uncertainty_key in MACRO_KEYS:
        total = 0.0
        unknown_amount = 0.0
        for portion in portions:
            amount = float(portion.get("amount_g") or 0.0)
            macro_100 = parse_source_macro(portion, macro_key)
            if macro_100 is None:
                unknown_amount += amount
                continue
            total += amount * float(macro_100) / 100.0

        inferred_uncertainty = (unknown_amount / total_amount) if total_amount > 0 else 0.0
        uncertainty = event.get(uncertainty_key)
        if uncertainty is None:
            uncertainty = inferred_uncertainty

        pills.append(
            Div(
                Div(
                    Span(label, cls="font-semibold"),
                    Button(
                        "?",
                        type="button",
                        title=f"Uncertainty: {inferred_uncertainty * 100:.1f}%",
                        onclick=f"alert('Uncertainty: {inferred_uncertainty * 100:.1f}%');",
                        cls="""
                            web_button rounded-full
                            h-4 w-4 md:h-5 md:w-5
                            text-[10px] md:text-xs
                            p-0 leading-none
                            flex items-center justify-center
                            shadow-none
                        """,
                    ),
                    cls="flex items-center gap-1"
                ),
                Span(f"{total:.1f} g"),
                style=f"background-color: {macro_color(uncertainty)}; color: white;",
                title=(
                    f"Unknown {label.lower()} in "
                    f"{inferred_uncertainty * 100:.1f}% of ingredient amount"
                ),
                cls="""
                    rounded-md px-2 py-1 text-xs
                    md:rounded-lg md:px-3 md:py-2 md:text-sm
                    flex justify-between gap-2
                """
            )
        )

    return Div(
        Div(
            H3("Meal macros", cls="font-semibold"),
            Span(f"Total: {total_amount:.1f} g", cls="text-xs md:text-sm text-gray-700"),
            cls="flex items-center justify-between gap-2"
        ),
        Div(*pills, cls="grid grid-cols-2 md:grid-cols-2 lg:grid-cols-2 gap-1 md:gap-2"),
        cls="flex flex-col gap-2"
    )


def IngredientRow(event, grouped_item):
    sample = grouped_item["sample"]
    origin = grouped_item["origin"]
    origin_id = grouped_item["origin_id"]
    unit_g = unit_amount(sample)
    unit_label = display_unit(sample)
    amount = float(grouped_item["total_amount_g"] or unit_g)
    offset = sample.get("offset_minutes")
    offset_value = int(offset) if offset is not None else 0
    units_count = amount / unit_g if unit_g > 0 else 0.0

    return Div(
        Div(
            Div(portion_name(sample), cls="font-semibold"),
            Div(f"{units_count:.2f} units", cls="text-xs text-gray-600"),
            cls="flex items-center justify-between gap-2"
        ),
        Form(
            Input(type="hidden", name="unit_g", value=f"{unit_g:.4f}"),
            Div(
                Button(
                    "-",
                    type="button",
                    cls="web_button px-3 py-1",
                    hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/decrement",
                    hx_include="closest form",
                    hx_swap="none",
                ),
                Input(
                    type="number",
                    step="0.1",
                    min="0",
                    inputmode="decimal",
                    name="amount_g",
                    value=f"{amount:.1f}",
                    cls="web_input border border-white rounded-lg px-2 py-1 w-24 text-base",
                    hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/amount",
                    hx_trigger="change",
                    hx_swap="none",
                    onclick="this.select()",
                ),
                Span(unit_label, cls="text-xs text-gray-600"),
                Button(
                    "+",
                    type="button",
                    cls="web_button px-3 py-1",
                    hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/increment",
                    hx_include="closest form",
                    hx_swap="none",
                ),
                cls="flex items-center gap-2"
            ),
            cls="flex flex-col gap-2"
        ),
        Div(
            Label("Offset (min)", cls="text-xs text-gray-600"),
            Input(
                type="number",
                step="1",
                name="offset_minutes",
                inputmode="integer",
                value=str(offset_value),
                cls="web_input border border-white rounded-lg px-2 py-1 w-24 text-sm",
                hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/offset",
                hx_trigger="change",
                onclick= "this.select()",
                hx_swap="none",
            ),
            cls="flex items-center gap-2"
        ),
        Div(
            Label("Strictly weighted", cls="text-xs text-gray-600"),
            _checkbox(
                name="strictly_weighed",
                checked=bool(sample.get("strictly_weighed")),
                hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/strictly_weighed",
            ),
            cls="flex items-center gap-2"
        ),
        Div(
            Label("Macros quality", cls="text-xs text-gray-600"),
            _checkbox(
                name="macros_quality",
                checked=bool(sample.get("macros_quality")),
                hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/macros_quality",
            ),
            cls="flex items-center gap-2"
        ),
        Div(
            Label("Cooked weight", cls="text-xs text-gray-600"),
            _checkbox(
                name="is_cooked_weight",
                checked=bool(sample.get("is_cooked_weight")),
                hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/is_cooked_weight",
            ),
            cls="flex items-center gap-2"
        ),
        cls="web_container p-3 rounded-2xl flex flex-col gap-3"
    )


def ConfirmSection(event, portions):
    total_amount = sum(float(p.get("amount_g") or 0.0) for p in portions)
    return Form(
        Input(type="hidden", name="total_amount", value=f"{total_amount:.4f}"),
        Input(type="hidden", name="ingested_unit", value="g", id=f"ingested_unit_{event['id']}"),
        Input(
            type="number",
            step="0.1",
            min="0",
            name="ingested_value",
            value=f"{float(event.get('ingested_amount') or 0.0):.1f}" if event.get("ingested_amount") is not None else "",
            placeholder="Ingested amount",
            cls="""
                web_input border border-white rounded-lg
                px-2 py-1 w-24 text-xs
                md:px-3 md:py-2 md:w-36 md:text-sm
            """
        ),
        Button(
            "g",
            type="button",
            onclick=(
                f"const hidden=document.getElementById('ingested_unit_{event['id']}');"
                "hidden.value = hidden.value === 'g' ? '%' : 'g';"
                "this.innerText = hidden.value;"
            ),
            cls="""
                web_button px-2 py-1 text-xs min-w-10
                md:px-2 md:py-2 md:text-sm md:min-w-12
            """
        ),
        Button(
            "Confirm food",
            type="button",
            cls="""
                web_button px-2 py-1 text-xs
                md:px-4 md:py-2 md:text-sm
            """,
            hx_post=f"/cart/event/{event['id']}/confirm",
            hx_include="closest form",
            hx_swap="none",
        ),
        cls="flex items-center gap-1 md:gap-2 justify-end"
    )


def CartCard(event, portions):
    grouped_portions = group_portions(portions)
    return Div(
        EventHeader(event),
        Div(
            Label("Eating out", cls="text-xs text-gray-600"),
            _checkbox(
                name="eating_out",
                checked=bool(event.get("eating_out")),
                hx_post=f"/cart/event/{event['id']}/eating_out",
            ),
            cls="flex items-center gap-2"
        ),
        MacrosSummary(event, portions),
        Div(
            H3("Ingredients", cls="font-semibold"),
            *[IngredientRow(event, item) for item in grouped_portions],
            cls="flex flex-col gap-3"
        ),
        ConfirmSection(event, portions),
        cls="""
            web_container p-4 rounded-3xl
            md:w-md lg:w-md w-xs
            flex flex-col gap-4
            mx-auto
            transition-[width,margin,padding] duration-150
        """
    )
