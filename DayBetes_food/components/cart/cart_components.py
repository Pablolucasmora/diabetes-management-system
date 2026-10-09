import json

from fasthtml.common import *

from DayBetes_food.components.cart.cart_shared import (
    CHECKBOX_CLS,
    MACRO_KEYS,
    calculate_macro_summary_metrics,
    display_unit,
    group_portions,
    macro_color,
    macro_text_color,
    parse_source_macro,
    portion_intake_amount,
    portion_macro_amount,
    portion_name,
    unit_amount,
)
from DayBetes_food.components.injection_zone import (
    BASE_INJECTION_ZONE_IMAGE,
    INJECTION_ZONE_IMAGE_BY_ZONE,
    injection_zone_image,
    injection_zone_label,
    asset_busted,
)
from DayBetes_food.domain.constants import AmountInputUnit, InjectionZone, MealType, PortionOrigin
from DayBetes_food.domain.intake_event import (
    INTAKE_EVENT_NAME_MAX_LENGTH,
    INTAKE_EVENT_NOTES_MAX_LENGTH,
)
from DayBetes_food.domain.intake_plate import (
    INTAKE_PLATE_NAME_MAX_LENGTH,
    derive_plate_name,
)
from DayBetes_food.time_utils import local_now, to_local


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
        ),
        _check_icon(),
        cls="flex items-center cursor-pointer relative h-5 w-5",
    )


# Visible label of each tri-state flag (the interface is in English, 7.12).
_TRI_STATE_FLAG_LABELS = {
    "strictly_weighed": "Strictly weighted",
    "macros_quality": "Macros quality",
}


def tri_state_flag_id(name: str, portion_id: int) -> str:
    """Stable id of a tri-state control, target of its own OOB repaint (9.5)."""
    return f"portion_flag_{name}_{portion_id}"


def PortionTriStateFlag(event_id: int, portion, name: str, ingredient_name: str, oob: bool = False):
    """Tri-state control of one portion flag (`strictly_weighed`/`macros_quality`).

    Single builder for the row and for the route response: the route repaints
    this control out of band next to `MacrosSummary`, so the next state it
    sends is always the one computed from the row just saved (9.5 cart HTMX
    contract, frontend_conventions.md 6).
    """
    return _TriStateFlag(
        name=name,
        value=getattr(portion, name),
        hx_post=f"/cart/portion/{portion.id}/{name}",
        aria_label=f"{_TRI_STATE_FLAG_LABELS[name]} for {ingredient_name}",
        hx_target=f"#macros_summary_event_{event_id}",
        hx_swap="outerHTML",
        element_id=tri_state_flag_id(name, portion.id),
        oob=oob,
    )


