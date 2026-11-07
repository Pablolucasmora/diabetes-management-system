"""Settings `Insulin pens`: a menu that leads to the open pens and to the brands, each
on its own page (frontend_conventions.md §9.9, contract in code_conventions.md §9.5).
static/js/insulin_pens.js repaints #insulin_pens_body or #insulin_brands_body on
`insulinChanged` and `penCreated`."""

from fasthtml.common import *

from DayBetes_food.components.insulin_pen import (
    INSULIN_TYPE_LABELS,
    PEN_FORMAT_LABELS,
    InsulinPenModal,
    open_pen_modal_js,
    pen_remaining_text,
    units_text,
)
from DayBetes_food.components.modal import (
    ConfirmActionModal,
    ModalLayer,
    close_modal_js,
    modal_confirm_button,
    modal_secondary_button,
    open_modal_js,
)
from DayBetes_food.components.navigation import back_js
from DayBetes_food.domain.constants import InsulinType, PenFormat
from DayBetes_food.domain.insulin_pen import DEFAULT_IN_USE_DAYS, DEFAULT_PEN_UNITS, INSULIN_BRAND_NAME_MAX_LENGTH
from DayBetes_food.time_utils import to_local

_FIELD_CLS = "web_input border border-white rounded-lg px-2 py-1 text-base"
_SMALL_BUTTON_CLS = "web_button px-3 py-1 text-xs"


def _labelled(label: str, control):
    return Div(Label(label, cls="text-xs text-gray-600"), control, cls="flex flex-col gap-1")


def _days(n: int) -> str:
    return f"{n} day{'s' if n != 1 else ''}"


def _pen_days_line(pen, now):
    days_in = max((now - pen.opened_at).days, 0)
    if pen.is_expired(now):
        ago = (now - pen.expires_at).days
        return f"{_days(days_in)} in · expired {'today' if ago == 0 else _days(ago) + ' ago'}", "text-danger"
    colour = "text-warning" if pen.few_days_left(now) else "text-gray-700"
    return f"{_days(days_in)} in · {_days(pen.days_left(now))} left", colour


def _pen_edit_modal(pen):
    modal_id = f"insulin_pen_edit_{pen.id}"
    expires_local = to_local(pen.expires_at)
    return ModalLayer(
        P("Edit pen", cls="text-lg font-semibold"),
        P(f"{pen.brand_name} · {INSULIN_TYPE_LABELS[pen.insulin_type]}", cls="text-sm text-gray-600 -mt-2"),
        Form(
            Div(
                _labelled(
                    "Format",
                    Select(
                        *[
                            Option(PEN_FORMAT_LABELS[f], value=f.value, selected=f is pen.format)
                            for f in PenFormat
                        ],
                        name="format",
                        cls=_FIELD_CLS,
                    ),
                ),
                _labelled(
                    "Expires on",
                    Input(type="date", name="expires_date", value=expires_local.strftime("%Y-%m-%d"), cls=_FIELD_CLS),
                ),
                cls="grid grid-cols-2 gap-3",
            ),
            _labelled(
                "Units in the full pen",
                Input(
                    type="text",
                    inputmode="decimal",
                    name="capacity_units",
                    value=units_text(pen.capacity_units),
                    cls=_FIELD_CLS,
                ),
            ),
            Div(id=f"insulin_pen_edit_error_{pen.id}"),
            Div(
                modal_secondary_button("Cancel", onclick=close_modal_js(modal_id)),
                modal_confirm_button(
                    "Save",
                    hx_post=f"/insulin/pens/{pen.id}/update",
                    hx_include="closest form",
                    hx_target=f"#insulin_pen_edit_error_{pen.id}",
                    hx_swap="innerHTML",
                ),
                cls="flex items-center justify-end gap-2",
            ),
            cls="flex flex-col gap-3",
        ),
        modal_id=modal_id,
        card_cls="gap-3",
    )


def _pen_discard_modal(pen):
    modal_id = f"insulin_pen_discard_{pen.id}"
    return ConfirmActionModal(
        modal_id=modal_id,
        title="Discard pen",
        question=f"Stop using this {PEN_FORMAT_LABELS[pen.format].lower()} of {pen.brand_name}?",
        yes_button=modal_confirm_button(
            "Discard",
            danger=True,
            hx_post=f"/insulin/pens/{pen.id}/discard",
            hx_swap="none",
        ),
    )


