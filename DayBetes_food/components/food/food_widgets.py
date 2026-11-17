"""Form controls and small pieces shared by the Food pages: labels with help, inputs, selects and searchable autocompletes (frontend_conventions.md §2, §9.1)."""

import json
from fasthtml.common import *
from DayBetes_food.components.injection_zone import asset_busted
from DayBetes_food.components.cart.cart_shared import CHECKBOX_CLS
from DayBetes_food.components.navigation import back_js
from DayBetes_food.components.food.food_shared import (
    AMOUNT_METHOD_LABELS,
    FORM_FIELD_CLS,
    MACROS_SOURCE_LABELS,
)
from DayBetes_food.domain.constants import (
    AmountMethod,
    GlycemicIndex,
    MacrosSource,
    NutrientEntryMode,
)
from DayBetes_food.domain.nutrition import SMART_MACROS_MAX_LENGTH


# Presentation labels of the manual dish fields (§3.6: labels live in components).
GLYCEMIC_INDEX_LABELS = {
    GlycemicIndex.NONE: "No absorption",
    GlycemicIndex.LOW: "Slow",
    GlycemicIndex.MEDIUM: "Medium",
    GlycemicIndex.HIGH: "Fast",
}
# Declared confidence, ordinal 0-2 (measurement §6.10).
CONFIDENCE_LABELS = {0: "Not sure", 1: "More or less", 2: "Quite sure"}


FILTER_ITEM_CLS = """
    px-3 py-2
    w-full
    text-xs font-medium
    rounded-full
    transition-all duration-200
    cursor-pointer
    border border-line
"""


def _help_icon(help_text: str):
    return Button(
        "?",
        type="button",
        title=help_text,
        onclick=f"alert({help_text!r});",
        cls="""
            web_button rounded-full
            h-4 w-4 md:h-5 md:w-5
            text-[10px] md:text-xs
            p-0 leading-none
            flex items-center justify-center
            shadow-none
        """,
    )


def _label_with_help(text: str, help_text: str, for_id: str = "", label_attrs: dict | None = None):
    return Div(
        Label(
            text,
            cls="text-xs text-gray-700",
            **({"for": for_id} if for_id else {}),
            **(label_attrs or {}),
        ),
        _help_icon(help_text),
        cls="flex items-center gap-1",
    )


def on_after(target="this", reload_page=True):
    reload_snippet = "setTimeout(function() { location.reload(); }, 600);" if reload_page else ""
    return {"hx-on:htmx:after-request": f"""
    var btn = {target if target == "this" else f"document.getElementById('{target}')"};
    if(!btn) return;
    if(event.detail.successful) {{
        btn.style.backgroundColor = 'rgb(74, 222, 128)';
    }} else {{
        btn.style.backgroundColor = 'rgb(248, 113, 113)';
    }}
    setTimeout(function() {{ btn.style.backgroundColor = ''; }}, 300);
    {reload_snippet}
"""}


def _food_back_button(label: str = "Back"):
    return Button(
        label,
        type="button",
        cls="web_button self-start px-3 py-1.5 text-sm",
        onclick=back_js("/food"),
    )


def _labeled_input(
    label: str,
    name: str,
    typ: str = "text",
    placeholder: str = "",
    help_text: str = "",
    step: str = "",
    value: str | None = None,
    select_on_click: bool = True,
    input_style: str = "",
    inputmode: str | None = None,
    min_value=None,
    max_value=None,
    maxlength=None,
    pattern: str | None = None,
    label_attrs: dict | None = None,
    input_attrs: dict | None = None,
):
    help_value = help_text or f"What to enter in {label}"
    input_id = f"field_{name}"
    attrs = {}
    if select_on_click:
        attrs["onclick"] = "this.select()"
    if step:
        attrs["step"] = step
    if value is not None:
        attrs["value"] = value
    if inputmode:
        attrs["inputmode"] = inputmode
    if min_value is not None:
        attrs["min"] = str(min_value)
    if max_value is not None:
        attrs["max"] = str(max_value)
    if maxlength is not None:
        attrs["maxlength"] = str(maxlength)
    if pattern:
        attrs["pattern"] = pattern
    attrs.update(input_attrs or {})
    return Div(
        _label_with_help(label, help_value, for_id=input_id, label_attrs=label_attrs),
        Input(
            type=typ,
            id=input_id,
            name=name,
            placeholder=placeholder,
            cls=FORM_FIELD_CLS,
            style=input_style,
            **attrs,
        ),
        cls="flex flex-col gap-1",
    )