def _TriStateFlag(
    name: str,
    value,
    hx_post: str,
    aria_label: str = "",
    hx_target: str = "",
    hx_swap: str = "",
    element_id: str = "",
    oob: bool = False,
):
    """Tri-state flag: NULL -> True -> False -> NULL (decision 2026-09-18).

    A two-state checkbox cannot represent "no data": `NULL` must be visible and
    distinguishable from an explicit `False` (frontend_conventions.md 6,
    code_conventions.md 7.14). The next state is computed here, on the server,
    and sent in `hx_vals`; the client does not decide the transition. The
    "no data" state carries a small `–` marker next to the control.
    """
    if value is True:
        next_value, glyph = "false", "✓"
        style = "background-color:#111827;border-color:#111827;color:#ffffff;"
    elif value is False:
        next_value, glyph = "", ""
        style = "background-color:#ffffff;border-color:#9ca3af;color:#111827;"
    else:
        next_value, glyph = "true", ""
        style = "background-color:#ffffff;border-color:#d1d5db;color:#111827;"
    return Div(
        Button(
            glyph,
            type="button",
            aria_label=aria_label or name.replace("_", " ").title(),
            cls="w-5 h-5 rounded border flex items-center justify-center text-xs leading-none p-0",
            style=style,
            hx_post=hx_post,
            hx_vals=json.dumps({"value": next_value}),
            **({"hx_target": hx_target} if hx_target else {}),
            **({"hx_swap": hx_swap} if hx_swap else {}),
        ),
        Span("–", cls="text-xs text-gray-500") if value is None else None,
        cls="flex items-center gap-1",
        **({"id": element_id} if element_id else {}),
        **({"hx_swap_oob": "true"} if oob else {}),
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


def _open_injection_modal_js(modal_id: str) -> str:
    return (
        f"const m=document.getElementById('{modal_id}');"
        "if(!m) return;"
        "const img=m.querySelector('[data-injection-image]');"
        "const hidden=m.querySelector('[data-injection-zone-input]');"
        "if(img){"
        "const base=img.getAttribute('data-base-img')||'/images/content/injection_zones/injection_zones.svg';"
        "const zone=hidden&&hidden.value?hidden.value:'';"
        "const zoneBtn=zone?m.querySelector(\"[data-zone='\"+zone+\"']\"):null;"
        "const target=(zoneBtn&&zoneBtn.getAttribute('data-zone-img'))||base;"
        "img.dataset.fallbackStage='target';"
        "img.onerror=function(){"
        "if(this.dataset.fallbackStage==='target'){"
        "this.dataset.fallbackStage='base';"
        "this.src=base;"
        "return;"
        "}"
        "this.onerror=null;"
        "this.src='/images/content/injection.svg';"
        "};"
        "img.src=target;"
        "}"
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
    meal_time = to_local(event.meal_time) or local_now()
    event_name_id = f"event_name_{event.id}"
    meal_hour_id = f"meal_hour_{event.id}"
    meal_date_id = f"meal_date_{event.id}"
    meal_type_id = f"meal_type_{event.id}"
    card_target = f"#cart_card_event_{event.id}"
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
                    value=event.name or "",
                    maxlength=str(INTAKE_EVENT_NAME_MAX_LENGTH),
                    placeholder=f"Intake event #{event.id}",
                    aria_label="Event name",
                    cls="""
                        w-full font-bold text-lg text-black
                        px-0 py-0 border-0 rounded-none
                        bg-transparent shadow-none
                        focus:outline-none
                    """,
                    style="background:transparent;border-color:transparent;box-shadow:none;",
                    hx_post=f"/cart/event/{event.id}/name",
                    hx_trigger="change",
                    hx_target=card_target,
                    hx_swap="outerHTML",
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
                        hx_post=f"/cart/event/{event.id}/meal_hour",
                        hx_trigger="blur",
                        hx_include="closest form",
                        hx_target="#cart_events_list",
                        hx_swap="outerHTML",
                    ),
                    Button(
                        "Date",
                        type="button",
                        cls="web_button px-2 py-1 text-xs",
                        onclick=(
                            f"const el=document.getElementById('meal_date_wrap_{event.id}');"
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
                        hx_post=f"/cart/event/{event.id}/meal_hour",
                        hx_trigger="change",
                        hx_include="closest form",
                        hx_target="#cart_events_list",
                        hx_swap="outerHTML",
                    ),
                    id=f"meal_date_wrap_{event.id}",
                    cls="hidden flex-col gap-1 w-auto self-end items-end text-right"
                ),
                cls="flex flex-col gap-2 w-full items-end ml-auto",
            ),
            cls="flex items-start justify-between gap-3 w-full"
        ),
        Form(
            Label("Meal type", cls="text-xs text-gray-600", **{"for": meal_type_id}),
            Select(
                # Explicit placeholder for the "not chosen" state: without it,
                # an event.meal_type of None would leave the <select> with no
                # <option selected>, and the browser marks the first option as
                # chosen even though the database has NULL — the user would
                # confirm believing in a meal_type that was never saved (§7.14
                # of code_conventions.md, decision 2026-09-11). It should never
                # show except for time-slot gaps or an event created before this fix.
                Option("— Select —", value="", selected=(event.meal_type is None), disabled=True),
                *[Option(meal_type.value, value=meal_type.value, selected=(event.meal_type is meal_type)) for meal_type in MealType],
                id=meal_type_id,
                name="meal_type",
                aria_label="Meal type",
                cls="web_input border border-white rounded-lg px-2 py-1 text-sm",
                hx_post=f"/cart/event/{event.id}/meal_type",
                hx_trigger="change",
                hx_target=card_target,
                hx_swap="outerHTML",
                onchange="this.blur();",
            ),
            cls="flex gap-3 items-center justify-end"
        ),
        cls="flex flex-col gap-3"
    )


