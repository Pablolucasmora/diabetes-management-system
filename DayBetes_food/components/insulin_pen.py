"""Shared pieces of insulin pens (frontend_conventions.md §9.9): the label of a pen,
its selector and the pop-up that opens a new one. static/js/insulin_pens.js
drives the `+ New pen` option and the `penCreated` event."""

from fasthtml.common import *

from DayBetes_food.components.modal import ModalLayer, close_modal_js, modal_confirm_button, modal_secondary_button
from DayBetes_food.domain.constants import InsulinType, PenFormat
from DayBetes_food.domain.insulin_pen import (
    DEFAULT_IN_USE_DAYS,
    DEFAULT_PEN_UNITS,
    INSULIN_BRAND_NAME_MAX_LENGTH,
)

INSULIN_PEN_MODAL_ID = "insulin_pen_modal"
NEW_OPTION_VALUE = "new"

INSULIN_TYPE_LABELS = {InsulinType.RAPID: "Rapid", InsulinType.BASAL: "Basal"}
PEN_FORMAT_LABELS = {PenFormat.PREFILLED_PEN: "Prefilled pen", PenFormat.CARTRIDGE: "Cartridge"}

_FIELD_CLS = "web_input border border-white rounded-lg px-2 py-1 text-base"


def units_text(value: float) -> str:
    return f"{value:g}" if float(value).is_integer() else f"{value:.1f}"


def pen_remaining_text(pen) -> str:
    """`140 U left`, with `≈` when a dose was not recorded (measurement §8.4)."""
    prefix = "≈" if pen.remaining_is_estimate else ""
    return f"{prefix}{units_text(pen.remaining_units)} U left"


def pen_label(pen) -> str:
    """The same label in every selector (frontend §9.9)."""
    return f"{pen.brand_name} · {PEN_FORMAT_LABELS[pen.format]} · {pen_remaining_text(pen)}"


def PenSelect(pens, selected_id: int | None, *, select_id: str, only_type: InsulinType | None = None, **attrs):
    """Open pens plus `+ New pen`; no "no pen" option (§9.9). With nothing chosen,
    a `Choose pen` placeholder, so nothing is shown as chosen that is not (§6)."""
    options = []
    if selected_id is None:
        options.append(Option("Choose pen", value="", selected=True, disabled=True))
    for pen in pens:
        options.append(
            Option(
                pen_label(pen),
                value=str(pen.id),
                selected=pen.id == selected_id,
                data_insulin_type=pen.insulin_type.value,
            )
        )
    options.append(Option("+ New pen", value=NEW_OPTION_VALUE))
    return Select(
        *options,
        id=select_id,
        name="insulin_pen_id",
        aria_label="Insulin pen",
        data_pen_select="true",
        **({"data_pen_type": only_type.value} if only_type else {}),
        **attrs,
    )


def open_pen_modal_js() -> str:
    """Open the pop-up from a button: the new pen is not chosen in any selector."""
    return f"window.__dbPenOpener=null;dbOpenModal('{INSULIN_PEN_MODAL_ID}');"


def _labelled(label: str, control, **attrs):
    return Div(Label(label, cls="text-xs text-gray-600"), control, cls="flex flex-col gap-1", **attrs)


def InsulinPenModal(brands, today_iso: str):
    """Pop-up that opens a pen: brand (or a new one), format and the day it left the
    fridge (frontend §9.9). Brand and format start unchosen (§6)."""
    brand_options = [Option("Choose brand", value="", selected=True, disabled=True)]
    brand_options += [
        Option(f"{brand.name} · {INSULIN_TYPE_LABELS[brand.insulin_type]}", value=str(brand.id)) for brand in brands
    ]
    brand_options.append(Option("+ New brand", value=NEW_OPTION_VALUE))
    new_brand_fields = Div(
        _labelled(
            "Brand name",
            Input(
                type="text",
                name="brand_name",
                maxlength=str(INSULIN_BRAND_NAME_MAX_LENGTH),
                placeholder="e.g. NovoRapid",
                cls=_FIELD_CLS,
            ),
        ),
        Div(
            _labelled(
                "Type",
                Select(
                    Option("Choose type", value="", selected=True, disabled=True),
                    *[Option(INSULIN_TYPE_LABELS[t], value=t.value) for t in InsulinType],
                    name="brand_insulin_type",
                    cls=_FIELD_CLS,
                ),
            ),
            _labelled(
                "Days once opened",
                Input(type="text", inputmode="numeric", name="brand_in_use_days", value=str(DEFAULT_IN_USE_DAYS), cls=_FIELD_CLS),
            ),
            _labelled(
                "Units per pen",
                Input(type="text", inputmode="decimal", name="brand_pen_units", value=f"{DEFAULT_PEN_UNITS:g}", cls=_FIELD_CLS),
            ),
            cls="grid grid-cols-3 gap-2",
        ),
        data_new_brand_fields="true",
        cls="hidden flex flex-col gap-3",
    )
    return ModalLayer(
        P("New pen", cls="text-lg font-semibold"),
        P("Taken out of the fridge to start using it.", cls="text-sm text-gray-600 -mt-2"),
        Form(
            _labelled("Brand", Select(*brand_options, name="insulin_brand_id", data_brand_select="true", cls=_FIELD_CLS)),
            new_brand_fields,
            Div(
                _labelled(
                    "Format",
                    Select(
                        Option("Choose format", value="", selected=True, disabled=True),
                        *[Option(PEN_FORMAT_LABELS[f], value=f.value) for f in PenFormat],
                        name="format",
                        cls=_FIELD_CLS,
                    ),
                ),
                _labelled("Opened on", Input(type="date", name="opened_date", value=today_iso, max=today_iso, cls=_FIELD_CLS)),
                cls="grid grid-cols-2 gap-3",
            ),
            Div(id=f"{INSULIN_PEN_MODAL_ID}_error"),
            Div(
                modal_secondary_button("Cancel", onclick=close_modal_js(INSULIN_PEN_MODAL_ID)),
                modal_confirm_button(
                    "Save",
                    hx_post="/insulin/pens",
                    hx_include="closest form",
                    hx_target=f"#{INSULIN_PEN_MODAL_ID}_error",
                    hx_swap="innerHTML",
                    hx_disabled_elt="this",
                ),
                cls="flex items-center justify-end gap-2",
            ),
            cls="flex flex-col gap-3",
            data_pen_form="true",
        ),
        modal_id=INSULIN_PEN_MODAL_ID,
        card_cls="gap-3",
    )
