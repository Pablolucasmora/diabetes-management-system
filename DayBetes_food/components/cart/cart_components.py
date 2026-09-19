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
from DayBetes_food.domain.constants import AmountInputUnit, InjectionZone, MealType
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
                # Placeholder explícito para el estado "sin elegir": si no se
                # incluyera, un event.meal_type en None dejaría el <select>
                # sin ningún <option selected>, y el navegador marca la
                # primera opción como si fuera la elegida aunque la base
                # tenga NULL — el usuario confirmaría creyendo un meal_type
                # que nunca se guardó (§7.14 de code_conventions.md, decisión
                # 2026-09-11). No debería llegar a mostrarse salvo huecos de
                # franja horaria o un evento creado antes de esta corrección.
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
        total_calories += portion_intake_amount(portion) * float(calories_100) / 100.0

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
            amount = portion_intake_amount(portion)
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


def _portions_by_plate(portions):
    """Reparte las porciones de un evento por tanda, conservando su orden.

    La agrupación visual de filas iguales se hace **dentro** de cada tanda
    (§7.8): agrupar por evento colapsaría en una sola fila el mismo alimento
    presente en dos tandas, que es justo lo que la clave única de §4.6.4
    permite distinguir.
    """
    by_plate = {}
    for portion in portions:
        plate_id = portion.get("plate_id")
        if plate_id is None:
            continue
        by_plate.setdefault(int(plate_id), []).append(portion)
    return by_plate


def plate_display_name(plate, plate_portions) -> str:
    """Nombre visible de una tanda: el propio, o el derivado (§4.6.3).

    El derivado se calcula aquí, en el render, porque no se guarda: depende de
    los ingredientes que la tanda tenga en este momento.
    """
    if plate.name:
        return plate.name
    return derive_plate_name([portion_name(portion) for portion in plate_portions])


def _ApplyAllButton(plate, offset_input_id, card_target):
    """`Apply all`: propaga un offset a toda la tanda (§4.6.2, §7.3/§7.4).

    Envía el valor que haya en ese momento en el input de offset asociado, sea
    el de la cabecera o el de una fila: el endpoint es el mismo y la semántica
    también (fija el offset de la tanda y lo escribe en todas sus porciones).

    `hx-sync` con el input es obligatorio, no cosmético: pulsar el botón
    después de escribir en el input dispara su `change` por el blur, y las dos
    peticiones refrescan la misma tarjeta. Sin sincronizar, el primer swap
    borra del DOM el elemento de la segunda petición, su `htmx:afterRequest`
    ya no llega al listener global y el overlay de carga se queda encendido
    para siempre (page_loading.js cuenta peticiones pendientes). Con
    `replace`, la del botón cancela la del input y solo hay un swap.
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


def _MoveIngredientSelect(plate, plates, plate_labels, origin, origin_id, item_key, ingredient_name, card_target):
    """Selector `Move`: cambia el ingrediente de tanda (§7.5).

    La opción `+ New plate` (valor 0) crea la tanda en el acto y mueve la fila
    a ella. La tanda actual queda fuera de la lista: moverse a sí misma no es
    una acción.

    Las etiquetas llegan ya resueltas (`plate_labels`) porque el nombre de una
    tanda sin nombre propio se deriva de **sus** ingredientes (§4.6.3), que
    esta fila no tiene a mano.
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
            hx_post=f"/cart/plate/{plate.id}/ingredient/{origin}/{origin_id}/move",
            hx_trigger="change",
            hx_target=card_target,
            hx_swap="outerHTML",
        ),
        cls="flex items-center gap-2"
    )