def _decimal_input(
    label: str,
    name: str,
    *,
    help_text: str = "",
    value: str | None = None,
    label_attrs: dict | None = None,
    input_attrs: dict | None = None,
):
    """A field that admits decimals (frontend_conventions.md §4): a text field
    with the decimal keypad, never type="number", which rejects the comma the
    keypad types in Spanish. It takes no step, min or max: they only apply to
    type="number", and the server checks the range."""
    return _labeled_input(
        label,
        name,
        "text",
        help_text=help_text,
        value=value,
        inputmode="decimal",
        label_attrs=label_attrs,
        input_attrs=input_attrs,
    )


def _searchable_autocomplete_input(
    label: str,
    name: str,
    options: list[str] | None = None,
    help_text: str = "",
    placeholder: str = "",
    allow_add: bool = True,
    value: str | None = None,
    case_mode: str = "lower",
    maxlength=None,
    added: bool = False,
):
    normalized_options = sorted({(opt or "").strip() for opt in (options or []) if (opt or "").strip()})
    options_json = json.dumps(normalized_options)
    placeholder_value = placeholder or f"Type {label.lower()}"
    help_value = help_text or f"Search and select {label.lower()}."
    input_id = f"field_{name}"
    return Div(
        _label_with_help(label, help_value, for_id=input_id),
        Div(
            (Input(type="hidden", name=f"{name}__added", value="1" if added else "0", data_searchable_added_flag="true") if allow_add else None),
            Input(
                type="text",
                id=input_id,
                name=name,
                data_searchable_input="true",
                placeholder=placeholder_value,
                autocomplete="off",
                cls=FORM_FIELD_CLS,
                onclick="this.select()",
                **({"value": value} if value is not None else {}),
                **({"maxlength": str(maxlength)} if maxlength is not None else {}),
            ),
            Div(
                data_searchable_suggestions="true",
                cls="""
                    absolute left-0 right-0 top-full mt-1 z-[70]
                    rounded-md border border-gray-200
                    bg-white opacity-100 shadow-lg
                    overflow-hidden
                """,
                style="display:none;background:#fff;backdrop-filter:none;z-index:70;",
            ),
            data_searchable_autocomplete="true",
            data_searchable_options=options_json,
            data_searchable_allow_add="1" if allow_add else "0",
            data_searchable_case_mode=case_mode,
            cls="relative",
        ),
        cls="flex flex-col gap-1",
    )


def _searchable_compact_input(
    name: str,
    options: list[str] | None = None,
    value: str | None = None,
    placeholder: str = "",
    allow_add: bool = False,
    autosave: bool = False,
):
    normalized_options = sorted({(opt or "").strip() for opt in (options or []) if (opt or "").strip()})
    options_json = json.dumps(normalized_options)
    return Div(
        (Input(type="hidden", name=f"{name}__added", value="0", data_searchable_added_flag="true") if allow_add else None),
        Input(
            type="text",
            name=name,
            data_searchable_input="true",
            placeholder=placeholder or "Search",
            autocomplete="off",
            cls=f"{FORM_FIELD_CLS} min-w-0",
            **(
                {
                    "oninput": (
                        "if(!this.form) return;"
                        "clearTimeout(this._dbAutoSaveTimer);"
                        "this._dbAutoSaveTimer=setTimeout(()=>{if(this.form) htmx.trigger(this.form,'submit');},350);"
                    ),
                    "onblur": "if(this.form) htmx.trigger(this.form,'submit');",
                    "onchange": "if(this.form) htmx.trigger(this.form,'submit');",
                }
                if autosave
                else {}
            ),
            **({"value": value} if value is not None else {}),
        ),
        Div(
            data_searchable_suggestions="true",
            cls="""
                absolute left-0 right-0 top-full mt-1 z-[200]
                rounded-md border border-gray-200
                bg-white opacity-100 shadow-lg
                overflow-hidden
            """,
            style="display:none;background:#fff;backdrop-filter:none;z-index:200;",
        ),
        data_searchable_autocomplete="true",
        data_searchable_options=options_json,
        data_searchable_allow_add="1" if allow_add else "0",
        cls="relative w-full min-w-0",
    )