def MacrosSummary(event, portions, compact: bool = False):
    total_amount = sum(portion_intake_amount(p) for p in portions)
    inferred_metrics = calculate_macro_summary_metrics(portions)
    total_calories = 0.0
    for portion in portions:
        calories_100 = parse_source_macro(portion, "calories")
        if calories_100 is None:
            continue
        total_calories += portion_macro_amount(portion) * float(calories_100) / 100.0

    amount_confidence = event.amount_confidence
    quality_confidence = event.quality_confidence
    if amount_confidence is None:
        amount_confidence = inferred_metrics["amount_confidence"]
    if quality_confidence is None:
        quality_confidence = inferred_metrics["quality_confidence"]

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
        for portion in portions:
            amount = portion_macro_amount(portion)
            macro_100 = parse_source_macro(portion, macro_key)
            if macro_100 is None:
                continue
            total += amount * float(macro_100) / 100.0

        inferred_uncertainty = inferred_metrics[uncertainty_key]
        uncertainty = getattr(event, uncertainty_key)
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
        Span(f"Total: {total_amount:.1f} g | {total_calories:.0f} kcal", cls="text-[10px] text-gray-700 md:text-xs")
        if compact
        else Div(
            H3("Meal macros", cls="font-semibold text-sm md:text-base"),
            Span(f"Total: {total_amount:.1f} g | {total_calories:.0f} kcal", cls="text-xs md:text-sm text-gray-700"),
            cls="flex items-center justify-between gap-2"
        )
    )

    return Div(
        header,
        Div(*pills, cls="grid grid-cols-2 md:grid-cols-2 gap-1" if compact else "grid grid-cols-2 gap-1 md:gap-2"),
        cls="flex flex-col gap-2"
    )


def _unit_options(default_portion_base: float | None, base_unit: str):
    """Options of the amount unit selector.

    The conversion factors come from the central enum (measurement §11): the
    emitted value is the enum code and `data_factor` (presentation only) is
    generated from `grams_factor`. `portion` has no constant factor: its factor
    is the food's `unit_g`, resolved on the server from the database. With no
    serving (`default_portion_base is None`) the `serving` option is not offered
    and grams is selected (H15).
    """
    one_label = base_unit
    options = []
    if default_portion_base is not None:
        options.append(
            Option(
                f"serving ({default_portion_base:.0f}{base_unit})",
                value=AmountInputUnit.PORTION.value,
                selected=True,
                data_factor=f"{default_portion_base:.6f}",
                data_unit_label="serving",
            )
        )
    options.extend(
        [
            Option(
                f"{one_label} (1{base_unit})",
                value=AmountInputUnit.GRAMS.value,
                selected=default_portion_base is None,
                data_factor=f"{AmountInputUnit.GRAMS.grams_factor:.6f}",
                data_unit_label=one_label,
            ),
            Option(
                f"lb ({AmountInputUnit.LB.grams_factor:.2f}{base_unit})",
                value=AmountInputUnit.LB.value,
                data_factor=f"{AmountInputUnit.LB.grams_factor:.6f}",
                data_unit_label="lb",
            ),
            Option(
                f"oz ({AmountInputUnit.OZ.grams_factor:.2f}{base_unit})",
                value=AmountInputUnit.OZ.value,
                data_factor=f"{AmountInputUnit.OZ.grams_factor:.6f}",
                data_unit_label="oz",
            ),
        ]
    )
    return options


def _portions_by_plate(portions):
    """Distribute an event's portions by plate, keeping their order.

    The visual grouping of equal rows happens **inside** each plate (§7.8):
    grouping by event would collapse into a single row the same food present
    in two plates, which is exactly what the §4.6.4 unique key allows to
    tell apart.
    """
    by_plate = {}
    for portion in portions:
        plate_id = portion.plate_id
        if plate_id is None:
            continue
        by_plate.setdefault(int(plate_id), []).append(portion)
    return by_plate


def plate_display_name(plate, plate_portions) -> str:
    """Visible name of a plate: its own, or the derived one (§4.6.3).

    The derived one is computed here, at render time, because it is not
    stored: it depends on the ingredients the plate has right now.
    """
    if plate.name:
        return plate.name
    return derive_plate_name([portion_name(portion) for portion in plate_portions])


def _ApplyAllButton(plate, offset_input_id, card_target):
    """`Apply all`: propagate an offset to the whole plate (§4.6.2, §7.3/§7.4).

    It sends the value currently in the associated offset input, whether the
    header's or a row's: the endpoint is the same and so are the semantics
    (it sets the plate's offset and writes it into all its portions).

    `hx-sync` with the input is required, not cosmetic: clicking the button
    after typing in the input fires its `change` through the blur, and both
    requests refresh the same card. Without syncing, the first swap removes
    the second request's element from the DOM, its `htmx:afterRequest` never
    reaches the global listener and the loading overlay stays on forever
    (page_loading.js counts pending requests). With `replace`, the button's
    request cancels the input's and there is only one swap.
    """
    return Button(
        "Apply all",
        type="button",
        aria_label="Apply this offset to the whole plate",
        cls="web_button px-2 py-1 text-xs text-white shrink-0",
        style="background-color:#1d4ed8;border-color:#1d4ed8;",
        hx_post=f"/cart/plate/{plate.id}/apply_offset",
        hx_target=card_target,
        hx_swap="outerHTML",
        hx_sync=f"#{offset_input_id}:replace",
        **{"hx-vals": f"js:{{offset_minutes: document.getElementById('{offset_input_id}').value}}"},
    )