def _pen_row(pen, now):
    actions_id = f"insulin_pen_actions_{pen.id}"
    expired = pen.is_expired(now)
    days_text, days_cls = _pen_days_line(pen, now)
    units_cls = "text-warning" if pen.few_units_left else "text-gray-700"
    discard_button = Button(
        "Discard",
        type="button",
        cls=f"{_SMALL_BUTTON_CLS} text-danger",
        onclick=f"event.stopPropagation();{open_modal_js(f'insulin_pen_discard_{pen.id}')}",
    )
    return Div(
        Div(
            Div(
                P(
                    f"{pen.brand_name} · {PEN_FORMAT_LABELS[pen.format]}",
                    cls="text-sm font-semibold text-gray-900 truncate",
                ),
                Span("Expired", cls="text-[10px] font-semibold text-danger") if expired else
                Span(INSULIN_TYPE_LABELS[pen.insulin_type], cls="text-[11px] text-gray-500"),
                cls="flex items-center justify-between gap-3",
            ),
            Div(
                P(days_text, cls=f"text-xs {days_cls}"),
                P(pen_remaining_text(pen), cls=f"text-xs tabular-nums {units_cls}"),
                cls="flex items-center justify-between gap-3",
            ),
            Div(discard_button, cls="flex justify-end pt-1") if expired else "",
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
                cls=_SMALL_BUTTON_CLS,
                onclick=f"event.stopPropagation();{open_modal_js(f'insulin_pen_edit_{pen.id}')}",
            ),
            "" if expired else discard_button,
            id=actions_id,
            cls="hidden flex items-center justify-end gap-2 pt-2",
        ),
        cls="web_container food_entry flex flex-col gap-1",
    )


def _brand_form_fields(brand=None):
    """Fields of a new or edited brand. A brand with pens keeps its type (§8.4):
    the select is disabled and a hidden input sends the current value."""
    locked_type = brand is not None and brand.pen_count > 0
    type_options = []
    if brand is None:
        type_options.append(Option("Choose type", value="", selected=True, disabled=True))
    type_options += [
        Option(INSULIN_TYPE_LABELS[t], value=t.value, selected=brand is not None and t is brand.insulin_type)
        for t in InsulinType
    ]
    return (
        _labelled(
            "Name",
            Input(
                type="text",
                name="name",
                maxlength=str(INSULIN_BRAND_NAME_MAX_LENGTH),
                value=brand.name if brand else "",
                placeholder="e.g. NovoRapid",
                cls=_FIELD_CLS,
            ),
        ),
        Div(
            _labelled(
                "Type",
                Select(
                    *type_options,
                    name="insulin_type" if not locked_type else "insulin_type_shown",
                    disabled=locked_type,
                    title="It has pens: its type cannot change." if locked_type else None,
                    cls=_FIELD_CLS,
                ),
            ),
            Input(type="hidden", name="insulin_type", value=brand.insulin_type.value) if locked_type else "",
            _labelled(
                "Days once opened",
                Input(
                    type="text",
                    inputmode="numeric",
                    name="in_use_days",
                    value=str(brand.in_use_days if brand else DEFAULT_IN_USE_DAYS),
                    cls=_FIELD_CLS,
                ),
            ),
            _labelled(
                "Units per pen",
                Input(
                    type="text",
                    inputmode="decimal",
                    name="pen_units",
                    value=units_text(brand.pen_units if brand else DEFAULT_PEN_UNITS),
                    cls=_FIELD_CLS,
                ),
            ),
            cls="grid grid-cols-3 gap-2",
        ),
    )


def _brand_modal(modal_id: str, title: str, error_id: str, post_url: str, brand=None):
    return ModalLayer(
        P(title, cls="text-lg font-semibold"),
        Form(
            *_brand_form_fields(brand),
            Div(id=error_id),
            Div(
                modal_secondary_button("Cancel", onclick=close_modal_js(modal_id)),
                modal_confirm_button(
                    "Save",
                    hx_post=post_url,
                    hx_include="closest form",
                    hx_target=f"#{error_id}",
                    hx_swap="innerHTML",
                ),
                cls="flex items-center justify-end gap-2",
            ),
            cls="flex flex-col gap-3",
        ),
        modal_id=modal_id,
        card_cls="gap-3",
    )


def _brand_delete_modal(brand):
    modal_id = f"insulin_brand_delete_{brand.id}"
    question = (
        f"{brand.name} has pens: it will no longer be offered for new pens, and its pens stay as they are."
        if brand.pen_count
        else f"Delete {brand.name}?"
    )
    return ConfirmActionModal(
        modal_id=modal_id,
        title="Delete brand",
        question=question,
        yes_button=modal_confirm_button(
            "Delete",
            danger=True,
            hx_post=f"/insulin/brands/{brand.id}/delete",
            hx_swap="none",
        ),
    )