def _brand_autocomplete_input(brand_options: list[str] | None = None, value: str | None = None, added: bool = False):
    return _searchable_autocomplete_input(
        label="Brand",
        name="brand",
        options=brand_options,
        help_text="Brand or manufacturer name.",
        placeholder="Type brand",
        allow_add=True,
        value=value,
        case_mode="title",
        added=added,
    )


def _searchable_autocomplete_bootstrap_script():
    """The script of the searchable inputs (static/js/searchable_autocomplete.js).
    It guards against a second run, so a page can include it more than once."""
    return Script(src=asset_busted("/js/searchable_autocomplete.js"))


def _labeled_select(
    label: str,
    name: str,
    options: list[str],
    help_text: str = "",
    selected_value: str = "",
    labels: dict | None = None,
):
    """With `labels`, the visible text comes from the map and the `value` stays
    the code. The first option "-" is selected when nothing is chosen (§7.14:
    an explicit "not chosen" state)."""
    help_value = help_text or f"What to select in {label}"
    select_id = f"field_{name}"
    return Div(
        _label_with_help(label, help_value, for_id=select_id),
        Select(
            Option("-", value="", selected=(selected_value == "")),
            *[
                Option((labels or {}).get(opt, opt), value=opt, selected=(opt == selected_value))
                for opt in options
            ],
            id=select_id,
            name=name,
            cls=FORM_FIELD_CLS,
        ),
        cls="flex flex-col gap-1",
    )


def _confidence_select(label: str, name: str, selected: int | None, help_text: str):
    """Declared confidence 0-2 as three options plus "not declared" (measurement §6.10)."""
    return _labeled_select(
        label,
        name,
        [str(value) for value in CONFIDENCE_LABELS],
        help_text=help_text,
        selected_value="" if selected is None else str(selected),
        labels={str(value): text for value, text in CONFIDENCE_LABELS.items()},
    )


def _macros_source_select(selected: str | None):
    """U1 (study §6.3): where the food's macros come from. Portions read it live
    (measurement §6.11)."""
    return _labeled_select(
        "Macros from",
        "macros_source",
        [member.value for member in MacrosSource],
        help_text="Where these macros come from: the label, the menu, a table, an estimate...",
        selected_value=selected or "",
        labels={member.value: text for member, text in MACROS_SOURCE_LABELS.items()},
    )


def _amount_method_default_select(selected: str | None):
    """U2 (study §6.3): copied to every new portion; each portion can change it
    (measurement §6.11)."""
    return _labeled_select(
        "Amount usually from",
        "default_amount_method",
        [member.value for member in AmountMethod],
        help_text="Copied to every new portion: how you usually get its amount (e.g. the 60 g of a can).",
        selected_value=selected or "",
        labels={member.value: text for member, text in AMOUNT_METHOD_LABELS.items()},
    )


def _macros_confidence_select(selected: int | None):
    return _confidence_select(
        "Macros confidence",
        "macros_confidence",
        selected,
        "How sure you are about the macros you typed.",
    )


def _glycemic_index_select(selected: str | None):
    return _labeled_select(
        "Glycemic index",
        "glycemic_index",
        [member.value for member in GlycemicIndex],
        help_text="Absorption speed you expect from this dish (measurement §5.5). Not a measured GI.",
        selected_value=selected or "",
        labels={member.value: text for member, text in GLYCEMIC_INDEX_LABELS.items()},
    )


def _nutrient_mode_select(prefix: str):
    """Per 100 g (default, measurement §5.4) or total of one serving. Transport
    only: the mode is never stored; the server converts the totals."""
    select_id = f"{prefix}_nutrient_mode"
    return Div(
        _label_with_help(
            "Nutrients entered",
            "Per 100 g, or as the total of one serving. With totals, the serving weight is required.",
            for_id=select_id,
        ),
        Select(
            Option("Per 100 g", value=NutrientEntryMode.PER_100G.value, selected=True),
            Option("Total of one serving", value=NutrientEntryMode.PORTION_TOTAL.value),
            id=select_id,
            name="nutrient_mode",
            data_manual_mode="true",
            onchange="dbManualModeChange(this)",
            cls=FORM_FIELD_CLS,
        ),
        P("", data_manual_mode_hint="true", cls="text-[11px] text-amber-700 min-h-0"),
        cls="flex flex-col gap-1",
    )


