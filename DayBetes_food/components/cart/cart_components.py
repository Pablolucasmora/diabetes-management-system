from datetime import datetime
from fasthtml.common import *

from DayBetes_food.components.cart.cart_shared import (
    CHECKBOX_CLS,
    MACRO_KEYS,
    MEAL_TYPES,
    display_unit,
    group_portions,
    macro_color,
    macro_text_color,
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


def _checkbox(
    name: str,
    checked: bool,
    hx_post: str,
    input_id: str = "",
    aria_label: str = "",
    hx_target: str = "",
    hx_swap: str = "",
    after_request_js: str = "",
):
    return Label(
        Input(
            type="checkbox",
            name=name,
            value="true",
            checked=checked,
            aria_label=aria_label or name.replace("_", " ").title(),
            cls=CHECKBOX_CLS,
            hx_post=hx_post,
            hx_trigger="change",
            **({"id": input_id} if input_id else {}),
            **({"hx_target": hx_target} if hx_target else {}),
            **({"hx_swap": hx_swap} if hx_swap else {}),
            **({"hx-on:htmx:after-request": after_request_js} if after_request_js else {}),
        ),
        _check_icon(),
        cls="flex items-center cursor-pointer relative h-5 w-5",
    )


def _close_modal_js(modal_id: str) -> str:
    return (
        f"const m=document.getElementById('{modal_id}');"
        "m.classList.remove('opacity-100');"
        "m.classList.add('opacity-0','invisible','pointer-events-none');"
    )


def _open_modal_js(modal_id: str) -> str:
    return (
        f"const m=document.getElementById('{modal_id}');"
        "m.classList.remove('invisible','opacity-0','pointer-events-none');"
        "m.classList.add('opacity-100');"
    )


def ConfirmActionModal(modal_id: str, title: str, question: str, yes_button):
    return Div(
        Div(
            Div(
                Div(
                    P(title, cls="text-lg font-semibold"),
                    P(question, cls="text-sm md:text-base text-gray-700"),
                    cls="flex flex-col gap-1",
                ),
                Div(
                    yes_button,
                    Button(
                        "No",
                        type="button",
                        cls="web_button px-4 py-2 text-sm",
                        onclick=_close_modal_js(modal_id),
                    ),
                    cls="flex items-center gap-2 justify-end",
                ),
                onclick="event.stopPropagation()",
                cls="web_container p-5 md:p-6 rounded-3xl w-[92vw] max-w-md flex flex-col gap-4",
            ),
            id=modal_id,
            onclick=_close_modal_js(modal_id),
            cls="""
                fixed inset-0 z-[70]
                flex items-center justify-center
                bg-black/35 backdrop-blur-xl
                px-4
                opacity-0 invisible pointer-events-none
                transition-opacity duration-200
            """,
        ),
    )


def EventHeader(event):
    meal_time = event.get("meal_time") or datetime.now()
    event_name_id = f"event_name_{event['id']}"
    meal_hour_id = f"meal_hour_{event['id']}"
    meal_date_id = f"meal_date_{event['id']}"
    meal_type_id = f"meal_type_{event['id']}"
    return Div(
        Div(
            Form(
                Label(
                    "Event name",
                    **{"for": event_name_id},
                    style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;",
                ),
                Input(
                    type="text",
                    id=event_name_id,
                    name="event_name",
                    value=event.get("name") or "",
                    placeholder=f"Intake event #{event['id']}",
                    aria_label="Event name",
                    cls="""
                        w-full font-bold text-lg text-black
                        px-0 py-0 border-0 rounded-none
                        bg-transparent shadow-none
                        focus:outline-none
                    """,
                    style="background:transparent;border-color:transparent;box-shadow:none;",
                    hx_post=f"/cart/event/{event['id']}/name",
                    hx_trigger="change",
                    onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur();}",
                    onchange="this.blur();",
                    onclick="this.select();",
                ),
                cls="w-full",
            ),
            Form(
                Div(
                    Input(
                        type="time",
                        id=meal_hour_id,
                        value=meal_time.strftime("%H:%M"),
                        name="meal_hour",
                        aria_label="Meal time",
                        cls="web_input border border-white rounded-lg px-2 py-1 text-sm",
                        hx_post=f"/cart/event/{event['id']}/meal_hour",
                        hx_trigger="blur",
                        hx_include="closest form",
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
                    Label("Meal date", cls="text-xs text-gray-600", **{"for": meal_date_id}),
                    Input(
                        type="date",
                        id=meal_date_id,
                        value=meal_time.strftime("%Y-%m-%d"),
                        name="meal_date",
                        aria_label="Meal date",
                        cls="web_input border border-white rounded-lg px-2 py-1 text-sm self-end",
                        hx_post=f"/cart/event/{event['id']}/meal_hour",
                        hx_trigger="change",
                        hx_include="closest form",
                    ),
                    id=f"meal_date_wrap_{event['id']}",
                    cls="hidden flex-col gap-1 w-auto self-end items-end text-right"
                ),
                cls="flex flex-col gap-2 w-full items-end ml-auto",
            ),
            cls="flex items-start justify-between gap-3 w-full"
        ),
        Form(
            Label("Meal type", cls="text-xs text-gray-600", **{"for": meal_type_id}),
            Select(
                *[Option(m, value=m, selected=(event.get("meal_type") == m)) for m in MEAL_TYPES],
                id=meal_type_id,
                name="meal_type",
                aria_label="Meal type",
                cls="web_input border border-white rounded-lg px-2 py-1 text-sm",
                hx_post=f"/cart/event/{event['id']}/meal_type",
                hx_trigger="change",
                onchange="this.blur();",
            ),
            cls="flex gap-3 items-center justify-end"
        ),
        cls="flex flex-col gap-3"
    )


def MacrosSummary(event, portions, compact: bool = False):
    total_amount = sum(float(p.get("amount_g") or 0.0) for p in portions)
    inferred_amount_confidence_num = 0.0
    inferred_quality_confidence_num = 0.0
    for portion in portions:
        amount = float(portion.get("amount_g") or 0.0)
        inferred_amount_confidence_num += amount * float(bool(portion.get("strictly_weighed")))
        inferred_quality_confidence_num += amount * float(bool(portion.get("macros_quality")))
    inferred_amount_confidence = (inferred_amount_confidence_num / total_amount) if total_amount > 0 else 0.0
    inferred_quality_confidence = (inferred_quality_confidence_num / total_amount) if total_amount > 0 else 0.0
    amount_confidence = event.get("amount_confidence")
    quality_confidence = event.get("quality_confidence")
    if amount_confidence is None:
        amount_confidence = inferred_amount_confidence
    if quality_confidence is None:
        quality_confidence = inferred_quality_confidence

    compact_keys = {"carbs", "proteins", "fats", "fiber"}
    pills = []
    pill_cls = (
        "rounded-md px-1.5 py-1 text-[10px] leading-tight flex justify-between gap-1.5"
        if compact
        else "rounded-md px-2 py-1 text-xs md:rounded-lg md:px-3 md:py-2 md:text-sm flex justify-between gap-2"
    )
    for macro_key, label, uncertainty_key in MACRO_KEYS:
        if compact and macro_key not in compact_keys:
            continue
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

        label_block = Span(label, cls="font-semibold")
        if not compact:
            label_block = Div(
                Span(label, cls="font-semibold"),
                Button(
                    "?",
                    type="button",
                    title=f"Uncertainty: {inferred_uncertainty * 100:.1f}%",
                    onclick=f"alert('Uncertainty: {inferred_uncertainty * 100:.1f}%');",
                    cls="""
                        web_button rounded-full border-[1px] border-black/50
                        h-4 w-4 md:h-5 md:w-5
                        text-[10px] md:text-xs
                        p-0 leading-none
                        flex items-center justify-center
                        shadow-none
                    """,
                ),
                cls="flex items-center gap-1"
            )

        pills.append(
            Div(
                label_block,
                Span(f"{total:.1f} g"),
                style=(
                    f"background-color: {macro_color(uncertainty, amount_confidence, quality_confidence)}; "
                    f"color: {macro_text_color(uncertainty, amount_confidence, quality_confidence)};"
                ),
                title=(
                    f"Unknown {label.lower()} in "
                    f"{inferred_uncertainty * 100:.1f}% of ingredient amount | "
                    f"Strictly weighted confidence: {float(amount_confidence) * 100:.1f}% | "
                    f"Macros quality confidence: {float(quality_confidence) * 100:.1f}%"
                ),
                cls=pill_cls,
            )
        )

    header = (
        Span(f"Total: {total_amount:.1f} g", cls="text-[10px] text-gray-700 md:text-xs")
        if compact
        else Div(
            H3("Meal macros", cls="font-semibold text-sm md:text-base"),
            Span(f"Total: {total_amount:.1f} g", cls="text-xs md:text-sm text-gray-700"),
            cls="flex items-center justify-between gap-2"
        )
    )

    return Div(
        header,
        Div(*pills, cls="grid grid-cols-2 md:grid-cols-2 gap-1" if compact else "grid grid-cols-2 gap-1 md:gap-2"),
        cls="flex flex-col gap-2"
    )


def _unit_options(default_portion_base: float, base_unit: str):
    hundred_label = f"100{base_unit}"
    one_label = base_unit
    return [
        Option(
            f"serving ({default_portion_base:.0f}{base_unit})",
            value="portion",
            selected=True,
            data_factor=f"{default_portion_base:.6f}",
            data_unit_label="serving",
        ),
        Option(f"{hundred_label} (100{base_unit})", value="x100", data_factor="100.000000", data_unit_label=hundred_label),
        Option(f"{one_label} (1{base_unit})", value=base_unit, data_factor="1.000000", data_unit_label=one_label),
        Option(f"lb (453.59{base_unit})", value="lb", data_factor="453.592370", data_unit_label="lb"),
        Option(f"oz (28.35{base_unit})", value="oz", data_factor="28.349523", data_unit_label="oz"),
    ]


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
    item_key = f"{event['id']}_{origin}_{origin_id}"
    display_input_id = f"display_input_{item_key}"
    grams_input_id = f"grams_input_{item_key}"
    unit_select_id = f"unit_select_{item_key}"
    side_unit_id = f"side_unit_{item_key}"
    default_display = f"{units_count:.2f}".replace(".", ",")
    confirm_id = f"delete_food_confirm_{item_key}"
    ingredient_name = portion_name(sample)
    refresh_cart_js = "htmx.ajax('GET','/cart',{target:'#main_content',swap:'innerHTML'});"
    offset_input_id = f"offset_input_{item_key}"

    return Div(
        Div(
            Div(ingredient_name, cls="font-semibold"),
            Form(
                Button(
                    "Delete food",
                    type="button",
                    cls="web_button px-2 py-1 text-xs text-white",
                    style="background-color:#b91c1c;border-color:#b91c1c;",
                    onclick=_open_modal_js(confirm_id),
                ),
                cls="flex flex-col items-end gap-2"
            ),
            cls="flex items-center justify-between gap-2"
        ),
        ConfirmActionModal(
            modal_id=confirm_id,
            title="Delete food",
            question="Are you sure you want to delete this food?",
            yes_button=Button(
                "Yes",
                type="button",
                cls="web_button px-4 py-2 text-sm text-white",
                style="background-color:#b91c1c;border-color:#b91c1c;",
                hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/amount",
                hx_vals='{"amount_g":"0"}',
                hx_swap="none",
                **{"hx-on:htmx:after-request": refresh_cart_js},
                data_skip_page_loading="true",
                onclick=_close_modal_js(confirm_id),
            ),
        ),
        Form(
            Input(type="hidden", name="unit_g", value=f"{unit_g:.4f}"),
            Div(
                Input(
                    type="text",
                    inputmode="decimal",
                    id=display_input_id,
                    value=default_display,
                    aria_label=f"Amount for {ingredient_name}",
                    cls="web_input border border-white rounded-lg px-2 py-1 w-24 text-base",
                    oninput=f"dbRecalcGrams('{display_input_id}','{unit_select_id}','{grams_input_id}')",
                    onchange=f"dbRecalcGrams('{display_input_id}','{unit_select_id}','{grams_input_id}', true)",
                    onclick="this.select()",
                ),
                Span("serving", id=side_unit_id, cls="text-xs text-gray-600"),
                Input(
                    type="hidden",
                    name="amount_g",
                    id=grams_input_id,
                    value=f"{amount:.6f}",
                    hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/amount",
                    hx_trigger="change",
                    hx_include="closest form",
                    hx_swap="none",
                    **{"hx-on:htmx:after-request": refresh_cart_js},
                ),Select(
                    *_unit_options(unit_g, unit_label),
                    id=unit_select_id,
                    data_display_id=display_input_id,
                    data_grams_id=grams_input_id,
                    data_side_unit_id=side_unit_id,
                    data_persist_key=f"cart_unit_{item_key}",
                    aria_label=f"Unit selector for {ingredient_name}",
                    cls="web_input border border-white rounded-lg px-2 py-1 text-xs md:text-sm justify-self-end",
                    onchange=f"dbRecalcDisplayFromGrams('{display_input_id}','{unit_select_id}','{grams_input_id}','{side_unit_id}')",
                ),
                cls="flex items-center gap-2"
            ),
            cls="flex flex-col gap-2"
        ),
        Div(
            Label("Offset (min)", cls="text-xs text-gray-600", **{"for": offset_input_id}),
            Input(
                type="text",
                id=offset_input_id,
                name="offset_minutes",
                inputmode="numeric",
                pattern="[0-9]*",
                value=str(offset_value),
                aria_label=f"Offset minutes for {ingredient_name}",
                cls="web_input border border-white rounded-lg px-2 py-1 w-24 text-base",
                hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/offset",
                hx_trigger="change",
                onclick= "this.select()",
            ),
            cls="flex items-center gap-2"
        ),
        Div(
            Label("Strictly weighted", cls="text-xs text-gray-600"),
            _checkbox(
                name="strictly_weighed",
                checked=bool(sample.get("strictly_weighed")),
                hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/strictly_weighed",
                aria_label=f"Strictly weighted for {ingredient_name}",
                hx_swap="outerHTML",
                hx_target=f"#macros_summary_event_{event['id']}",
            ),
            cls="flex items-center gap-2"
        ),
        Div(
            Label("Macros quality", cls="text-xs text-gray-600"),
            _checkbox(
                name="macros_quality",
                checked=bool(sample.get("macros_quality")),
                hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/macros_quality",
                aria_label=f"Macros quality for {ingredient_name}",
                hx_swap="outerHTML",
                hx_target=f"#macros_summary_event_{event['id']}",
            ),
            cls="flex items-center gap-2"
        ),
        Div(
            Label("Cooked weight", cls="text-xs text-gray-600"),
            _checkbox(
                name="is_cooked_weight",
                checked=bool(sample.get("is_cooked_weight")),
                hx_post=f"/cart/event/{event['id']}/ingredient/{origin}/{origin_id}/is_cooked_weight",
                aria_label=f"Cooked weight for {ingredient_name}",
                hx_swap="outerHTML",
                hx_target=f"#macros_summary_event_{event['id']}",
            ),
            cls="flex items-center gap-2"
        ),
        cls="web_container p-4 rounded-2xl flex flex-col gap-3 "
    )


def ConfirmSection(event, portions):
    total_amount = sum(float(p.get("amount_g") or 0.0) for p in portions)
    ingested_value_id = f"ingested_value_{event['id']}"
    return Form(
        Input(type="hidden", name="total_amount", value=f"{total_amount:.4f}"),
        Input(type="hidden", name="ingested_unit", value="g", id=f"ingested_unit_{event['id']}"),
        Input(
            type="number",
            id=ingested_value_id,
            inputmode="number",
            step="0.1",
            min="0",
            pattern="[0-9]*",
            name="ingested_value",
            value=f"{float(event.get('ingested_amount') or 0.0):.1f}" if event.get("ingested_amount") is not None else "",
            aria_label="Ingested amount",
            placeholder="Ingested amount",
            cls="""
                web_input border border-white rounded-lg
                px-2 py-1 w-24 text-base
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
            aria_label="Toggle ingested amount unit",
            cls="""
                web_button px-2 py-1 text-base min-w-10
                md:px-2 md:py-2 md:text-sm md:min-w-12
            """
        ),
        Button(
            "Confirm food",
            type="button",
            cls="""
                web_button px-2 py-1 text-base
                md:px-4 md:py-2 md:text-sm
            """,
            hx_post=f"/cart/event/{event['id']}/confirm",
            hx_include="closest form",
        ),
        cls="flex items-center gap-1 md:gap-2 justify-end"
    )


def DeleteMealModal(event):
    confirm_id = f"delete_meal_confirm_{event['id']}"
    refresh_cart_js = "htmx.ajax('GET','/cart',{target:'#main_content',swap:'innerHTML'});"
    return ConfirmActionModal(
        modal_id=confirm_id,
        title="Delete meal",
        question="Are you sure you want to delete this meal?",
        yes_button=Button(
            "Yes",
            type="button",
            cls="web_button px-4 py-2 text-sm text-white",
            style="background-color:#b91c1c;border-color:#b91c1c;",
            hx_post=f"/cart/event/{event['id']}/delete",
            hx_swap="none",
            **{"hx-on:htmx:after-request": refresh_cart_js},
            data_skip_page_loading="true",
            onclick=_close_modal_js(confirm_id),
        ),
    )


def CartCard(event, portions):
    grouped_portions = group_portions(portions)
    confirm_id = f"delete_meal_confirm_{event['id']}"
    eating_out_id = f"eating_out_{event['id']}"
    insulin_dose_id = f"insulin_dose_{event['id']}"
    return Div(
        EventHeader(event),
        Div(
            Div(
                Label("Eating out", cls="text-xs text-gray-600", **{"for": eating_out_id}),
                _checkbox(
                    name="eating_out",
                    checked=bool(event.get("eating_out")),
                    hx_post=f"/cart/event/{event['id']}/eating_out",
                    input_id=eating_out_id,
                    aria_label="Eating out",
                ),
                cls="flex items-center gap-2"
            ),
            Div(
                Label("Insulin", cls="text-xs text-gray-600", **{"for": insulin_dose_id}),
                _checkbox(
                    name="insulin_dose",
                    checked=bool(event.get("insulin_dose")),
                    hx_post=f"/cart/event/{event['id']}/insulin_dose",
                    input_id=insulin_dose_id,
                    aria_label="Insulin",
                ),
                cls="flex items-center gap-2"
            ),
            Button(
                "Delete meal",
                type="button",
                cls="web_button px-2 py-1 text-xs text-white",
                style="background-color:#b91c1c;border-color:#b91c1c;",
                onclick=_open_modal_js(confirm_id),
            ),
            cls="flex items-center justify-between gap-2"
        ),
        DeleteMealModal(event),
        Div(
            MacrosSummary(event, portions),
            id=f"macros_summary_event_{event['id']}",
        ),
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
        """,
        hx_target="#main_content",
        hx_swap="innerHTML",
    )
