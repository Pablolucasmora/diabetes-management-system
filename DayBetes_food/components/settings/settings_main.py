from fasthtml.common import *
from DayBetes_food.components.data_sources import ciqual_attribution, off_attribution
from DayBetes_food.components.navigation import back_js
from DayBetes_food.database.queries import get_meal_type_schedule
from DayBetes_food.components.injection_zone import (
    BASE_INJECTION_ZONE_IMAGE,
    INJECTION_ZONE_IMAGE_BY_ZONE,
    injection_zone_image,
    injection_zone_label,
    parse_injection_zone,
    asset_busted,
)
from DayBetes_food.components.insulin_pen import pen_label
from DayBetes_food.domain.constants import InjectionZone, InsulinType
from DayBetes_food.domain.meal_type_schedule import (
    AUTO_ASSIGNABLE_MEAL_TYPES,
    resolve_meal_type_window,
)
from DayBetes_food.time_utils import to_local
from DayBetes_food.config import CSRF_COOKIE_NAME
from DayBetes_food.components.modal import (
    ConfirmActionModal,
    close_modal_js,
    modal_confirm_button,
    ModalLayer,
    open_modal_js,
)
import re


def settings_main(connection, current_user=None):
    username = (current_user or {}).get("username") or "Usuario"
    email = (current_user or {}).get("email") or ""
    return Div(
        Div(
            H1("Settings", cls="text-xl font-bold text-center"),
            Div(
                H2(username, cls="text-3xl font-extrabold text-center text-gray-900"),
                P(email, cls="text-xs text-gray-500 text-center"),
                cls="mt-2 flex flex-col items-center gap-1",
            ),
            P(
                "Configure profile, targets, and app preferences.",
                cls="text-sm text-gray-600 text-center",
            ),
            Form(
                Input(type="hidden", name="csrf_token", value=""),
                Button(
                    "Log out",
                    type="submit",
                    cls="web_button px-4 py-2 text-sm text-white",
                    style="background-color:#b91c1c;border-color:#b91c1c;",
                ),
                action="/auth/logout",
                method="post",
                enctype="application/x-www-form-urlencoded",
                cls="mt-3",
                onsubmit=(
                    f"var m=document.cookie.match(/(?:^|; ){re.escape(CSRF_COOKIE_NAME)}=([^;]+)/);"
                    "if(m){this.querySelector(\"input[name='csrf_token']\").value=decodeURIComponent(m[1]);}"
                ),
            ),
            Button(
                "Injection log",
                type="button",
                cls="web_button food_entry flex items-center justify-between cursor-pointer text-left",
                hx_get="/settings/injections",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button(
                "Insulin pens",
                type="button",
                cls="web_button food_entry flex items-center justify-between cursor-pointer text-left",
                hx_get="/settings/insulin",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button(
                "Meal type schedule",
                type="button",
                cls="web_button food_entry flex items-center justify-between cursor-pointer text-left",
                hx_get="/settings/meal_type_schedule",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            Button(
                "Tags",
                type="button",
                cls="web_button food_entry flex items-center justify-between cursor-pointer text-left",
                hx_get="/settings/tags",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
            ),
            off_attribution(),
            ciqual_attribution(),
            cls="web_container p-6 flex flex-col items-center gap-3",
        ),
        cls="flex flex-col items-center justify-center gap-6 md:mt-7 lg:mt-7 mt-2",
    )


_MEAL_TYPE_SCHEDULE_LABELS = {
    m: m.value.replace("_", " ").capitalize() for m in AUTO_ASSIGNABLE_MEAL_TYPES
}


def meal_type_schedule_row(meal_type, start_time, end_time, is_default: bool):
    """
    An editable row of the automatic meal_type assignment schedule.

    start_time/end_time are always sent together (`hx_include="closest
    form"`): the two columns of the same slot are written in the same
    request, never separately, so the slot is never left half saved with the
    ambiguous meaning of "missing field" (§7.4/§7.9 of code_conventions.md).
    """
    row_id = f"meal_type_schedule_row_{meal_type.value}"
    label = _MEAL_TYPE_SCHEDULE_LABELS[meal_type]
    common_input_cls = (
        "web_input border border-white rounded-lg px-1 py-1 md:px-2 lg:px-2 text-sm "
        "w-full min-w-0 overflow-hidden"
    )
    return Form(
        Input(type="hidden", name="meal_type", value=meal_type.value),
        Div(
            Div(
                P(label, cls="text-sm font-semibold"),
                P("Custom" if not is_default else "Default", cls="text-[10px] text-gray-500"),
                cls="flex flex-col px-2",
            ),
            Button(
                "Reset",
                type="button",
                cls=f"web_button px-2 py-1 text-xs {'invisible' if is_default else ''}",
                hx_post="/settings/meal_type_schedule/reset",
                hx_vals=f'{{"meal_type":"{meal_type.value}"}}',
                hx_target=f"#{row_id}",
                hx_swap="outerHTML",
            ),
            cls="flex items-center justify-between gap-2",
        ),
        Div(
            Div(
                Label("Start", cls="text-xs text-gray-600", **{"for": f"{row_id}_start"}),
                Input(
                    type="time",
                    id=f"{row_id}_start",
                    name="start_time",
                    value=start_time.strftime("%H:%M"),
                    aria_label=f"{label} start time",
                    cls=common_input_cls,
                    hx_post="/settings/meal_type_schedule/update",
                    hx_trigger="change",
                    hx_include="closest form",
                    hx_target=f"#{row_id}",
                    hx_swap="outerHTML",
                ),
                cls="flex flex-col gap-1 min-w-0 px-2",
            ),
            Div(
                Label("End", cls="text-xs text-gray-600", **{"for": f"{row_id}_end"}),
                Input(
                    type="time",
                    id=f"{row_id}_end",
                    name="end_time",
                    value=end_time.strftime("%H:%M"),
                    aria_label=f"{label} end time",
                    cls=common_input_cls,
                    hx_post="/settings/meal_type_schedule/update",
                    hx_trigger="change",
                    hx_include="closest form",
                    hx_target=f"#{row_id}",
                    hx_swap="outerHTML",
                ),
                cls="flex flex-col gap-1 min-w-0 px-3",
            ),
            cls="grid grid-cols-2 gap-1 md:gap-2 lg:gap-2 items-end",
        ),
        id=row_id,
        cls="web_container food_entry flex flex-col gap-2 px-2 py-3 md:px-4 lg:px-4",
    )


def meal_type_schedule_settings_page(connection, user_id: int):
    overrides = get_meal_type_schedule(connection, user_id)
    rows = [
        meal_type_schedule_row(
            meal_type,
            *resolve_meal_type_window(meal_type, overrides),
            is_default=meal_type not in overrides,
        )
        for meal_type in AUTO_ASSIGNABLE_MEAL_TYPES
    ]
    return Div(
        Div(
            Button(
                "Back",
                type="button",
                cls="web_button self-start px-3 py-1.5 text-sm",
                onclick=back_js("/settings"),
            ),
            cls="w-full flex justify-start",
        ),
        H1("Meal type schedule", cls="text-xl font-bold"),
        P(
            "Time windows used to auto-fill meal type when a food is added "
            "outside the cart. Snack and rescue are always chosen manually.",
            cls="text-sm text-gray-600 text-center",
        ),
        Div(*rows, cls="flex flex-col gap-2 w-full"),
        cls="flex flex-col items-center gap-4 md:mt-7 lg:mt-7 mt-2 md:w-md lg:w-md w-xs w-full mx-auto md:mb-28 lg:mb-28 mb-24",
        data_hide_cart="true",
    )


def _format_injection_day(dt):
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"


def _format_injection_hour(dt):
    return dt.strftime("%H:%M")


def _injection_delete_modal(injection):
    modal_id = f"settings_injection_delete_{injection.id}"
    return ConfirmActionModal(
        modal_id=modal_id,
        title="Delete injection",
        question="Are you sure you want to delete this injection log?",
        yes_button=modal_confirm_button(
            "Yes",
            danger=True,
            hx_post=f"/settings/injections/{injection.id}/delete",
            hx_swap="none",
        ),
    )


def _injection_pen_options(injection, open_pens, pens_by_id):
    """The open pens and the one it already has; one without a pen can stay so
    (frontend_conventions.md §9.9). No `+ New pen` here: this page has no pop-up of pens."""
    options = []
    if injection.insulin_pen_id is None:
        options.append(
            Option(
                f"No pen ({'Basal' if injection.insulin_type is InsulinType.BASAL else 'Rapid'}, before pens)",
                value="",
                selected=True,
                data_insulin_type=injection.insulin_type.value,
            )
        )
    pens = list(open_pens)
    current = pens_by_id.get(injection.insulin_pen_id)
    if current is not None and all(pen.id != current.id for pen in pens):
        pens.insert(0, current)
    for pen in pens:
        options.append(
            Option(
                pen_label(pen),
                value=str(pen.id),
                selected=pen.id == injection.insulin_pen_id,
                data_insulin_type=pen.insulin_type.value,
            )
        )
    return options


def _injection_edit_modal(injection, open_pens, pens_by_id):
    modal_id = f"settings_injection_edit_{injection.id}"
    local_dt = to_local(injection.shot_time)
    shot_hour = local_dt.strftime("%H:%M") if local_dt else ""
    shot_date = local_dt.strftime("%Y-%m-%d") if local_dt else ""
    selected_zone = injection.injection_zone
    units = injection.units
    base_image = asset_busted(BASE_INJECTION_ZONE_IMAGE)
    image = asset_busted(injection_zone_image(selected_zone))
    selector_js = (
        f"const mid='{modal_id}';"
        "const box=document.getElementById(mid);"
        "if(!box) return;"
        "const zone=this.getAttribute('data-zone')||'';"
        "const img=box.querySelector('[data-settings-injection-image]');"
        "const hidden=box.querySelector('[data-settings-injection-zone-input]');"
        "if(hidden){hidden.value=zone;}"
        "if(img){img.src=this.getAttribute('data-zone-img')||img.src;}"
        "box.querySelectorAll('[data-zone]').forEach(function(el){"
        "el.classList.remove('ring-2','ring-cyan-500','bg-cyan-50');"
        "});"
        "this.classList.add('ring-2','ring-cyan-500','bg-cyan-50');"
    )
    switch_type_js = (
        f"const box=document.getElementById('{modal_id}');"
        "if(!box) return;"
        "const sel=box.querySelector('[data-settings-insulin-pen]');"
        "const hint=box.querySelector('[data-settings-dose-optional]');"
        "if(!sel||!hint) return;"
        # The dose is required for basal and optional for rapid (measurement §8.1);
        # the type is the one of the pen's brand (§8.4).
        "const opt=sel.options[sel.selectedIndex];"
        "hint.classList.toggle('hidden',!!opt&&opt.dataset.insulinType==='basal');"
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
        P("Insulin injection", cls="text-lg font-semibold"),
        Form(
            Input(type="hidden", name="injection_id", value=str(injection.id)),
            Div(
                Div(
                    Label("Pen", cls="text-xs text-gray-600"),
                    Select(
                        *_injection_pen_options(injection, open_pens, pens_by_id),
                        name="insulin_pen_id",
                        aria_label="Insulin pen",
                        cls="web_input border border-white rounded-lg px-2 py-1 text-base min-w-0 w-full",
                        data_settings_insulin_pen="true",
                        onchange=switch_type_js,
                    ),
                    cls="flex flex-col gap-1 flex-1 min-w-0",
                ),
                Div(
                    Label("Injection hour", cls="text-xs text-gray-600"),
                    Div(
                        Input(
                            type="time",
                            name="shot_hour",
                            value=shot_hour,
                            aria_label="Injection hour",
                            cls="web_input border border-white rounded-lg px-2 py-1 text-base",
                        ),
                        Button(
                            "Date",
                            type="button",
                            cls="web_button px-2 py-1 text-xs",
                            onclick=(
                                f"const el=document.getElementById('settings_shot_date_wrap_{injection.id}');"
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
                            value=shot_date,
                            aria_label="Injection date",
                            cls="web_input border border-white rounded-lg px-2 py-1 text-base",
                        ),
                        id=f"settings_shot_date_wrap_{injection.id}",
                        cls="hidden flex-col gap-1 mt-1",
                    ),
                    cls="flex flex-col gap-1 flex-1 min-w-0",
                ),
                cls="grid grid-cols-2 gap-3",
            ),
            Div(
                Label(
                    "Dose (U)",
                    Span(
                        " - optional",
                        data_settings_dose_optional="true",
                        cls="hidden" if injection.insulin_type is InsulinType.BASAL else "",
                    ),
                    cls="text-xs text-gray-600",
                ),
                Input(
                    type="text",
                    name="units",
                    inputmode="decimal",
                    pattern="[0-9]+([\\.,][0-9]+)?",
                    placeholder="e.g. 8.5",
                    value=(f"{float(units):g}" if units is not None else ""),
                    cls="web_input border border-white rounded-lg px-2 py-1 text-sm",
                ),
                cls="flex flex-col gap-1",
            ),
            Div(
                Img(
                    src=image,
                    alt="Injection zones map",
                    cls="w-full max-h-[38vh] md:max-h-[46vh] object-contain rounded-2xl border border-gray-200 bg-white",
                    data_settings_injection_image="true",
                ),
                cls="w-full",
            ),
            Div(*zone_buttons, cls="flex flex-wrap gap-2"),
            Input(type="hidden", name="zone", value=(selected_zone.value if selected_zone else ""), data_settings_injection_zone_input="true"),
            # Form errors land here (code_conventions.md §9.5); the pop-up closes
            # only on success, with `injectionUpdated` (static/js/insulin_pens.js).
            Div(id=f"settings_injection_error_{injection.id}"),
            Div(
                modal_confirm_button(
                    "OK",
                    cls="ml-auto",
                    hx_post=f"/settings/injections/{injection.id}/update",
                    hx_include="closest form",
                    hx_target=f"#settings_injection_error_{injection.id}",
                    hx_swap="innerHTML",
                    hx_disabled_elt="this",
                ),
            ),
            cls="flex flex-col gap-3",
        ),
        modal_id=modal_id,
        card_cls="gap-3",
    )


def _injection_row(injection, pens_by_id):
    actions_id = f"settings_injection_actions_{injection.id}"
    insulin_label = "Basal" if injection.insulin_type is InsulinType.BASAL else "Rapid"
    pen = pens_by_id.get(injection.insulin_pen_id)
    if pen is not None:
        insulin_label = f"{insulin_label} · {pen.brand_name}"
    zone_label = injection_zone_label(injection.injection_zone)
    local_dt = to_local(injection.shot_time)
    hour = _format_injection_hour(local_dt) if local_dt else "--:--"
    dose_text = ""
    if injection.units is not None:
        dose_text = f"Dose: {float(injection.units):g} U"

    return Div(
        Div(
            Div(
                P(insulin_label, cls="text-sm font-semibold text-gray-900"),
                P(hour, cls="text-xs text-gray-600"),
                cls="flex items-center justify-between gap-3",
            ),
            Div(
                P(f"Zone: {zone_label}", cls="text-xs text-gray-700"),
                P(dose_text, cls=f"text-xs text-gray-700 {'hidden' if not dose_text else ''}"),
                cls="flex items-center justify-between gap-3",
            ),
            onclick=(
                f"const el=document.getElementById('{actions_id}');"
                "if(el){el.classList.toggle('hidden');}"
            ),
            cls="flex flex-col gap-1 cursor-pointer",
        ),
        Div(
            Button(
                "Edit",
                type="button",
                cls="web_button px-3 py-1 text-xs",
                onclick=f"event.stopPropagation();{open_modal_js(f'settings_injection_edit_{injection.id}')}",
            ),
            Button(
                "Delete",
                type="button",
                cls="web_button px-3 py-1 text-xs text-white",
                style="background-color:#b91c1c;border-color:#b91c1c;",
                onclick=f"event.stopPropagation();{open_modal_js(f'settings_injection_delete_{injection.id}')}",
            ),
            id=actions_id,
            cls="hidden flex items-center justify-end gap-2 pt-2",
        ),
        cls="web_container food_entry flex flex-col gap-1",
    )


def _injection_row_modals(injection, open_pens, pens_by_id):
    return Div(
        _injection_edit_modal(injection, open_pens, pens_by_id),
        _injection_delete_modal(injection),
    )


def _injection_day_header(day_text: str):
    return P(day_text, cls="text-xs font-semibold uppercase tracking-wide text-gray-600 pt-2")


def injections_settings_chunk(
    rows,
    offset: int,
    page_size: int,
    previous_day=None,
    open_pens=(),
    pens_by_id=None,
):
    """`open_pens` feed the pen selector of each edit pop-up and `pens_by_id` has the
    pen of each row, open or closed (frontend_conventions.md §9.9)."""
    pens_by_id = pens_by_id or {}
    if not rows and offset == 0:
        return Div(P("No injections found.", cls="text-sm text-gray-600"), cls="w-full")

    items = []
    modals = []
    current_day = previous_day
    for injection in rows:
        local_dt = to_local(injection.shot_time)
        if not local_dt:
            continue
        day_value = local_dt.date()
        if current_day != day_value:
            items.append(_injection_day_header(_format_injection_day(local_dt)))
            current_day = day_value
        items.append(_injection_row(injection, pens_by_id))
        modals.append(_injection_row_modals(injection, open_pens, pens_by_id))

    has_more = len(rows) >= page_size
    next_offset = offset + len(rows)
    if has_more:
        items.append(
            Div(
                Button(
                    "Load more",
                    type="button",
                    cls="web_button px-4 py-2 text-sm",
                    hx_get=f"/settings/injections/list?offset={next_offset}",
                    hx_target="#settings-injections-more",
                    hx_swap="outerHTML",
                ),
                id="settings-injections-more",
                cls="w-full flex justify-center pt-2",
            )
        )
    else:
        items.append(Div(id="settings-injections-more", cls="w-full"))

    return Div(
        Div(*items, cls="flex flex-col gap-2 w-full"),
        Div(*modals),
        cls="w-full",
    )


def injections_settings_page(first_chunk):
    return Div(
        Div(
            Button(
                "Back",
                type="button",
                cls="web_button self-start px-3 py-1.5 text-sm",
                onclick=back_js("/settings"),
            ),
            cls="w-full flex justify-start",
        ),
        H1("Injection log", cls="text-xl font-bold"),
        Div(first_chunk, id="settings-injections-list", cls="w-full"),
        cls="flex flex-col items-center gap-4 md:mt-7 lg:mt-7 mt-2 md:w-md lg:w-md w-xs w-full mx-auto md:mb-28 lg:mb-28 mb-24",
        data_hide_cart="true",
    )