def PlateHeader(event, plate, display_name, card_target):
    """Cabecera de una tanda (§7.3): título, offset, `Apply all` y borrar.

    El título se edita como el del evento (mismo control, autosave al salir).
    Vaciarlo devuelve la tanda a su nombre derivado, que es lo que se muestra
    como placeholder.
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
            # min-w-0 es lo que permite que `truncate` recorte el nombre en vez
            # de empujar los controles fuera de la tarjeta en móvil (§7.9).
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
                "Delete plate",
                type="button",
                cls="web_button px-2 py-1 text-xs text-white shrink-0",
                style="background-color:#b91c1c;border-color:#b91c1c;",
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
    """Una tanda dentro de la tarjeta del evento: cabecera (si procede) y filas.

    Con una sola tanda sin nombre no se pinta cabecera y la tarjeta se ve como
    antes de existir las tandas (§7.2); en ese caso `Apply all` baja a cada
    fila (§7.4).
    """
    card_target = f"#cart_card_event_{event.id}"
    grouped = group_portions(plate_portions)
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
            )
            for item in grouped
        ],
        cls=(
            "flex flex-col gap-3 border border-gray-300 rounded-2xl p-3"
            if show_header
            else "flex flex-col gap-3"
        ),
    )


def IngredientRow(event, plate, grouped_item, plates=(), plate_labels=None, show_apply_all=False):
    """Fila de un ingrediente dentro de una tanda.

    `show_apply_all` implementa la regla de frontend_conventions.md §7.4: el
    botón `Apply all` vive en la cabecera de la tanda y solo baja a la fila
    cuando esa cabecera no se pinta (evento de una sola tanda sin nombre).
    Nunca aparece en los dos sitios. El selector `Move` es el caso contrario:
    solo tiene sentido cuando hay cabeceras que distinguir (§7.5).
    """
    sample = grouped_item["sample"]
    origin = grouped_item["origin"]
    origin_id = grouped_item["origin_id"]
    unit_g = unit_amount(sample)
    unit_label = display_unit(sample)
    amount = float(grouped_item["total_amount_g"] or unit_g)
    offset = sample.get("offset_minutes")
    offset_value = int(offset) if offset is not None else 0
    units_count = amount / unit_g if unit_g > 0 else 0.0
    # La clave lleva la tanda, no el evento: el mismo alimento puede estar en
    # dos tandas de la misma comida y cada fila necesita ids propios.
    item_key = f"{plate.id}_{origin}_{origin_id}"
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
                hx_post=f"/cart/plate/{plate.id}/ingredient/{origin}/{origin_id}/amount",
                hx_vals='{"amount_g":"0"}',
                hx_target=card_target,
                hx_swap="outerHTML",
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
                    hx_post=f"/cart/plate/{plate.id}/ingredient/{origin}/{origin_id}/amount",
                    hx_trigger="change",
                    hx_include="closest form",
                    hx_target=card_target,
                    hx_swap="outerHTML",
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
                pattern="-?[0-9]*",
                value=str(offset_value),
                aria_label=f"Offset minutes for {ingredient_name}",
                cls="web_input border border-white rounded-lg px-2 py-1 w-24 text-base",
                hx_post=f"/cart/plate/{plate.id}/ingredient/{origin}/{origin_id}/offset",
                hx_trigger="change",
                hx_target=card_target,
                hx_swap="outerHTML",
                onclick= "this.select()",
            ),
            _ApplyAllButton(plate, offset_input_id, card_target) if show_apply_all else None,
            cls="flex items-center gap-2 flex-wrap"
        ),
        # `Move` aparece exactamente cuando hay cabecera de tanda, que es el
        # caso complementario de `Apply all` en la fila (§7.4, §7.5).
        _MoveIngredientSelect(
            plate, plates, plate_labels or {}, origin, origin_id, item_key, ingredient_name, card_target
        )
        if not show_apply_all
        else None,
        Div(
            Label("Strictly weighted", cls="text-xs text-gray-600"),
            _checkbox(
                name="strictly_weighed",
                checked=bool(sample.get("strictly_weighed")),
                hx_post=f"/cart/plate/{plate.id}/ingredient/{origin}/{origin_id}/strictly_weighed",
                aria_label=f"Strictly weighted for {ingredient_name}",
                hx_swap="outerHTML",
                hx_target=f"#macros_summary_event_{event.id}",
            ),
            cls="flex items-center gap-2"
        ),
        Div(
            Label("Macros quality", cls="text-xs text-gray-600"),
            _checkbox(
                name="macros_quality",
                checked=bool(sample.get("macros_quality")),
                hx_post=f"/cart/plate/{plate.id}/ingredient/{origin}/{origin_id}/macros_quality",
                aria_label=f"Macros quality for {ingredient_name}",
                hx_swap="outerHTML",
                hx_target=f"#macros_summary_event_{event.id}",
            ),
            cls="flex items-center gap-2"
        ),
        Div(
            Label("Cooked weight", cls="text-xs text-gray-600"),
            _checkbox(
                name="is_cooked_weight",
                checked=bool(sample.get("is_cooked_weight")),
                hx_post=f"/cart/plate/{plate.id}/ingredient/{origin}/{origin_id}/is_cooked_weight",
                aria_label=f"Cooked weight for {ingredient_name}",
                hx_swap="outerHTML",
                hx_target=f"#macros_summary_event_{event.id}",
            ),
            cls="flex items-center gap-2"
        ),
        cls="web_container p-4 rounded-2xl flex flex-col gap-3 "
    )


def NotesSection(event):
    """
    Nota libre del evento, justo encima de "Confirm food".

    Se guarda sola al salir del campo (`change`), igual que el nombre del
    evento: no hay botón de guardar en el carrito. El `maxlength` es ayuda de
    UX; el límite real lo comprueba la ruta y devuelve 422 si se excede, sin
    truncar (§7.3, hallazgo 44 de audit/audit_intake_event.md).
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
        # La unidad que emite este control sale del enum central de unidades,
        # el mismo que valida la ruta: no se escriben aquí literales sueltos
        # (§4.3 de code_conventions.md, §11 de measurement_conventions.md;
        # hallazgo 47 de audit/audit_intake_event.md).
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
    # La cabecera de tanda se pinta si hay dos o más tandas o si alguna tiene
    # nombre propio (§7.2): sin la segunda condición, nombrar la única tanda
    # de una comida haría desaparecer ese nombre de la pantalla.
    show_plate_headers = len(plates) > 1 or any(plate.name for plate in plates)
    # Los nombres visibles se resuelven una sola vez: cada tanda los necesita
    # para su cabecera y todas las filas los necesitan para el selector `Move`.
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
                "Delete meal",
                type="button",
                cls="web_button px-2 py-1 text-xs text-white",
                style="background-color:#b91c1c;border-color:#b91c1c;",
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
            md:w-md lg:w-md w-xs
            flex flex-col gap-4
            mx-auto
            transition-[width,margin,padding] duration-150
        """,
    )