def _brand_row(brand):
    actions_id = f"insulin_brand_actions_{brand.id}"
    return Div(
        Div(
            P(brand.name, cls="text-sm font-semibold text-gray-900 truncate"),
            P(
                f"{INSULIN_TYPE_LABELS[brand.insulin_type]} · {_days(brand.in_use_days)} · "
                f"{units_text(brand.pen_units)} U per pen",
                cls="text-xs text-gray-700",
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
                cls=_SMALL_BUTTON_CLS,
                onclick=f"event.stopPropagation();{open_modal_js(f'insulin_brand_edit_{brand.id}')}",
            ),
            Button(
                "Delete",
                type="button",
                cls=f"{_SMALL_BUTTON_CLS} text-danger",
                onclick=f"event.stopPropagation();{open_modal_js(f'insulin_brand_delete_{brand.id}')}",
            ),
            id=actions_id,
            cls="hidden flex items-center justify-end gap-2 pt-2",
        ),
        cls="web_container food_entry flex flex-col gap-1",
    )


def _subpage(title: str, back_to: str, *content, data_attrs=None):
    """A settings sub-page: Back, title and its content (same frame as the injection log)."""
    return Div(
        Div(
            Button(
                "Back",
                type="button",
                cls="web_button self-start px-3 py-1.5 text-sm",
                onclick=back_js(back_to),
            ),
            cls="w-full flex justify-start",
        ),
        H1(title, cls="text-xl font-bold"),
        *content,
        cls="flex flex-col items-center gap-4 md:mt-7 lg:mt-7 mt-2 md:w-md lg:w-md w-xs w-full mx-auto md:mb-28 lg:mb-28 mb-24",
        data_hide_cart="true",
    )


def _menu_button(label: str, url: str):
    return Button(
        label,
        type="button",
        cls="web_button food_entry flex items-center justify-between cursor-pointer text-left",
        hx_get=url,
        hx_target="#main_content",
        hx_swap="innerHTML",
        hx_push_url="true",
    )


def insulin_menu_page():
    """`Insulin pens` of settings: a menu with the same design as the settings
    page, which leads to the pens and to the brands (frontend_conventions.md §9.9)."""
    return Div(
        Div(
            Button(
                "Back",
                type="button",
                cls="web_button self-start px-3 py-1.5 text-sm",
                onclick=back_js("/settings"),
            ),
            H1("Insulin pens", cls="text-xl font-bold text-center"),
            P("The pens you are using and the insulins they hold.", cls="text-sm text-gray-600 text-center"),
            _menu_button("Pens", "/settings/insulin/pens"),
            _menu_button("Brands", "/settings/insulin/brands"),
            cls="web_container p-6 flex flex-col items-center gap-3",
        ),
        cls="flex flex-col items-center justify-center gap-6 md:mt-7 lg:mt-7 mt-2",
        data_hide_cart="true",
    )


def insulin_pens_body(pens, brands, now, today_iso: str):
    """Open pens and every pop-up they use; repainted whole after a change. The
    brands feed the pop-up of a new pen."""
    rows = [_pen_row(pen, now) for pen in pens] or [P("No pens in use.", cls="text-sm text-gray-600")]
    return Div(
        *rows,
        Button("New pen", type="button", cls="web_button w-full py-2 text-sm", onclick=open_pen_modal_js()),
        Div(
            *[_pen_edit_modal(pen) for pen in pens],
            *[_pen_discard_modal(pen) for pen in pens],
            InsulinPenModal(brands, today_iso),
        ),
        cls="flex flex-col gap-2 w-full",
    )


def insulin_brands_body(brands):
    """Active brands and every pop-up they use; repainted whole after a change."""
    rows = [_brand_row(brand) for brand in brands] or [
        P("No brands yet. Add the insulins you use.", cls="text-sm text-gray-600")
    ]
    return Div(
        *rows,
        Button(
            "New brand",
            type="button",
            cls="web_button w-full py-2 text-sm",
            onclick=open_modal_js("insulin_brand_new"),
        ),
        Div(
            *[
                _brand_modal(
                    f"insulin_brand_edit_{brand.id}",
                    "Edit brand",
                    f"insulin_brand_edit_error_{brand.id}",
                    f"/insulin/brands/{brand.id}/update",
                    brand,
                )
                for brand in brands
            ],
            *[_brand_delete_modal(brand) for brand in brands],
            _brand_modal("insulin_brand_new", "New brand", "insulin_brand_form_error", "/insulin/brands"),
        ),
        cls="flex flex-col gap-2 w-full",
    )


def insulin_pens_page(pens, brands, now, today_iso: str):
    return _subpage(
        "Pens",
        "/settings/insulin",
        Div(insulin_pens_body(pens, brands, now, today_iso), id="insulin_pens_body", cls="w-full"),
    )


def insulin_brands_page(brands):
    return _subpage(
        "Brands",
        "/settings/insulin",
        Div(insulin_brands_body(brands), id="insulin_brands_body", cls="w-full"),
    )
