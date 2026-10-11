"""Rescue pop-up and the provisional Rescue button (frontend_conventions.md §9.6).

The pop-up is one `ModalLayer` whose body is requested from the server each
time it opens, so the date and time are those of that moment and the form
starts empty. Its lines are painted by the server too: the browser only
shows, hides and removes them, and moves the amount with the − / + buttons
(static/js/rescue.js).
"""

from fasthtml.common import *

from DayBetes_food.components.modal import (
    ModalLayer,
    close_modal_js,
    modal_confirm_button,
    modal_secondary_button,
)
from DayBetes_food.domain.constants import AmountInputUnit

RESCUE_MODAL_ID = "rescue_modal"

# Solid controls: the pop-up card is a solid panel (frontend_conventions.md §8).
_FIELD_CLS = "web_input w-full rounded-lg border border-line px-2 py-1.5 text-sm"
# Native date/time controls share a row (frontend_conventions.md §3).
# iOS gives native date/time controls a wide intrinsic size: without
# appearance-none and a 0 minimum column they overflow the card on a phone.
_NATIVE_FIELD_CLS = (
    "web_input block w-full min-w-0 max-w-full appearance-none overflow-hidden "
    "rounded-lg border border-line px-1.5 py-1.5 text-sm text-center"
)
# Long food names: up to two lines, then an ellipsis; a single long word breaks.
_NAME_CLS = "min-w-0 max-w-full line-clamp-2 break-words font-semibold text-gray-900"
_ICON_BUTTON_CLS = """
    h-7 w-7 shrink-0 rounded-full cursor-pointer
    text-gray-500 hover:bg-line-soft transition-colors
    flex items-center justify-center text-lg leading-none
"""
_STEP_BUTTON_CLS = """
    h-8 w-8 shrink-0 cursor-pointer
    text-base text-gray-700 hover:bg-control transition-colors
    flex items-center justify-center
"""

_SEARCH_ICON = NotStr(
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" aria-hidden="true" class="h-4 w-4">'
    '<circle cx="9" cy="9" r="5.5"/><path d="m13.5 13.5 3.5 3.5"/></svg>'
)


def rescue_open_attrs() -> dict:
    """Attributes of any button that opens the rescue pop-up: it asks the
    server for a fresh form, and static/js/rescue.js opens the layer once the
    form is in, so the pop-up appears complete in a single animation (§9.6)."""
    return {
        "hx_get": "/food/rescue/form",
        "hx_target": "#rescue_modal_body",
        "hx_swap": "innerHTML",
        "hx_push_url": "false",
        "data_skip_page_loading": "true",
    }


def RescueModal():
    """The rescue pop-up layer. Its body arrives with `GET /food/rescue/form`."""
    return ModalLayer(
        Div(id="rescue_modal_body", cls="flex flex-col gap-3"),
        modal_id=RESCUE_MODAL_ID,
        card_cls="gap-3 max-h-[88vh] overflow-y-auto",
    )


def _carbs_meta(carbs_100g: float | None, serving_g: float | None) -> str:
    """Stored carbs of the food, the figure that matters to treat a low. It
    is a fact of the food, not a calculation over the typed amount."""
    if carbs_100g is None:
        return "Carbs unknown"
    if serving_g is not None:
        return f"{carbs_100g * serving_g / 100:.0f} g carbs per serving ({serving_g:.0f} g)"
    return f"{carbs_100g:.0f} g carbs / 100 g"


def RescueForm(date_value: str, time_value: str, options: list[dict]):
    """Body of the pop-up: title, food picker, lines, time and actions. Compact:
    it has to fit a phone screen with the keyboard closed. It arrives with the
    initial food list inside, so it is painted in one go (§9.6)."""
    return Form(
        Div(
            P("Rescue", cls="text-lg font-semibold text-gray-900"),
            Button("×", type="button", aria_label="Close", onclick=close_modal_js(RESCUE_MODAL_ID), cls=_ICON_BUTTON_CLS),
            cls="flex items-center justify-between gap-3",
        ),
        Div(
            Label(
                Span(_SEARCH_ICON, cls="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted"),
                Input(
                    id="rescue_search_input",
                    name="q",
                    type="search",
                    placeholder="Search a food",
                    autocomplete="off",
                    aria_label="Search a food",
                    cls="web_input w-full rounded-lg border border-line pl-8 pr-2 py-1.5 text-sm",
                ),
                cls="relative block",
            ),
            Div(
                RescueOptions(options, searching=False),
                id="rescue_picker_results",
                hx_get="/food/rescue/options",
                hx_trigger="input changed delay:220ms from:#rescue_search_input",
                hx_include="#rescue_search_input",
                hx_swap="innerHTML",
                cls="max-h-[36vh] overflow-y-auto",
            ),
            id="rescue_picker",
            cls="flex flex-col gap-2",
        ),
        Div(id="rescue_lines", cls="flex flex-col gap-2 empty:hidden"),
        Button(
            "+ Add another food",
            type="button",
            id="rescue_add_another",
            cls="hidden self-start text-sm font-medium text-gray-600 hover:text-gray-900 cursor-pointer",
        ),
        Div(
            Input(type="date", name="meal_date", value=date_value, required=True,
                  aria_label="Date", cls=_NATIVE_FIELD_CLS),
            Input(type="time", name="meal_hour", value=time_value, required=True,
                  aria_label="Time", cls=_NATIVE_FIELD_CLS),
            cls="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-2 w-full",
        ),
        Div(id="rescue_form_error", cls="empty:hidden"),
        Div(
            modal_secondary_button("Cancel", onclick=close_modal_js(RESCUE_MODAL_ID), cls="w-full"),
            # The pop-up buttons are type="button": this one submits the form
            # through htmx with requestSubmit().
            modal_confirm_button(
                "Log rescue",
                id="rescue_submit",
                disabled=True,
                onclick="this.form.requestSubmit();",
                cls="w-full disabled:opacity-40 disabled:cursor-not-allowed",
            ),
            cls="grid grid-cols-2 gap-2",
        ),
        hx_post="/food/rescue/log",
        hx_target="#rescue_form_error",
        hx_swap="innerHTML",
        data_skip_page_loading="true",
        id="rescue_form",
        cls="flex flex-col gap-3",
    )