def _MoveIngredientSelect(plate, plates, plate_labels, portion_id, item_key, ingredient_name, card_target):
    """`Move` selector: change the portion's plate (§7.5).

    The `+ New plate` option (value 0) creates the plate on the spot and
    moves the row into it. The current plate is left out of the list: moving
    to itself is not an action.

    The labels arrive already resolved (`plate_labels`) because the name of a
    plate without its own name is derived from **its** ingredients (§4.6.3),
    which this row does not have at hand.
    """
    move_id = f"move_select_{item_key}"
    options = [Option("Move to…", value="", selected=True)]
    for other in plates:
        if other.id == plate.id:
            continue
        options.append(Option(plate_labels.get(other.id, ""), value=str(other.id)))
    options.append(Option("+ New plate", value="0"))

    return Div(
        Label("Move", cls="text-xs text-gray-600", **{"for": move_id}),
        Select(
            *options,
            id=move_id,
            name="target_plate_id",
            aria_label=f"Move {ingredient_name} to another plate",
            cls="web_input border border-white rounded-lg px-2 py-1 text-xs md:text-sm",
            hx_post=f"/cart/portion/{portion_id}/move",
            hx_trigger="change",
            hx_target=card_target,
            hx_swap="outerHTML",
        ),
        cls="flex items-center gap-2"
    )


def PlateHeader(event, plate, display_name, card_target):
    """Header of a plate (§7.3): title, offset, `Apply all` and delete.

    The title is edited like the event's (same control, autosave on blur).
    Clearing it returns the plate to its derived name, which is what is shown
    as the placeholder.
    """
    name_input_id = f"plate_name_{plate.id}"
    offset_input_id = f"plate_offset_{plate.id}"
    confirm_id = f"delete_plate_confirm_{plate.id}"
    offset_value = plate.offset_minutes if plate.offset_minutes is not None else 0

    return Div(
        Form(
            Label(
                "Plate name",
                **{"for": name_input_id},
                style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;",
            ),
            Input(
                type="text",
                id=name_input_id,
                name="name",
                value=plate.name or "",
                maxlength=str(INTAKE_PLATE_NAME_MAX_LENGTH),
                placeholder=display_name,
                aria_label="Plate name",
                cls="""
                    w-full font-semibold text-black truncate
                    px-0 py-0 border-0 rounded-none
                    bg-transparent shadow-none
                    focus:outline-none
                """,
                style="background:transparent;border-color:transparent;box-shadow:none;",
                hx_post=f"/cart/plate/{plate.id}/name",
                hx_trigger="change",
                hx_target=card_target,
                hx_swap="outerHTML",
                onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur();}",
                onchange="this.blur();",
                onclick="this.select();",
            ),
            # min-w-0 is what lets `truncate` clip the name instead of pushing
            # the controls out of the card on mobile (§7.9).
            cls="min-w-0 flex-1",
        ),
        Div(
            Label("Offset (min)", cls="text-xs text-gray-600", **{"for": offset_input_id}),
            Input(
                type="text",
                id=offset_input_id,
                name="offset_minutes",
                inputmode="numeric",
                pattern="-?[0-9]*",
                value=str(offset_value),
                aria_label="Plate offset minutes",
                cls="web_input border border-white rounded-lg px-2 py-1 w-16 text-base",
                hx_post=f"/cart/plate/{plate.id}/offset",
                hx_trigger="change",
                hx_target=card_target,
                hx_swap="outerHTML",
                onclick="this.select()",
            ),
            _ApplyAllButton(plate, offset_input_id, card_target),
            Button(
                Img(src="/images/content/delete.svg", alt="Delete plate", cls="w-5 h-5"),
                type="button",
                aria_label="Delete plate",
                title="Delete plate",
                cls="""
                    web_button p-2 shrink-0
                    border-red-600/40 shadow-none
                    w-9 h-9
                    flex items-center justify-center
                    hover:bg-red-50
                """,
                style="color:#b91c1c;",
                onclick=_open_modal_js(confirm_id),
            ),
            cls="flex items-center gap-2 shrink-0 flex-wrap justify-end"
        ),
        ConfirmActionModal(
            modal_id=confirm_id,
            title="Delete plate",
            question="Are you sure you want to delete this plate?",
            yes_button=Button(
                "Yes",
                type="button",
                cls="web_button px-4 py-2 text-sm text-white",
                style="background-color:#b91c1c;border-color:#b91c1c;",
                hx_post=f"/cart/plate/{plate.id}/delete",
                hx_target=card_target,
                hx_swap="outerHTML",
                onclick=_close_modal_js(confirm_id),
            ),
        ),
        cls="flex items-center justify-between gap-2 flex-wrap"
    )


