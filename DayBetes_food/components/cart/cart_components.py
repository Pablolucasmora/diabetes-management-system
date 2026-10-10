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
from DayBetes_food.domain.constants import (
    AmountInputUnit,
    ConservationMethod,
    CookingMethod,
    FoodPhysicalState,
    InjectionZone,
    MealType,
    PortionOrigin,
)
from DayBetes_food.domain.intake_event import (
    INTAKE_EVENT_NAME_MAX_LENGTH,
    INTAKE_EVENT_NOTES_MAX_LENGTH,
)
from DayBetes_food.domain.intake_plate import (
    INTAKE_PLATE_NAME_MAX_LENGTH,
    derive_plate_name,
)
from DayBetes_food.components.modal import (
    close_modal_js,
    ConfirmActionModal,
    modal_confirm_button,
    modal_secondary_button,
    ModalLayer,
    open_modal_js,
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
}


def tri_state_flag_id(name: str, portion_id: int) -> str:
    """Stable id of a tri-state control, target of its own OOB repaint (9.5)."""
    return f"portion_flag_{name}_{portion_id}"


def PortionTriStateFlag(event_id: int, portion, name: str, ingredient_name: str, oob: bool = False):
    """Tri-state control of one portion flag (`strictly_weighed`).

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
        + open_modal_js(modal_id)
    )


# Controls inside the glass card are solid: no glass inside glass
# (frontend_conventions.md §8).
_SOFT_BUTTON_CLS = (
    "bg-white border border-line rounded-xl text-stone-900 cursor-pointer "
    "hover:bg-control transition-colors"
)
_FIELD_CLS = "web_input border border-line rounded-xl px-3 py-2 text-sm"
_PILL_FIELD_CLS = "web_input border border-line rounded-full px-3 py-1.5 text-sm"
_SR_ONLY_STYLE = (
    "position:absolute;width:1px;height:1px;padding:0;margin:-1px;"
    "overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;"
)


def _trash_button(label: str, onclick: str):
    return Button(
        Img(src="/images/content/delete.svg", alt=label, cls="w-4 h-4"),
        type="button",
        aria_label=label,
        title=label,
        cls="""
            w-9 h-9 shrink-0 rounded-xl
            flex items-center justify-center
            bg-transparent hover:bg-red-50 cursor-pointer transition-colors
        """,
        style="color:#b91c1c;",
        onclick=onclick,
    )



def EventHeader(event):
    """Name of the meal with its delete button, then when and what kind of
    meal it is, as small pills."""
    meal_time = to_local(event.meal_time) or local_now()
    event_name_id = f"event_name_{event.id}"
    meal_hour_id = f"meal_hour_{event.id}"
    meal_date_id = f"meal_date_{event.id}"
    meal_type_id = f"meal_type_{event.id}"
    card_target = f"#cart_card_event_{event.id}"
    return Div(
        Div(
            Form(
                Label("Event name", **{"for": event_name_id}, style=_SR_ONLY_STYLE),
                Input(
                    type="text",
                    id=event_name_id,
                    name="event_name",
                    value=event.name or "",
                    maxlength=str(INTAKE_EVENT_NAME_MAX_LENGTH),
                    placeholder=f"Intake event #{event.id}",
                    aria_label="Event name",
                    cls="""
                        w-full font-bold text-xl text-black
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
                cls="min-w-0 flex-1",
            ),
            _trash_button("Delete meal", open_modal_js(f"delete_meal_confirm_{event.id}")),
            cls="flex items-center gap-2",
        ),
        Div(
            Form(
                Input(
                    type="time",
                    id=meal_hour_id,
                    value=meal_time.strftime("%H:%M"),
                    name="meal_hour",
                    aria_label="Meal time",
                    cls=_PILL_FIELD_CLS,
                    hx_post=f"/cart/event/{event.id}/meal_hour",
                    hx_trigger="blur",
                    hx_include="closest form",
                    hx_target="#cart_events_list",
                    hx_swap="outerHTML",
                ),
                Button(
                    meal_time.strftime("%b %d"),
                    type="button",
                    aria_label="Change the meal date",
                    cls=f"{_SOFT_BUTTON_CLS} rounded-full px-3 py-1.5",
                    onclick=f"document.getElementById('meal_date_wrap_{event.id}').classList.toggle('hidden');",
                ),
                Div(
                    Label("Meal date", cls="text-xs text-gray-600", **{"for": meal_date_id}),
                    Input(
                        type="date",
                        id=meal_date_id,
                        value=meal_time.strftime("%Y-%m-%d"),
                        name="meal_date",
                        aria_label="Meal date",
                        cls=_PILL_FIELD_CLS,
                        hx_post=f"/cart/event/{event.id}/meal_hour",
                        hx_trigger="change",
                        hx_include="closest form",
                        hx_target="#cart_events_list",
                        hx_swap="outerHTML",
                    ),
                    id=f"meal_date_wrap_{event.id}",
                    cls="hidden w-full flex items-center gap-2",
                ),
                cls="flex flex-wrap items-center gap-2",
            ),
            Form(
                Label("Meal type", **{"for": meal_type_id}, style=_SR_ONLY_STYLE),
                Select(
                    # Explicit placeholder for the "not chosen" state: without it,
                    # an event.meal_type of None would leave the <select> with no
                    # <option selected>, and the browser marks the first option as
                    # chosen even though the database has NULL — the user would
                    # confirm believing in a meal_type that was never saved (§7.14
                    # of code_conventions.md, decision 2026-09-11). It should never
                    # show except for time-slot gaps or an event created before this fix.
                    Option("— Meal type —", value="", selected=(event.meal_type is None), disabled=True),
                    *[Option(meal_type.value, value=meal_type.value, selected=(event.meal_type is meal_type)) for meal_type in MealType],
                    id=meal_type_id,
                    name="meal_type",
                    aria_label="Meal type",
                    cls=_PILL_FIELD_CLS,
                    hx_post=f"/cart/event/{event.id}/meal_type",
                    hx_trigger="change",
                    hx_target=card_target,
                    hx_swap="outerHTML",
                    onchange="this.blur();",
                ),
            ),
            cls="flex flex-wrap items-center gap-2",
        ),
        cls="flex flex-col gap-2",
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
    if amount_confidence is None:
        amount_confidence = inferred_metrics["amount_confidence"]
    # Depends on the food, so it is always live (measurement §6.9.4).
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

        uncertainty = inferred_metrics[uncertainty_key]

        label_block = Span(label, cls="font-semibold")
        if not compact:
            label_block = Div(
                Span(label, cls="font-semibold"),
                Button(
                    "?",
                    type="button",
                    title=f"Uncertainty: {uncertainty * 100:.1f}%",
                    onclick=f"alert('Uncertainty: {uncertainty * 100:.1f}%');",
                    cls="""
                        rounded-full border border-current/50 bg-white/40
                        h-4 w-4 md:h-5 md:w-5
                        text-[10px] md:text-xs
                        p-0 leading-none cursor-pointer
                        flex items-center justify-center
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
                    f"{uncertainty * 100:.1f}% of ingredient amount | "
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
        cls="px-3 py-2 rounded-xl text-xs font-semibold text-white shrink-0 cursor-pointer",
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
        Label("Plate", cls="text-xs text-gray-600 w-24 shrink-0", **{"for": move_id}),
        Select(
            *options,
            id=move_id,
            name="target_plate_id",
            aria_label=f"Move {ingredient_name} to another plate",
            cls=f"{_FIELD_CLS} flex-1 min-w-0",
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
        Div(
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
            _trash_button("Delete plate", open_modal_js(confirm_id)),
            cls="flex items-center gap-2",
        ),
        Div(
            Label("Offset", cls="text-xs text-gray-600", **{"for": offset_input_id}),
            Input(
                type="text",
                id=offset_input_id,
                name="offset_minutes",
                inputmode="numeric",
                pattern="-?[0-9]*",
                value=str(offset_value),
                aria_label="Plate offset minutes",
                cls="web_input border border-line rounded-xl px-2 py-1.5 w-16 text-sm",
                hx_post=f"/cart/plate/{plate.id}/offset",
                hx_trigger="change",
                hx_target=card_target,
                hx_swap="outerHTML",
                onclick="this.select()",
            ),
            Span("min", cls="text-xs text-gray-600"),
            _ApplyAllButton(plate, offset_input_id, card_target),
            cls="flex items-center gap-2 flex-wrap",
        ),
        ConfirmActionModal(
            modal_id=confirm_id,
            title="Delete plate",
            question="Are you sure you want to delete this plate?",
            yes_button=modal_confirm_button(
                "Yes",
                danger=True,
                hx_post=f"/cart/plate/{plate.id}/delete",
                hx_target=card_target,
                hx_swap="outerHTML",
                onclick=close_modal_js(confirm_id),
            ),
        ),
        cls="flex flex-col gap-1.5"
    )


def PlateBlock(event, plate, plate_portions, plates, plate_labels):
    """A plate inside the event card: its header and its rows.

    The header is always drawn, also for a single unnamed plate (§7.2,
    decision 2026-10-10): the plate's offset and `Apply all` live there.
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
        PlateHeader(event, plate, plate_labels[plate.id], card_target),
        *[
            IngredientRow(
                event,
                plate,
                item,
                plates=plates,
                plate_labels=plate_labels,
                differences=_differences(item),
            )
            for item in grouped
        ],
        cls="flex flex-col gap-2 border border-line rounded-2xl p-2.5 bg-white/30",
    )


def _preparation_summary(sample) -> str:
    """One short line with how the ingredient was prepared and weighed."""
    parts = [
        value.value
        for value in (sample.cooking, sample.final_state, sample.conservation)
        if value is not None
    ]
    if sample.is_cooked_weight:
        parts.append("weighed cooked")
    if sample.offset_minutes:
        parts.append(f"{int(sample.offset_minutes):+d} min")
    return " · ".join(parts)


def _preparation_select(label: str, name: str, enum_cls, current, item_key: str):
    select_id = f"{name}_{item_key}"
    return Div(
        Label(label, cls="text-xs text-gray-600", **{"for": select_id}),
        Select(
            # NULL is "no data", shown as such and never as the first value of
            # the enum (frontend_conventions.md §6).
            Option("Not set", value="", selected=current is None),
            *[Option(option.value, value=option.value, selected=current is option) for option in enum_cls],
            id=select_id,
            name=name,
            cls=f"{_FIELD_CLS} w-full",
        ),
        cls="flex flex-col gap-1 min-w-0",
    )


def _settings_group(title: str, *content):
    return Div(
        P(title, cls="web_section_label"),
        *content,
        cls="flex flex-col gap-2 pt-3 border-t border-line-soft",
    )


def IngredientSettingsModal(event, plate, sample, item_key, ingredient_name, plates, plate_labels, card_target):
    """Everything about an ingredient that is not its amount, in a pop-up:
    how it was prepared, how it was weighed, when it was eaten and its plate.

    It keeps the row short, and it is where a wrong or forgotten preparation
    is corrected from the cart. The ingredient's own offset is here; the
    plate's, with `Apply all`, is in the plate header (§7.4).
    """
    portion_id = int(sample.id)
    modal_id = f"ingredient_settings_{item_key}"
    offset_input_id = f"offset_input_{item_key}"
    offset_value = int(sample.offset_minutes) if sample.offset_minutes is not None else 0
    shows_cooked_weight = sample.origin is PortionOrigin.CATALOG and (
        sample.source.cooking_factor is not None or sample.is_cooked_weight
    )
    return ModalLayer(
        Div(
            P(ingredient_name, cls="text-lg font-semibold leading-snug"),
            P("Fix anything that was set wrong.", cls="text-sm text-gray-600"),
            cls="flex flex-col gap-0.5",
        ),
        _settings_group(
            "Preparation",
            Form(
                Div(
                    _preparation_select("Cooking", "cooking", CookingMethod, sample.cooking, item_key),
                    _preparation_select("Final state", "final_state", FoodPhysicalState, sample.final_state, item_key),
                    _preparation_select("Conservation", "conservation", ConservationMethod, sample.conservation, item_key),
                    cls="grid grid-cols-2 gap-2",
                ),
                modal_confirm_button(
                    "Save preparation",
                    cls="w-full py-2.5",
                    hx_post=f"/cart/portion/{portion_id}/preparation",
                    hx_include="closest form",
                    hx_target=card_target,
                    hx_swap="outerHTML",
                    onclick=close_modal_js(modal_id),
                ),
                cls="flex flex-col gap-2",
            ),
        ),
        _settings_group(
            "Weighing",
            # Catalog origins with a known factor, plus an inherited TRUE portion whose
            # food has lost its factor: it is shown so it can be unmarked (decisions
            # 2026-09-24 / 2026-09-25).
            Div(
                Label("Weighed cooked", cls="text-sm text-gray-700"),
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
                cls="flex items-center justify-between gap-2",
            ),
        ) if shows_cooked_weight else None,
        _settings_group(
            "Timing and plate",
            Div(
                Label("Offset", cls="text-xs text-gray-600 w-24 shrink-0", **{"for": offset_input_id}),
                Input(
                    type="text",
                    id=offset_input_id,
                    name="offset_minutes",
                    inputmode="numeric",
                    pattern="-?[0-9]*",
                    value=str(offset_value),
                    aria_label=f"Offset minutes for {ingredient_name}",
                    cls=f"{_FIELD_CLS} w-20",
                    hx_post=f"/cart/portion/{portion_id}/offset",
                    hx_trigger="change",
                    hx_target=card_target,
                    hx_swap="outerHTML",
                    onclick="this.select()",
                ),
                Span("min", cls="text-xs text-gray-600"),
                cls="flex items-center gap-2 flex-wrap",
            ),
            _MoveIngredientSelect(
                plate, plates, plate_labels or {}, portion_id, item_key, ingredient_name, card_target
            ),
        ),
        modal_secondary_button("Done", cls="w-full py-2.5", onclick=close_modal_js(modal_id)),
        modal_id=modal_id,
        card_cls="gap-3 max-h-[85vh] overflow-y-auto",
    )


def IngredientRow(event, plate, grouped_item, plates=(), plate_labels=None, differences=()):
    """Row of an ingredient inside a plate: its name, how it was prepared, its
    amount and `Strictly weighted`. The rest lives in
    `IngredientSettingsModal`, behind `Adjust` (frontend_conventions.md §7.1).
    """
    sample = grouped_item["sample"]
    portion_id = int(sample.id)
    unit_g = unit_amount(sample)
    unit_label = display_unit(sample)
    amount = float(grouped_item["total_amount_g"] or 0.0)
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
    summary = _preparation_summary(sample)

    return Div(
        Div(
            Div(
                Div(ingredient_name, cls="font-semibold leading-snug"),
                Span(
                    " · ".join(f"{label}: {value or '—'}" for label, value in differences),
                    cls="text-[11px] text-amber-700",
                ) if differences else None,
                Span(
                    summary or "Preparation not set",
                    cls=f"text-xs {'text-gray-600' if summary else 'text-gray-400'}",
                ),
                cls="flex flex-col min-w-0 flex-1",
            ),
            Button(
                "Adjust",
                type="button",
                aria_label=f"Adjust {ingredient_name}",
                cls=f"{_SOFT_BUTTON_CLS} px-3 py-1.5 text-xs font-medium shrink-0",
                onclick=open_modal_js(f"ingredient_settings_{item_key}"),
            ),
            _trash_button("Delete food", open_modal_js(confirm_id)),
            cls="flex items-start gap-1.5",
        ),
        Form(
            Input(
                type="text",
                inputmode="decimal",
                id=display_input_id,
                name="amount_value",
                value=default_display,
                aria_label=f"Amount for {ingredient_name}",
                cls=f"{_FIELD_CLS} w-20",
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
                cls=f"{_FIELD_CLS} ml-auto min-w-0",
                onchange=f"dbRecalcDisplayFromGrams('{display_input_id}','{unit_select_id}','{grams_input_id}','{side_unit_id}')",
            ),
            cls="flex items-center gap-2",
        ),
        Div(
            Label("Strictly weighted", cls="text-xs text-gray-600"),
            PortionTriStateFlag(event.id, sample, "strictly_weighed", ingredient_name),
            cls="flex items-center gap-2",
        ),
        ConfirmActionModal(
            modal_id=confirm_id,
            title="Delete food",
            question="Are you sure you want to delete this food?",
            yes_button=modal_confirm_button(
                "Yes",
                danger=True,
                hx_post=f"/cart/portion/{portion_id}/delete",
                hx_target=card_target,
                hx_swap="outerHTML",
                onclick=close_modal_js(confirm_id),
            ),
        ),
        IngredientSettingsModal(
            event, plate, sample, item_key, ingredient_name, plates, plate_labels, card_target
        ),
        cls="bg-white/70 border border-line-soft rounded-2xl p-3 flex flex-col gap-2",
    )


def NotesSection(event):
    """
    Free-text note of the event, right above "Confirm meal".

    It saves itself when leaving the field (`change`), like the event name:
    there is no save button in the cart. The `maxlength` is a UX aid; the real
    limit is checked by the route, which returns 422 if it is exceeded,
    without truncating (§7.3, finding 44 of audit/audit_intake_event.md).
    """
    notes_id = f"event_notes_{event.id}"
    return Form(
        Label("Notes", cls="text-xs text-gray-600", **{"for": notes_id}),
        Input(
            type="text",
            id=notes_id,
            name="notes",
            value=event.notes or "",
            maxlength=str(INTAKE_EVENT_NOTES_MAX_LENGTH),
            placeholder="Add a note for this meal",
            aria_label="Meal notes",
            cls=f"{_FIELD_CLS} w-full",
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
        Div(
            Label("Eaten", cls="text-xs text-gray-600 shrink-0", **{"for": ingested_value_id}),
            Input(
                type="number",
                id=ingested_value_id,
                inputmode="decimal",
                step="0.1",
                min="0",
                name="ingested_value",
                value=f"{float(event.ingested_amount or 0.0):.1f}" if event.ingested_amount is not None else "",
                aria_label="Ingested amount",
                placeholder="All of it",
                cls=f"{_FIELD_CLS} flex-1 min-w-0",
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
                cls=f"{_SOFT_BUTTON_CLS} px-3 py-2 min-w-12",
            ),
            cls="flex items-center gap-2",
        ),
        Button(
            "Confirm meal",
            type="button",
            cls="web_button web_button_primary w-full px-4 py-3 rounded-2xl",
            hx_post=f"/cart/event/{event.id}/confirm",
            hx_include="closest form",
            hx_target=f"#cart_card_event_{event.id}",
            hx_swap="outerHTML",
        ),
        cls="flex flex-col gap-3",
    )


def DeleteMealModal(event):
    confirm_id = f"delete_meal_confirm_{event.id}"
    return ConfirmActionModal(
        modal_id=confirm_id,
        title="Delete meal",
        question="Are you sure you want to delete this meal?",
        yes_button=modal_confirm_button(
            "Yes",
            danger=True,
            hx_post=f"/cart/event/{event.id}/delete",
            hx_target=f"#cart_card_event_{event.id}",
            hx_swap="outerHTML",
            onclick=close_modal_js(confirm_id),
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

    return ModalLayer(
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
            modal_confirm_button(
                "OK",
                cls="ml-auto",
                hx_post=f"/cart/event/{event.id}/injection_zone",
                hx_include="closest form",
                hx_target=f"#cart_card_event_{event.id}",
                hx_swap="outerHTML",
                onclick=(
                    "const z=this.form?this.form.querySelector('[data-injection-zone-input]'):null;"
                    "if(!z||!z.value){alert('Select a zone first.');return false;}"
                    + close_modal_js(modal_id)
                ),
            ),
            cls="w-full flex items-center",
        ),
        modal_id=modal_id,
        card_cls="gap-3",
    )


def _toggle_row(label: str, hint: str, control, extra=None):
    return Div(
        Div(
            P(label, cls="text-sm font-medium text-gray-800"),
            P(hint, cls="text-xs text-gray-500"),
            cls="flex flex-col min-w-0 flex-1",
        ),
        extra,
        control,
        cls="flex items-center gap-3",
    )


def CartCard(event, portions, plates=()):
    """One planned meal, read from top to bottom in the order it is used:
    what it is, what it has, the details that matter before eating, and the
    confirmation (frontend_conventions.md §7.1)."""
    plates = list(plates)
    portions_by_plate = _portions_by_plate(portions)
    # The visible names are resolved once: each plate needs them for its
    # header and every row needs them for the `Move` selector.
    plate_labels = {
        plate.id: plate_display_name(plate, portions_by_plate.get(plate.id, []))
        for plate in plates
    }
    eating_out_id = f"eating_out_{event.id}"
    insulin_dose_id = f"insulin_dose_{event.id}"
    card_target = f"#cart_card_event_{event.id}"
    zone_label = injection_zone_label(event.injection_zone) if event.injection_zone else "Choose zone"
    return Div(
        EventHeader(event),
        DeleteMealModal(event),
        Div(
            MacrosSummary(event, portions),
            id=f"macros_summary_event_{event.id}",
        ),
        Div(
            P("Plates", cls="web_section_label"),
            *[
                PlateBlock(
                    event,
                    plate,
                    portions_by_plate.get(plate.id, []),
                    plates,
                    plate_labels,
                )
                for plate in plates
            ],
            Button(
                "+ Add plate",
                type="button",
                aria_label="Add plate to this meal",
                cls=f"{_SOFT_BUTTON_CLS} w-full px-2 py-2 text-sm border-dashed",
                hx_post=f"/cart/event/{event.id}/plate",
                hx_target=card_target,
                hx_swap="outerHTML",
            ),
            cls="flex flex-col gap-2",
        ),
        Div(
            P("Before you confirm", cls="web_section_label"),
            _toggle_row(
                "Eating out",
                "Restaurant or someone else's kitchen",
                _checkbox(
                    name="eating_out",
                    checked=event.eating_out,
                    hx_post=f"/cart/event/{event.id}/eating_out",
                    input_id=eating_out_id,
                    aria_label="Eating out",
                    hx_target=card_target,
                    hx_swap="outerHTML",
                ),
            ),
            _toggle_row(
                "Insulin",
                "You injected for this meal",
                _checkbox(
                    name="insulin_dose",
                    checked=event.insulin_dose,
                    hx_post=f"/cart/event/{event.id}/insulin_dose",
                    input_id=insulin_dose_id,
                    aria_label="Insulin",
                    hx_target=card_target,
                    hx_swap="outerHTML",
                ),
                extra=Button(
                    Img(src="/images/content/injection.svg", alt="", cls="w-4 h-4"),
                    Span(zone_label),
                    type="button",
                    aria_label="Injection zone",
                    cls=f"{_SOFT_BUTTON_CLS} px-3 py-1.5 text-xs flex items-center gap-1.5 shrink-0",
                    onclick=_open_injection_modal_js(f"injection_zone_modal_{event.id}"),
                ) if event.insulin_dose else None,
            ),
            NotesSection(event),
            cls="flex flex-col gap-3 pt-4 border-t border-line-soft",
        ),
        InjectionZoneModal(event),
        Div(
            ConfirmSection(event, portions),
            cls="pt-4 border-t border-line-soft",
        ),
        id=f"cart_card_event_{event.id}",
        cls="""
            web_container p-4 rounded-3xl
            md:w-md lg:w-md w-[90vw]
            flex flex-col gap-4
            mx-auto
            transition-[width,margin,padding] duration-150
        """,
    )