def _favorite_checkbox(name: str = "favorite", checked: bool = True, centered: bool = False):
    checkbox_id = f"field_{name}"
    return Div(
        Label(
            Input(
                type="checkbox",
                id=checkbox_id,
                name=name,
                value="true",
                checked=checked,
                cls=CHECKBOX_CLS,
            ),
            Span(
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
            ),
            cls="flex items-center cursor-pointer relative h-5 w-5",
        ),
        Label("Favorite", cls="text-xs text-gray-700 cursor-pointer", **{"for": checkbox_id}),
        _help_icon("Mark as favorite so it appears highlighted and in Favs filter."),
        cls=(
            "flex items-center justify-center gap-2 col-span-1 md:col-span-2"
            if centered
            else "flex items-center justify-end gap-2 col-span-1 md:col-span-2"
        ),
    )


def _smart_macros_block(
    prefix: str,
    prefill: dict | None = None,
    *,
    label: str = "Smart macros (per 100 g)",
    label_total: str | None = None,
):
    """With `label_total`, the label follows the nutrient mode select of the
    form (static/js/manual_intake_form.js)."""
    prefill = prefill or {}
    def _smart_prefill_text():
        calories = prefill.get("calories_100g")
        carbs = prefill.get("carbs_100g")
        sugars = prefill.get("sugars_100g")
        proteins = prefill.get("proteins_100g")
        fats = prefill.get("fats_100g")
        saturated = prefill.get("saturated_100g")
        fiber = prefill.get("fiber_100g")
        parts = []
        if calories not in (None, ""):
            parts.append(f"{calories}kcal")
        if carbs not in (None, ""):
            parts.append(f"{carbs}hc")
        if sugars not in (None, ""):
            parts.append(f"{sugars}az")
        if proteins not in (None, ""):
            parts.append(f"{proteins}prot")
        if fats not in (None, ""):
            parts.append(f"{fats}grasas")
        if saturated not in (None, ""):
            parts.append(f"{saturated}sat")
        if fiber not in (None, ""):
            parts.append(f"{fiber}fibra")
        return " ".join(parts)
    input_id = f"{prefix}_smart_macros_input"
    output_id = f"{prefix}_smart_macros_output"
    mode_attrs = (
        {"data_mode_label": "true", "data_label_per100": label, "data_label_total": label_total}
        if label_total
        else {}
    )
    return Div(
        _label_with_help(
            label,
            (
                "Write each value as a number followed by its macro. Examples: "
                "'120kcal 30hc 12az 20prot 10 grasas 3 sat 5 fibra', '30g carbs 20g proteins'. "
                "Synonyms accepted: hc/ch/hidratos/carbs, prot/proteina/proteins, grasas/gr/fats, "
                "sat/saturadas/st/gs, fibra/fb/fiber, az/azucar/sugars, kcal/cal/calorias."
            ),
            for_id=input_id,
            label_attrs=mode_attrs,
        ),
        Input(
            type="text",
            id=input_id,
            name=f"{prefix}_smart_macros_raw",
            placeholder="e.g. 120kcal 30hc 12az 20prot 10 grasas 3 sat 5 fibra",
            maxlength=SMART_MACROS_MAX_LENGTH,
            data_smart_macros="true",
            data_smart_macros_output=f"#{output_id}",
            data_smart_macros_prefix=prefix,
            oninput="dbSmartMacrosSync(this)",
            onchange="dbSmartMacrosSync(this)",
            cls=FORM_FIELD_CLS,
            value=_smart_prefill_text(),
        ),
        Div(
            "Imported from barcode data." if _smart_prefill_text() else "Type macros to preview what is detected.",
            id=output_id,
            cls="text-xs text-gray-700 min-h-5",
        ),
        cls="flex flex-col gap-1 col-span-1 md:col-span-2",
    )