def PlateBlock(event, plate, plate_portions, show_header: bool, plates, plate_labels):
    """A plate inside the event card: header (when applicable) and rows.

    With a single unnamed plate no header is drawn and the card looks as it
    did before plates existed (§7.2); in that case `Apply all` moves down to
    each row (§7.4).
    """
    card_target = f"#cart_card_event_{event.id}"
    grouped = group_portions(plate_portions)

    # Uniqueness by preparation (§4.6.4): when a plate has two or more rows of
    # the same food, each one highlights only the values that differ from the
    # other, so it is clear why they are separate (§7.8).
    by_food = {}
    for item in grouped:
        by_food.setdefault((item["origin"], item["origin_id"]), []).append(item)

    def _differences(item):
        siblings = by_food[(item["origin"], item["origin_id"])]
        if len(siblings) < 2:
            return []
        sample = item["sample"]
        result = []
        for field, label in (("cooking", "Cooking"), ("conservation", "Conservation"), ("final_state", "Final state")):
            if len({getattr(other["sample"], field) for other in siblings}) > 1:
                value = getattr(sample, field)
                result.append((label, value.value if value is not None else None))
        if len({bool(other["sample"].is_cooked_weight) for other in siblings}) > 1:
            result.append(("Weighed", "cooked" if sample.is_cooked_weight else "raw"))
        return result

    return Div(
        PlateHeader(event, plate, plate_labels[plate.id], card_target) if show_header else None,
        *[
            IngredientRow(
                event,
                plate,
                item,
                plates=plates,
                plate_labels=plate_labels,
                show_apply_all=not show_header,
                differences=_differences(item),
            )
            for item in grouped
        ],
        cls=(
            "flex flex-col gap-3 border border-gray-300 rounded-2xl p-3"
            if show_header
            else "flex flex-col gap-3"
        ),
    )