def RescueOptions(rows: list[dict], searching: bool):
    """Foods of the picker: rescue foods first. One compact row per food."""
    if not rows:
        message = (
            "No foods match that search."
            if searching
            else "No rescue foods yet. Search any food: the ones you log show up here next time."
        )
        return P(message, cls="text-xs text-gray-600 px-1 py-1")
    return Div(
        *[
            Button(
                Div(
                    Span(row["name"] or "Unnamed", cls=f"text-sm {_NAME_CLS}"),
                    Span(
                        " · ".join(x for x in (row["subtitle"], _carbs_meta(row["carbs_100g"], row["serving_g"])) if x),
                        cls="block max-w-full text-[11px] text-gray-500 truncate",
                    ),
                    cls="flex flex-col items-start min-w-0 flex-1",
                ),
                Span("+", aria_hidden="true", cls="shrink-0 text-xl leading-none text-gray-600"),
                type="button",
                aria_label=f"Add {row['name']}",
                cls="""
                    w-full text-left px-3 py-1.5 rounded-lg cursor-pointer
                    bg-control border border-line hover:bg-line-soft
                    transition-colors flex items-center justify-between gap-3
                """,
                hx_get=f"/food/rescue/line/{row['entry_type']}/{row['entry_id']}",
                hx_target="#rescue_lines",
                hx_swap="beforeend",
                data_skip_page_loading="true",
                data_rescue_pick=f"{row['entry_type']}:{row['entry_id']}",
            )
            for row in rows
        ],
        cls="flex flex-col gap-1.5",
    )


def _rescue_unit_options(serving_g: float | None):
    """Amount units of a line (AmountInputUnit without `%`). `portion` only
    exists when the food has a serving, and then it is the starting one."""
    options = []
    if serving_g is not None:
        options.append(Option("servings", value=AmountInputUnit.PORTION.value, selected=True))
    options.extend(
        [
            Option("g", value=AmountInputUnit.GRAMS.value, selected=serving_g is None),
            Option("oz", value=AmountInputUnit.OZ.value),
            Option("lb", value=AmountInputUnit.LB.value),
        ]
    )
    return options


def RescueLine(entry_type: str, entry_id: int, name: str, serving_g: float | None):
    """One food of the rescue: name, amount with − / + and unit.

    `data-rescue-serving-g` is presentation only: picking the same food again
    adds one serving's grams to a line in grams (§9.6). The server still
    converts every amount from the food in the database (§7.13)."""
    return Div(
        Input(type="hidden", name="entry_type", value=entry_type),
        Input(type="hidden", name="entry_id", value=str(entry_id)),
        Div(
            Span(name or "Unnamed", cls=f"text-sm flex-1 {_NAME_CLS}"),
            Button("×", type="button", aria_label=f"Remove {name}", data_rescue_remove="true", cls=_ICON_BUTTON_CLS),
            cls="flex items-start justify-between gap-2 min-w-0",
        ),
        Div(
            Div(
                Button("−", type="button", aria_label="Less", data_rescue_step="-1", cls=_STEP_BUTTON_CLS),
                Input(
                    type="number",
                    name="amount_value",
                    value="1" if serving_g is not None else "",
                    min="0",
                    step="any",
                    inputmode="decimal",
                    required=True,
                    placeholder="0",
                    aria_label="Amount",
                    cls="web_input w-full min-w-0 border-0 bg-white text-center text-sm font-semibold py-1 focus:scale-100 focus:shadow-none",
                ),
                Button("+", type="button", aria_label="More", data_rescue_step="1", cls=_STEP_BUTTON_CLS),
                cls="flex items-center rounded-lg border border-line bg-white overflow-hidden",
            ),
            Select(*_rescue_unit_options(serving_g), name="amount_unit", aria_label="Unit", cls=_FIELD_CLS),
            cls="grid grid-cols-[1fr_6.5rem] gap-2",
        ),
        data_rescue_line=f"{entry_type}:{entry_id}",
        data_rescue_serving_g=(f"{serving_g:.3f}" if serving_g is not None else ""),
        cls="rounded-xl bg-control border border-line px-3 py-2 flex flex-col gap-1.5",
    )


def RescueMarkButton(entry_type: str, entry_id: int, is_rescue: bool):
    """Provisional two-state button of the food detail (§9.6): it shows what is
    stored and asks for the opposite."""
    return Button(
        "Rescue food ✓" if is_rescue else "Mark as rescue food",
        type="button",
        aria_pressed="true" if is_rescue else "false",
        cls="web_button w-full px-4 py-2 text-sm rounded-2xl",
        hx_post=f"/food/rescue/mark/{entry_type}/{entry_id}",
        hx_vals='{"rescue": "false"}' if is_rescue else '{"rescue": "true"}',
        hx_target="this",
        hx_swap="outerHTML",
        data_skip_page_loading="true",
        id=f"rescue_mark_{entry_type}_{entry_id}",
    )


def RescueFormError(message: str):
    """Validation message inside the pop-up (code_conventions.md §9.5). Solid,
    not glass: it sits in a solid card (frontend_conventions.md §8)."""
    return P(
        message,
        role="alert",
        cls="text-sm text-danger bg-danger/5 border border-danger/25 rounded-xl px-3 py-2",
    )