def IngredientRow(event, plate, grouped_item, plates=(), plate_labels=None, show_apply_all=False, differences=()):
    """Row of an ingredient inside a plate.

    `show_apply_all` implements the rule of frontend_conventions.md §7.4: the
    `Apply all` button lives in the plate header and only moves down to the
    row when that header is not drawn (an event with a single unnamed plate).
    It never appears in both places. The `Move` selector is the opposite case:
    it only makes sense when there are headers to tell apart (§7.5).
    """
    sample = grouped_item["sample"]
    portion_id = int(sample.id)
    unit_g = unit_amount(sample)
    unit_label = display_unit(sample)
    amount = float(grouped_item["total_amount_g"] or 0.0)
    offset = sample.offset_minutes
    offset_value = int(offset) if offset is not None else 0
    if unit_g is not None:
        units_count = amount / unit_g if unit_g > 0 else 0.0
        side_label = "serving"
    else:
        # No serving: the selector offers grams and the amount is shown in grams.
        units_count = amount
        side_label = unit_label
    # The key carries the plate and the portion: each row needs its own ids.
    item_key = f"{plate.id}_{portion_id}"
    display_input_id = f"display_input_{item_key}"
    grams_input_id = f"grams_input_{item_key}"
    unit_select_id = f"unit_select_{item_key}"
    side_unit_id = f"side_unit_{item_key}"
    default_display = f"{units_count:.2f}".replace(".", ",")
    confirm_id = f"delete_food_confirm_{item_key}"
    ingredient_name = portion_name(sample)
    card_target = f"#cart_card_event_{event.id}"
    offset_input_id = f"offset_input_{item_key}"

    return Div(
        Div(
            Div(
                Div(ingredient_name, cls="font-semibold"),
                Span(
                    " · ".join(f"{label}: {value or '—'}" for label, value in differences),
                    cls="text-[10px] text-gray-500",
                ) if differences else None,
                cls="flex flex-col min-w-0",
            ),
            Form(
                Button(
                    Img(src="/images/content/delete.svg", alt="Delete food", cls="w-5 h-5"),
                    type="button",
                    aria_label="Delete food",
                    title="Delete food",
                    cls="""
                        web_button p-2
                        border-red-600/40 shadow-none
                        w-9 h-9
                        flex items-center justify-center
                        hover:bg-red-50
                    """,
                    style="color:#b91c1c;",
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
                hx_post=f"/cart/portion/{portion_id}/delete",
                hx_target=card_target,
                hx_swap="outerHTML",
                onclick=_close_modal_js(confirm_id),
            ),
        ),
        Form(
            Div(
                Input(
                    type="text",
                    inputmode="decimal",
                    id=display_input_id,
                    name="amount_value",
                    value=default_display,
                    aria_label=f"Amount for {ingredient_name}",
                    cls="web_input border border-white rounded-lg px-2 py-1 w-24 text-base",
                    hx_post=f"/cart/portion/{portion_id}/amount",
                    hx_trigger="change",
                    hx_include="closest form",
                    hx_target=card_target,
                    hx_swap="outerHTML",
                    oninput=f"dbRecalcGrams('{display_input_id}','{unit_select_id}','{grams_input_id}')",
                    onclick="this.select()",
                ),
                Span(side_label, id=side_unit_id, cls="text-xs text-gray-600"),
                # Presentation-only helper: it is not submitted (no name); the
                # server converts `amount_value` + `amount_unit` itself (§7.13).
                Input(type="hidden", id=grams_input_id, value=f"{amount:.6f}"),
                Select(
                    *_unit_options(unit_g, unit_label),
                    id=unit_select_id,
                    name="amount_unit",
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
                pattern="-?[0-9]*",
                value=str(offset_value),
                aria_label=f"Offset minutes for {ingredient_name}",
                cls="web_input border border-white rounded-lg px-2 py-1 w-24 text-base",
                hx_post=f"/cart/portion/{portion_id}/offset",
                hx_trigger="change",
                hx_target=card_target,
                hx_swap="outerHTML",
                onclick= "this.select()",
            ),
            _ApplyAllButton(plate, offset_input_id, card_target) if show_apply_all else None,
            cls="flex items-center gap-2 flex-wrap"
        ),
        # `Move` appears exactly when there is a plate header, which is the
        # complementary case of the row's `Apply all` (§7.4, §7.5).
        _MoveIngredientSelect(
            plate, plates, plate_labels or {}, portion_id, item_key, ingredient_name, card_target
        )
        if not show_apply_all
        else None,
        Div(
            Label("Strictly weighted", cls="text-xs text-gray-600"),
            PortionTriStateFlag(event.id, sample, "strictly_weighed", ingredient_name),
            cls="flex items-center gap-2"
        ),
        Div(
            Label("Macros quality", cls="text-xs text-gray-600"),
            PortionTriStateFlag(event.id, sample, "macros_quality", ingredient_name),
            cls="flex items-center gap-2"
        ),
        # Catalog origins with a known factor, plus an inherited TRUE portion whose
        # food has lost its factor: it is shown so it can be unmarked (decisions
        # 2026-09-24 / 2026-09-25).
        Div(
            Label("Cooked weight", cls="text-xs text-gray-600"),
            _checkbox(
                name="is_cooked_weight",
                checked=bool(sample.is_cooked_weight),
                hx_post=f"/cart/portion/{portion_id}/is_cooked_weight",
                aria_label=f"Cooked weight for {ingredient_name}",
                hx_swap="outerHTML",
                # Whole card, not only the summary: the flag is part of the
                # uniqueness key (4.6.4), so toggling it can merge two rows.
                hx_target=card_target,
            ),
            cls="flex items-center gap-2"
        ) if (
            sample.origin is PortionOrigin.CATALOG
            and (sample.source.cooking_factor is not None or sample.is_cooked_weight)
        ) else None,
        cls="web_container p-4 rounded-2xl flex flex-col gap-3 "
    )


def NotesSection(event):
    """
    Free-text note of the event, right above "Confirm food".

    It saves itself when leaving the field (`change`), like the event name:
    there is no save button in the cart. The `maxlength` is a UX aid; the real
    limit is checked by the route, which returns 422 if it is exceeded,
    without truncating (§7.3, finding 44 of audit/audit_intake_event.md).
    """
    notes_id = f"event_notes_{event.id}"
    return Form(
        Label("Notes", cls="text-sm text-gray-600", **{"for": notes_id}),
        Input(
            type="text",
            id=notes_id,
            name="notes",
            value=event.notes or "",
            maxlength=str(INTAKE_EVENT_NOTES_MAX_LENGTH),
            placeholder="Add a note for this meal",
            aria_label="Meal notes",
            cls="web_input border border-white rounded-lg px-2 py-1 text-sm w-full",
            hx_post=f"/cart/event/{event.id}/notes",
            hx_trigger="change",
            hx_target=f"#cart_card_event_{event.id}",
            hx_swap="outerHTML",
            onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur();}",
            onchange="this.blur();",
        ),
        cls="flex flex-col gap-1 w-full",
    )


def ConfirmSection(event, portions):
    ingested_value_id = f"ingested_value_{event.id}"
    return Form(
        # The unit this control emits comes from the central units enum, the
        # same one the route validates: no loose literals are written here
        # (§4.3 of code_conventions.md, §11 of measurement_conventions.md;
        # finding 47 of audit/audit_intake_event.md).
        Input(
            type="hidden",
            name="ingested_unit",
            value=AmountInputUnit.GRAMS.value,
            id=f"ingested_unit_{event.id}",
        ),
        Input(
            type="number",
            id=ingested_value_id,
            inputmode="number",
            step="0.1",
            min="0",
            pattern="[0-9]*",
            name="ingested_value",
            value=f"{float(event.ingested_amount or 0.0):.1f}" if event.ingested_amount is not None else "",
            aria_label="Ingested amount",
            placeholder="All of it (100%)",
            cls="""
                web_input border border-white rounded-lg
                px-2 py-1 w-24 text-base
                md:px-3 md:py-2 md:w-36 md:text-sm
            """
        ),
        Button(
            AmountInputUnit.GRAMS.value,
            type="button",
            onclick=(
                f"const hidden=document.getElementById('ingested_unit_{event.id}');"
                f"hidden.value = hidden.value === '{AmountInputUnit.GRAMS.value}'"
                f" ? '{AmountInputUnit.PERCENT.value}'"
                f" : '{AmountInputUnit.GRAMS.value}';"
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
            hx_post=f"/cart/event/{event.id}/confirm",
            hx_include="closest form",
            hx_target=f"#cart_card_event_{event.id}",
            hx_swap="outerHTML",
        ),
        cls="flex items-center gap-1 md:gap-2 justify-end"
    )


def DeleteMealModal(event):
    confirm_id = f"delete_meal_confirm_{event.id}"
    return ConfirmActionModal(
        modal_id=confirm_id,
        title="Delete meal",
        question="Are you sure you want to delete this meal?",
        yes_button=Button(
            "Yes",
            type="button",
            cls="web_button px-4 py-2 text-sm text-white",
            style="background-color:#b91c1c;border-color:#b91c1c;",
            hx_post=f"/cart/event/{event.id}/delete",
            hx_target=f"#cart_card_event_{event.id}",
            hx_swap="outerHTML",
            onclick=_close_modal_js(confirm_id),
        ),
    )


def InjectionZoneModal(event):
    modal_id = f"injection_zone_modal_{event.id}"
    selected_zone = event.injection_zone
    base_image = asset_busted(BASE_INJECTION_ZONE_IMAGE)
    image = asset_busted(injection_zone_image(selected_zone))
    selector_js = (
        f"const mid='{modal_id}';"
        "const box=document.getElementById(mid);"
        "if(!box) return;"
        "const zone=this.getAttribute('data-zone')||'';"
        "const img=box.querySelector('[data-injection-image]');"
        "const hidden=box.querySelector('[data-injection-zone-input]');"
        "if(hidden){hidden.value=zone;}"
        "if(img){img.src=this.getAttribute('data-zone-img')||img.src;}"
        "box.querySelectorAll('[data-zone]').forEach(function(el){"
        "el.classList.remove('ring-2','ring-cyan-500','bg-cyan-50');"
        "});"
        "this.classList.add('ring-2','ring-cyan-500','bg-cyan-50');"
    )
    zone_buttons = [
        Button(
            injection_zone_label(zone),
            type="button",
            cls=(
                "web_button px-3 py-2 text-xs "
                + ("ring-2 ring-cyan-500 bg-cyan-50" if selected_zone is zone else "")
            ),
            **{
                "data-zone": zone.value,
                "data-zone-img": asset_busted(INJECTION_ZONE_IMAGE_BY_ZONE[zone]),
                "onclick": selector_js,
            },
        )
        for zone in InjectionZone
    ]

    return Div(
        Div(
            Div(
                P("Injection zone", cls="text-lg font-semibold"),
                Div(
                    Img(
                        src=image,
                        alt="Injection zones map",
                        cls="w-full max-h-[38vh] md:max-h-[46vh] object-contain rounded-2xl border border-gray-200 bg-white",
                        data_injection_image="true",
                        data_base_img=base_image,
                    ),
                    cls="w-full",
                ),
                Div(*zone_buttons, cls="flex flex-wrap gap-2"),
                Form(
                    Input(
                        type="hidden",
                        name="zone",
                        value=(selected_zone.value if selected_zone else ""),
                        data_injection_zone_input="true",
                    ),
                    Button(
                        "OK",
                        type="button",
                        cls="web_button px-4 py-2 text-sm text-white ml-auto",
                        style="background-color:#111111;border-color:#111111;",
                        hx_post=f"/cart/event/{event.id}/injection_zone",
                        hx_include="closest form",
                        hx_target=f"#cart_card_event_{event.id}",
                        hx_swap="outerHTML",
                        onclick=(
                            "const z=this.form?this.form.querySelector('[data-injection-zone-input]'):null;"
                            "if(!z||!z.value){alert('Select a zone first.');return false;}"
                            + _close_modal_js(modal_id)
                        ),
                    ),
                    cls="w-full flex items-center",
                ),
                onclick="event.stopPropagation()",
                cls="web_container p-4 md:p-5 rounded-3xl w-[92vw] md:w-[88vw] max-w-md flex flex-col gap-3",
            ),
            id=modal_id,
            onclick=_close_modal_js(modal_id),
            cls="""
                fixed inset-0 z-[70]
                flex items-center justify-center
                bg-slate-800/30 backdrop-blur-lg
                px-4
                opacity-0 invisible pointer-events-none
                transition-opacity duration-200
            """,
        )
    )


def CartCard(event, portions, plates=()):
    plates = list(plates)
    portions_by_plate = _portions_by_plate(portions)
    # The plate header is drawn if there are two or more plates or if any of
    # them has its own name (§7.2): without the second condition, naming the
    # only plate of a meal would make that name disappear from the screen.
    show_plate_headers = len(plates) > 1 or any(plate.name for plate in plates)
    # The visible names are resolved once: each plate needs them for its
    # header and every row needs them for the `Move` selector.
    plate_labels = {
        plate.id: plate_display_name(plate, portions_by_plate.get(plate.id, []))
        for plate in plates
    }
    confirm_id = f"delete_meal_confirm_{event.id}"
    eating_out_id = f"eating_out_{event.id}"
    insulin_dose_id = f"insulin_dose_{event.id}"
    card_target = f"#cart_card_event_{event.id}"
    return Div(
        EventHeader(event),
        Div(
            Div(
                Label("Eating out", cls="text-xs text-gray-600", **{"for": eating_out_id}),
                _checkbox(
                    name="eating_out",
                    checked=event.eating_out,
                    hx_post=f"/cart/event/{event.id}/eating_out",
                    input_id=eating_out_id,
                    aria_label="Eating out",
                    hx_target=card_target,
                    hx_swap="outerHTML",
                ),
                cls="flex items-center gap-2"
            ),
            Div(
                Label("Insulin", cls="text-xs text-gray-600", **{"for": insulin_dose_id}),
                _checkbox(
                    name="insulin_dose",
                    checked=event.insulin_dose,
                    hx_post=f"/cart/event/{event.id}/insulin_dose",
                    input_id=insulin_dose_id,
                    aria_label="Insulin",
                    hx_target=card_target,
                    hx_swap="outerHTML",
                ),
                cls="flex items-center gap-2"
            ),
            Div(
                Button(
                    Img(src="/images/content/injection.svg", alt="Injection", cls="w-5 h-5"),
                    type="button",
                    cls="web_button px-2 py-1",
                    onclick=_open_injection_modal_js(f"injection_zone_modal_{event.id}"),
                ),
                P("zone", cls="text-[10px] text-gray-600 text-center"),
                cls=f"flex flex-col items-center gap-1 {'hidden' if not event.insulin_dose else ''}",
            ),
            Button(
                Img(src="/images/content/delete.svg", alt="Delete meal", cls="w-5 h-5"),
                type="button",
                aria_label="Delete meal",
                title="Delete meal",
                cls="""
                    web_button p-2
                    border-red-600/40 shadow-none
                    w-9 h-9
                    flex items-center justify-center
                    hover:bg-red-50
                """,
                style="color:#b91c1c;",
                onclick=_open_modal_js(confirm_id),
            ),
            cls="flex items-center justify-between gap-2"
        ),
        InjectionZoneModal(event),
        DeleteMealModal(event),
        Div(
            MacrosSummary(event, portions),
            id=f"macros_summary_event_{event.id}",
        ),
        Div(
            H3("Plates", cls="font-semibold"),
            *[
                PlateBlock(
                    event,
                    plate,
                    portions_by_plate.get(plate.id, []),
                    show_plate_headers,
                    plates,
                    plate_labels,
                )
                for plate in plates
            ],
            cls="flex flex-col gap-3"
        ),
        Button(
            "+ Add plate",
            type="button",
            aria_label="Add plate to this meal",
            cls="web_button w-full px-2 py-2 text-sm",
            hx_post=f"/cart/event/{event.id}/plate",
            hx_target=card_target,
            hx_swap="outerHTML",
        ),
        NotesSection(event),
        ConfirmSection(event, portions),
        id=f"cart_card_event_{event.id}",
        cls="""
            web_container p-4 rounded-3xl
            md:w-md lg:w-md w-[90vw]
            flex flex-col gap-4
            mx-auto
            transition-[width,margin,padding] duration-150
        """,
    )
