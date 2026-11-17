"""Create and edit pages of a food, a dish, a recipe and a quick add (frontend_conventions.md §9.1)."""

from dataclasses import dataclass
from fasthtml.common import *
from DayBetes_food.components.data_sources import ciqual_attribution, off_attribution
from DayBetes_food.components.injection_zone import asset_busted
from DayBetes_food.components.navigation import back_js
from DayBetes_food.components.food.food_shared import AMOUNT_METHOD_LABELS, FORM_FIELD_CLS
from DayBetes_food.domain.catalog import CATALOG_BARCODE_MAX_LENGTH, CATALOG_NAME_MAX_LENGTH
from DayBetes_food.domain.food import FOOD_SUBTYPE_MAX_LENGTH
from DayBetes_food.components.stats.stats_shared import MEAL_TYPE_LABELS
from DayBetes_food.domain.recipe import (
    RECIPE_MEAL_TYPES,
    RECIPE_NAME_MAX_LENGTH,
    RECIPE_NOTES_MAX_LENGTH,
)
from DayBetes_food.domain.manual_intake import (
    MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH,
    MANUAL_INTAKE_NAME_MAX_LENGTH,
    MANUAL_INTAKE_ORIGIN_MAX_LENGTH,
)
from DayBetes_food.domain.constants import (
    NOVA_MAX,
    NOVA_MIN,
    YUKA_MAX,
    YUKA_MIN,
    FoodCategory,
    FoodPhysicalState,
    AmountMethod,
    Nutriscore,
)
from DayBetes_food.components.food.food_widgets import (
    _amount_method_default_select,
    _brand_autocomplete_input,
    _confidence_select,
    _decimal_input,
    _favorite_checkbox,
    _glycemic_index_select,
    _label_with_help,
    _labeled_input,
    _labeled_select,
    _macros_confidence_select,
    _macros_source_select,
    _nutrient_mode_select,
    _searchable_autocomplete_bootstrap_script,
    _searchable_autocomplete_input,
    _smart_macros_block,
)
from DayBetes_food.components.food.food_list import (
    MealSelector,
    _meal_type_pill,
)


def _form_page_shell(content, result_id: str, *scripts):
    """Shared shell of the create and edit pages: one column of sections."""
    return Div(
        Div(content, cls="w-full"),
        Div(id=result_id, cls="text-sm w-full"),
        _searchable_autocomplete_bootstrap_script(),
        *scripts,
        data_hide_cart="true",
        cls="""
            flex flex-col items-center
            gap-4
            md:mt-7 lg:mt-7 mt-2
            md:w-xl lg:w-xl w-xs
            w-full mx-auto
            md:mb-32 lg:mb-32 mb-28
        """,
    )


def _form_back_button(back_path: str | None = None):
    """Back to the previous page; `back_path` is the parent opened when there
    is none (the food's page when editing, Food when creating)."""
    return Button(
        "‹ Back",
        type="button",
        cls="text-sm font-medium text-gray-700 cursor-pointer px-1 py-1",
        onclick=back_js(back_path or "/food"),
    )


def _name_title_input(value: str, placeholder: str, maxlength: int | None = None):
    """The name reads as the page title and is edited in place, with no box."""
    return Div(
        Label("Name", cls="sr-only", **{"for": "field_name"}),
        Input(
            type="text",
            id="field_name",
            name="name",
            value=value,
            placeholder=placeholder,
            autocomplete="off",
            **({"maxlength": str(maxlength)} if maxlength is not None else {}),
            cls="""
                w-full text-2xl font-bold text-gray-900 placeholder:text-gray-400
                px-0 py-0.5 border-0 rounded-none
                bg-transparent shadow-none
                focus:outline-none
            """,
            style="background:transparent;border-color:transparent;box-shadow:none;",
        ),
    )


def _form_header(kind: str, title, back_path: str | None = None):
    """Back link and what is being created or edited, over the name as title."""
    return Div(
        Div(
            _form_back_button(back_path),
            Span(kind, cls="web_section_label"),
            cls="flex items-center justify-between",
        ),
        title,
        cls="w-full px-1 flex flex-col gap-1",
    )


def _form_grid_cls(cols: int) -> str:
    if cols == 3:
        return "grid grid-cols-2 md:grid-cols-3 gap-3"
    if cols == 2:
        return "grid grid-cols-1 md:grid-cols-2 gap-3"
    return "flex flex-col gap-3"


def _form_section(title: str, *fields, cols: int = 2, hint: str = "", step: int | None = None):
    """A group of related fields under one title, instead of one card per field."""
    return Div(
        Div(
            Span(
                str(step),
                cls="w-5 h-5 rounded-full bg-ink text-white text-[11px] font-semibold flex items-center justify-center",
            ) if step else "",
            P(title, cls="web_section_label"),
            cls="flex items-center gap-2",
        ),
        P(hint, cls="text-xs text-gray-500 -mt-1") if hint else "",
        Div(*[field for field in fields if field], cls=_form_grid_cls(cols)),
        cls="web_container relative w-full p-4 flex flex-col gap-3",
    )


def _form_subgroup(title: str, *fields, cols: int = 2):
    """A smaller group inside a section, for the folded optional fields."""
    return Div(
        P(title, cls="text-xs font-semibold text-gray-700"),
        Div(*[field for field in fields if field], cls=_form_grid_cls(cols)),
        cls="flex flex-col gap-2",
    )


def _optional_section(title: str, summary: str, *groups, open_: bool = False):
    """Fields that are rarely needed, folded so they do not overwhelm the form."""
    return Details(
        Summary(
            Div(
                P(title, cls="text-sm font-semibold text-gray-900"),
                P(summary, cls="text-xs text-gray-500"),
                cls="flex flex-col gap-0.5",
            ),
            Span("›", cls="text-2xl leading-none text-gray-500 transition-transform group-open:rotate-90"),
            cls="flex items-center justify-between gap-3 cursor-pointer list-none [&::-webkit-details-marker]:hidden",
        ),
        Div(
            *[group for group in groups if group],
            cls="flex flex-col gap-4 mt-4 pt-4 border-t border-line-soft",
        ),
        open=open_,
        cls="group web_container relative w-full p-4",
    )


def _favorite_row(checked: bool = True):
    return Div(_favorite_checkbox(checked=checked, centered=True), cls="web_container w-full px-4 py-3")


def _form_submit(label: str, **attrs):
    return Button(
        label,
        type="submit",
        cls="web_button web_button_primary w-full px-4 py-3 text-sm md:text-base rounded-2xl",
        **attrs,
    )


def CreateCatalogPage(
    brand_options: list[str] | None = None,
    subtype_options: list[str] | None = None,
    prefill: dict | None = None,
    existing_item_id: int | None = None,
    off_notice: str | None = None,
    barcode_notice: str | None = None,
    alcohol_source_note: str | None = None,
    off_prefill_barcode: str | None = None,
    ciqual_note: str | None = None,
    add_to_recipe: tuple[int, int | None] | None = None,
    return_to_assistant: int | None = None,
    assistant_note: str | None = None,
    draft_key: str | None = None,
):
    """Name, what it is and its macros come first; the rest is folded under
    "More details" and opens by itself when the scanner prefilled any of it.

    `return_to_assistant` is the conversation that opened the form with a draft
    (frontend §9.11): saving goes back to it, and `draft_key` gives that draft
    its own browser draft (§7.14)."""
    result_id = "create_catalog_result_page"
    data = prefill or {}
    def _pv(key: str, fallback: str = ""):
        value = data.get(key)
        if value is None:
            return fallback
        return str(value)

    initial_barcode = _pv("barcode", "").strip()
    draft_suffix = draft_key or (initial_barcode if initial_barcode else "no_barcode")
    details_open = any(
        _pv(k, "").strip()
        for k in (
            "initial_state", "nutriscore", "nova", "yuka", "caffeine", "alcohol", "barcode", "cooking_factor",
            "macros_source", "macros_confidence", "default_amount_method",
        )
    )
    notices = Div(
        *(
            [P(off_notice, cls="text-xs text-amber-700")] if off_notice else []
        ),
        *(
            [P(barcode_notice, cls="text-xs text-amber-700")] if barcode_notice else []
        ),
        *(
            [off_attribution(off_prefill_barcode)] if off_prefill_barcode else []
        ),
        *(
            [P(ciqual_note, cls="text-xs text-gray-700"), ciqual_attribution()] if ciqual_note else []
        ),
        *([P(assistant_note, cls="text-xs text-gray-700")] if assistant_note else []),
        cls="web_container w-full px-4 py-3 flex flex-col gap-1",
    ) if (off_notice or barcode_notice or off_prefill_barcode or ciqual_note or assistant_note) else None
    existing_notice = (
        Div(
            P("A food with this barcode already exists.", cls="text-sm text-gray-700"),
            A(
                "Open it",
                hx_get=f"/food/item/catalog/{int(existing_item_id)}",
                hx_target="#main_content",
                hx_push_url="true",
                **{"hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });"},
                cls="web_button web_button_primary px-3 py-1.5 text-xs w-fit shrink-0",
            ),
            cls="web_container w-full px-4 py-3 flex items-center justify-between gap-2",
        )
        if existing_item_id
        else None
    )
    form = Form(
        _form_header("New food", _name_title_input(_pv("name"), "Name of the food", CATALOG_NAME_MAX_LENGTH)),
        *(
            [
                Input(type="hidden", name="prefill_source", value=_pv("prefill_source")),
                Input(type="hidden", name="prefill_source_id", value=_pv("prefill_source_id")),
            ]
            if _pv("prefill_source")
            else []
        ),
        # The food was chosen from a recipe's ingredient search: it goes in when saved (§9.7).
        *(
            [
                Input(type="hidden", name="add_to_recipe", value=str(add_to_recipe[0])),
                Input(type="hidden", name="add_to_recipe_plate", value=str(add_to_recipe[1] or "")),
            ]
            if add_to_recipe
            else []
        ),
        # A draft of the assistant: saving goes back to its conversation (§9.11).
        *(
            [Input(type="hidden", name="return_to_assistant", value=str(return_to_assistant))]
            if return_to_assistant
            else []
        ),
        notices,
        existing_notice,
        _form_section(
            "What is it?",
            _brand_autocomplete_input(
                brand_options=brand_options, value=_pv("brand"), added=bool(data.get("brand_is_new"))
            ),
            _searchable_autocomplete_input(
                "Category*",
                "category",
                [category.value for category in FoodCategory],
                help_text="Main category. Required.",
                allow_add=False,
                value=_pv("category"),
            ),
            _searchable_autocomplete_input(
                "Subtype*",
                "subtype",
                subtype_options or [],
                help_text="Specific subtype, e.g. yogurt, pasta, soda. Required.",
                allow_add=True,
                value=_pv("subtype"),
                maxlength=FOOD_SUBTYPE_MAX_LENGTH,
                added=bool(data.get("subtype_is_new")),
            ),
            step=1,
        ),
        _form_section(
            "Nutrition",
            _smart_macros_block("catalog", prefill=data, label="Macros per 100 g"),
            _decimal_input(
                "Default serving (g)",
                "default_portion",
                help_text="Default serving size in g. Leave empty if the food has no serving.",
                value=_pv("default_portion"),
            ),
            step=2,
        ),
        _optional_section(
            "More details",
            "Barcode, health scores, caffeine, data quality",
            _form_subgroup(
                "Product",
                _labeled_input(
                    "Barcode",
                    "barcode",
                    value=initial_barcode,
                    help_text="Optional product barcode.",
                    select_on_click=False,
                    inputmode="numeric",
                    pattern="[0-9]*",
                    maxlength=CATALOG_BARCODE_MAX_LENGTH,
                    input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
                ),
                _searchable_autocomplete_input(
                    "Initial state",
                    "initial_state",
                    [s.value for s in FoodPhysicalState],
                    help_text="Physical state before preparation.",
                    allow_add=False,
                    value=_pv("initial_state"),
                ),
                _decimal_input("Cooking factor", "cooking_factor", help_text="Cooked/raw weight ratio. Leave empty if unknown.", value=_pv("cooking_factor")),
            ),
            _form_subgroup(
                "Other nutrients per 100 g",
                _decimal_input("Caffeine (mg)", "caffeine", help_text="Caffeine in mg per 100 g.", value=_pv("caffeine")),
                _decimal_input("Alcohol (g)", "alcohol", help_text="Alcohol in g per 100 g.", value=_pv("alcohol")),
                *([P(alcohol_source_note, cls="text-xs text-gray-600 md:col-span-2")] if alcohol_source_note else []),
            ),
            _form_subgroup(
                "Health scores",
                _searchable_autocomplete_input(
                    "Nutriscore",
                    "nutriscore",
                    [n.value for n in Nutriscore],
                    help_text="Nutrition quality score from A to E.",
                    allow_add=False,
                    value=_pv("nutriscore"),
                ),
                _labeled_input("NOVA (1-4)", "nova", "number", help_text="Food processing level from 1 to 4.", step="1", inputmode="numeric", min_value=NOVA_MIN, max_value=NOVA_MAX, value=_pv("nova")),
                _labeled_input("Yuka (0-100)", "yuka", "number", help_text="Optional Yuka-style score from 0 to 100.", step="1", inputmode="numeric", min_value=YUKA_MIN, max_value=YUKA_MAX, value=_pv("yuka")),
                cols=3,
            ),
            _form_subgroup(
                "Data quality",
                _macros_source_select(_pv("macros_source") or None),
                _macros_confidence_select(int(_pv("macros_confidence")) if _pv("macros_confidence") else None),
                _amount_method_default_select(_pv("default_amount_method") or None),
            ),
            open_=details_open,
        ),
        _favorite_row(data.get("favorite", True) is not False),
        _form_submit("Create food"),
        hx_post="/food/create/catalog",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key=f"food_form_create_catalog_page::{draft_suffix}",
        cls="flex flex-col gap-4 w-full",
    )
    return _form_page_shell(form, result_id, Script(src=asset_busted("/js/smart_macros.js"), defer="defer"))


def _manual_nutrient_input(label_per100: str, label_total: str, name: str, value: str | None = None):
    """Nutrient field of the manual dish forms. Its label follows the nutrient
    mode (static/js/manual_intake_form.js). There is no `max` on the field: a
    total may legitimately exceed the per-100 g limit, and the server checks
    the converted value (measurement §5.4)."""
    return _decimal_input(
        label_per100,
        name,
        value=value,
        label_attrs={
            "data_mode_label": "true",
            "data_label_per100": label_per100,
            "data_label_total": label_total,
        },
        input_attrs={"data_nutrient_field": "true"},
    )


def _manual_portion_input(value: str | None = None):
    return _decimal_input(
        "Serving weight (g)",
        "default_portion",
        help_text="Optional when you type values per 100 g; required when you type totals.",
        value=value,
        input_attrs={"data_manual_weight": "true"},
    )


def _manual_description_input(value: str = "", textarea_id: str = "manual_description"):
    return Div(
        _label_with_help("Description", "Optional notes about the dish.", for_id=textarea_id),
        Textarea(
            value,
            id=textarea_id,
            name="description",
            rows="3",
            maxlength=str(MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH),
            cls=FORM_FIELD_CLS,
        ),
        cls="flex flex-col gap-1 col-span-1 md:col-span-2",
    )


def _manual_origin_input(origin_options: list[str] | None, value: str | None = None):
    # Free text (decision 2026-10-09): no "Add"; the suggestions only help.
    # The field is not called "origin": FastHTML resolves a route parameter
    # from the request headers before the form body, and every browser POST
    # carries an `Origin` header that would replace the typed value.
    return _searchable_autocomplete_input(
        "Origin",
        "source_origin",
        origin_options or [],
        help_text="Who or where made it (e.g. grandma Geno, Burger King). Free text.",
        allow_add=False,
        value=value,
        maxlength=MANUAL_INTAKE_ORIGIN_MAX_LENGTH,
    )


def CreateManualPage(
    subtype_options: list[str] | None = None,
    origin_options: list[str] | None = None,
    prefill: dict | None = None,
    return_to_assistant: int | None = None,
    draft_key: str | None = None,
):
    """Reusable dish (code_conventions.md §11.2.3): name and carbs required.

    With `prefill`, a dish draft of the assistant (§8.12, frontend §9.11): its
    values are shown for review, `return_to_assistant` sends the save back to the
    conversation and `draft_key` gives it its own browser draft (§7.14)."""
    result_id = "create_manual_result_page"
    data = prefill or {}

    def _pv(key: str) -> str:
        value = data.get(key)
        return "" if value is None else str(value)

    details_open = any(
        _pv(key) for key in (
            "description", "glycemic_index", "ig_confidence", "caffeine", "alcohol",
            "macros_source", "macros_confidence", "default_amount_method",
        )
    )
    note = data.get("assistant_note")
    form = Form(
        _form_header("New dish", _name_title_input(_pv("name"), "Name of the dish", MANUAL_INTAKE_NAME_MAX_LENGTH)),
        *(
            [Input(type="hidden", name="return_to_assistant", value=str(return_to_assistant))]
            if return_to_assistant
            else []
        ),
        Div(P(note, cls="text-xs text-gray-700"), cls="web_container w-full px-4 py-3") if note else None,
        _form_section(
            "About the dish",
            _manual_origin_input(origin_options, _pv("origin") or None),
            _searchable_autocomplete_input(
                "Subtype",
                "subtype",
                subtype_options or [],
                help_text="Specific subtype. Optional.",
                allow_add=True,
                value=_pv("subtype") or None,
                maxlength=FOOD_SUBTYPE_MAX_LENGTH,
                added=bool(data.get("subtype_is_new")),
            ),
            step=1,
        ),
        _form_section(
            "Nutrition",
            _nutrient_mode_select("manual"),
            _manual_portion_input(_pv("default_portion") or None),
            _smart_macros_block(
                "manual",
                prefill=data,
                label="Macros per 100 g",
                label_total="Macros of one serving",
            ),
            P("Carbs are required: write 0hc if the dish has no carbs.", cls="text-xs text-gray-500 md:col-span-2 -mt-1"),
            step=2,
        ),
        _optional_section(
            "More details",
            "Description, glycemic response, caffeine, data quality",
            _form_subgroup("Description", _manual_description_input(_pv("description")), cols=1),
            _form_subgroup(
                "Glycemic response",
                _glycemic_index_select(_pv("glycemic_index") or None),
                _confidence_select(
                    "IG confidence",
                    "ig_confidence",
                    data.get("ig_confidence"),
                    "How sure you are about the glycemic index. Needs a glycemic index.",
                ),
            ),
            _form_subgroup(
                "Other nutrients",
                _manual_nutrient_input("Caffeine (mg/100 g)", "Caffeine (mg in total)", "caffeine", _pv("caffeine") or None),
                _manual_nutrient_input("Alcohol (g/100 g)", "Alcohol (g in total)", "alcohol", _pv("alcohol") or None),
            ),
            _form_subgroup(
                "Data quality",
                _macros_source_select(_pv("macros_source") or None),
                _macros_confidence_select(data.get("macros_confidence")),
                _amount_method_default_select(_pv("default_amount_method") or None),
            ),
            open_=details_open,
        ),
        _favorite_row(data.get("favorite", True) is not False),
        _form_submit("Create dish"),
        Script(src=asset_busted("/js/manual_intake_form.js"), defer="defer"),
        hx_post="/food/create/manual_intake",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key=f"food_form_create_manual_page::{draft_key}" if draft_key else "food_form_create_manual_page",
        cls="flex flex-col gap-4 w-full",
    )
    return _form_page_shell(form, result_id, Script(src=asset_busted("/js/smart_macros.js"), defer="defer"))


def QuickAddPage(events: list, plate_options: list, selected_plate_id: int | None):
    """Quick add (code_conventions.md §11.2.3): a one-off meal logged into a
    plate and never offered again. Name, estimated weight and carbs are
    required; the smart-macros text is always the total eaten (measurement §5.4).

    The meal and plate selector goes on top and outside the Form: its "New
    Meal" input has its own hx_post and must not submit the form. Its values
    travel with hx_include, as in AddButton (frontend §7.7)."""
    result_id = "quick_add_result"
    form = Form(
        _form_section(
            "What did you eat?",
            _labeled_input(
                "Name*",
                "name",
                help_text="e.g. Menu of the day. Required.",
                maxlength=MANUAL_INTAKE_NAME_MAX_LENGTH,
            ),
            _decimal_input(
                "Estimated weight (g)*",
                "default_portion",
                help_text="Rough weight of everything you ate. Required.",
            ),
            _smart_macros_block("quick", label="Macros of everything you ate"),
            P("Carbs are required: write 0hc if there were none.", cls="text-xs text-gray-500 md:col-span-2 -mt-1"),
            # U1 and U2 (study §6.3): optional, empty by default; nothing is guessed.
            _macros_source_select(None),
            _labeled_select(
                "Weight from",
                "amount_method",
                [member.value for member in AmountMethod],
                help_text="How you got that weight: a scale, the package, by eye, an AI estimate...",
                labels={member.value: text for member, text in AMOUNT_METHOD_LABELS.items()},
            ),
        ),
        _optional_section(
            "Notes",
            "Anything worth remembering about it",
            Div(
                Label("Notes", cls="sr-only", **{"for": "quick_add_notes"}),
                Textarea(
                    "",
                    id="quick_add_notes",
                    name="description",
                    rows="3",
                    maxlength=str(MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH),
                    cls=FORM_FIELD_CLS,
                ),
            ),
        ),
        _form_submit("Add to meal", **{"hx-disabled-elt": "this"}),
        hx_post="/food/quick_add",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        hx_include="#meal_selector, #plate_selector",
        data_draft_key="food_form_quick_add",
        cls="flex flex-col gap-4 w-full",
    )
    content = Div(
        _form_header("Quick add", H1("Log it once", cls="text-2xl font-bold text-gray-900")),
        Div(
            MealSelector(
                events or [],
                selected_id=(events[0].id if events else None),
                plate_options=plate_options,
                selected_plate_id=selected_plate_id,
            ),
                cls="web_container relative w-full px-4 py-3",
        ),
        form,
        cls="flex flex-col gap-4 w-full",
    )
    return _form_page_shell(content, result_id, Script(src=asset_busted("/js/smart_macros.js"), defer="defer"))


def _recipe_servings_field(value: str):
    """Optional. Adding a recipe to a meal then asks how many servings (measurement §4.7)."""
    return Div(
        _label_with_help("Servings", "How many servings the whole recipe makes. Optional.", for_id="field_servings"),
        Input(type="text", id="field_servings", name="servings", inputmode="numeric", value=value, cls=FORM_FIELD_CLS),
        cls="flex flex-col gap-1",
    )


def _recipe_extra_meal_types_field(selected):
    """The search also finds it under these. Adding it to a new meal uses the main one."""
    return Div(
        _label_with_help("Also for", "Other meal types this recipe is eaten as. They only help to find it."),
        Div(
            *[
                _meal_type_pill(meal, name="extra_meal_types", checked=meal.value in selected)
                for meal in RECIPE_MEAL_TYPES
            ],
            cls="flex flex-wrap gap-1.5",
        ),
        cls="flex flex-col gap-1 md:col-span-2",
    )


@dataclass(frozen=True)
class RecipeDraftLine:
    """One ingredient of a recipe draft of the assistant, as the form shows it."""

    name: str
    grams: float
    preparation: str  # "griddle · solid · weighed cooked", or ""
    new_dish_carbs_g: float | None  # a new dish: its estimated carbs; None for a food


@dataclass(frozen=True)
class RecipeDraftForm:
    """A recipe draft of the assistant for the create form (frontend §9.11)."""

    message_id: int
    tool_use_id: str
    name: str
    meal_type: str
    extra_meal_types: tuple
    servings: str
    notes: str
    plates: tuple  # (plate name or None, tuple[RecipeDraftLine, ...])
    favorite: bool = True


def _recipe_draft_line(line: RecipeDraftLine):
    meta = [f"{line.grams:g} g"]
    if line.preparation:
        meta.append(line.preparation)
    if line.new_dish_carbs_g is not None:
        meta.append(f"{line.new_dish_carbs_g:g} g carbs")
    return Li(
        Div(
            Span(line.name, cls="text-sm text-gray-900 break-words"),
            Span("New dish", cls="text-[10px] font-semibold uppercase text-amber-800")
            if line.new_dish_carbs_g is not None
            else None,
            cls="flex items-center gap-2 min-w-0",
        ),
        P(" · ".join(meta), cls="text-xs text-gray-500"),
        cls="flex flex-col",
    )


def _recipe_draft_section(draft: RecipeDraftForm):
    """The ingredients the assistant proposes: read only, saved with the recipe."""
    several = len(draft.plates) > 1
    blocks = []
    for index, (plate_name, lines) in enumerate(draft.plates, start=1):
        blocks.append(
            Div(
                P(plate_name or f"Plate {index}", cls="web_section_label") if several else None,
                Ul(*(_recipe_draft_line(line) for line in lines), cls="flex flex-col gap-1.5"),
                cls="flex flex-col gap-1.5",
            )
        )
    return _form_section(
        "Ingredients",
        P(
            "Proposed by the assistant. They are added when you save; edit them afterwards in the recipe.",
            cls="text-xs text-gray-600 md:col-span-2",
        ),
        Div(*blocks, cls="flex flex-col gap-3 md:col-span-2"),
    )


def CreateRecipePage(draft: RecipeDraftForm | None = None, return_to_assistant: int | None = None):
    """With `draft`, the form of a recipe draft of the assistant (frontend §9.11):
    the fields prefilled and its ingredients below, all saved together."""
    result_id = "create_recipe_result_page"
    form = Form(
        _form_header(
            "New recipe",
            _name_title_input(draft.name if draft else "", "Name of the recipe", RECIPE_NAME_MAX_LENGTH),
        ),
        *(
            [
                Input(type="hidden", name="assistant_message", value=str(draft.message_id)),
                Input(type="hidden", name="assistant_tool", value=draft.tool_use_id),
                Input(type="hidden", name="return_to_assistant", value=str(return_to_assistant or "")),
            ]
            if draft
            else []
        ),
        _form_section(
            "About the recipe",
            _labeled_select(
                "Meal type",
                "meal_type",
                [meal_type.value for meal_type in RECIPE_MEAL_TYPES],
                help_text="When this recipe is usually eaten.",
                selected_value=draft.meal_type if draft else "",
                labels=MEAL_TYPE_LABELS,
            ),
            _recipe_extra_meal_types_field(draft.extra_meal_types if draft else ()),
            _recipe_servings_field(draft.servings if draft else ""),
            Div(
                _label_with_help("Notes", "Optional instructions, comments, or context about this recipe.", for_id="create_recipe_notes"),
                Textarea(
                    draft.notes if draft else "",
                    id="create_recipe_notes",
                    name="notes",
                    rows="8",
                    maxlength=str(RECIPE_NOTES_MAX_LENGTH),
                    cls=FORM_FIELD_CLS,
                ),
                cls="flex flex-col gap-1 md:col-span-2",
            ),
            hint="" if draft else "You add the ingredients on the next screen.",
        ),
        _recipe_draft_section(draft) if draft else None,
        _favorite_row(draft.favorite if draft else True),
        _form_submit("Create recipe"),
        hx_post="/food/create/recipe",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        # A draft of the assistant has its own browser draft (frontend §9.11).
        data_draft_key=(
            f"food_form_create_recipe_page::assistant_{draft.message_id}_{draft.tool_use_id}"
            if draft
            else "food_form_create_recipe_page"
        ),
        cls="flex flex-col gap-4 w-full",
    )
    return _form_page_shell(form, result_id)


def _input_value(value) -> str:
    if value is None:
        return ""
    return str(value)


def _edit_header(kind: str, name: str, back_path: str, maxlength: int):
    return _form_header(f"Edit {kind}", _name_title_input(name, "Name", maxlength), back_path)


def _edit_actions(back_path: str):
    return Div(
        Button(
            "Cancel",
            type="button",
            cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl",
            hx_get=back_path,
            hx_target="#main_content",
            hx_swap="innerHTML",
            hx_push_url="true",
            **{"hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });"},
        ),
        Button(
            "Save changes",
            type="submit",
            cls="web_button web_button_primary w-full px-4 py-3 text-sm md:text-base rounded-2xl",
        ),
        cls="grid grid-cols-2 gap-3 w-full",
    )


def EditCatalogPage(
    entry: dict,
    brand_options: list[str] | None = None,
    subtype_options: list[str] | None = None,
):
    result_id = f"edit_catalog_result_{entry['id']}"
    back_path = f"/food/item/catalog/{entry['id']}"

    def _num(label, name):
        return _decimal_input(label, name, value=_input_value(entry.get(name)))

    form = Form(
        _edit_header("food", _input_value(entry.get("name")), back_path, CATALOG_NAME_MAX_LENGTH),
        _form_section(
            "Basics",
            _brand_autocomplete_input(brand_options=brand_options, value=_input_value(entry.get("brand"))),
            _labeled_input(
                "Barcode",
                "barcode",
                value=_input_value(entry.get("barcode")),
                select_on_click=False,
                inputmode="numeric",
                pattern="[0-9]*",
                maxlength=CATALOG_BARCODE_MAX_LENGTH,
                input_style="transition:none; transform:none; scale:1; box-shadow:none; outline:none;",
            ),
            _decimal_input("Default serving (g)", "default_portion", value=_input_value(entry.get("default_portion"))),
        ),
        _form_section(
            "Nutrition per 100 g",
            _num("Calories (kcal)", "calories_100g"),
            _num("Carbs (g)", "carbs_100g"),
            _num("Sugars (g)", "sugars_100g"),
            _num("Fats (g)", "fats_100g"),
            _num("Saturated (g)", "saturated_100g"),
            _num("Proteins (g)", "proteins_100g"),
            _num("Fiber (g)", "fiber_100g"),
            _num("Caffeine (mg)", "caffeine"),
            _num("Alcohol (g)", "alcohol"),
            cols=3,
        ),
        _form_section(
            "Classification",
            _searchable_autocomplete_input("Category*", "category", [c.value for c in FoodCategory], allow_add=False, value=_input_value(entry.get("category"))),
            _searchable_autocomplete_input("Subtype*", "subtype", subtype_options or [], allow_add=True, value=_input_value(entry.get("subtype")), maxlength=FOOD_SUBTYPE_MAX_LENGTH),
            _searchable_autocomplete_input("Initial state", "initial_state", [s.value for s in FoodPhysicalState], allow_add=False, value=_input_value(entry.get("initial_state"))),
            _decimal_input("Cooking factor", "cooking_factor", value=_input_value(entry.get("cooking_factor"))),
        ),
        _form_section(
            "Data quality",
            _macros_source_select(entry.get("macros_source")),
            _macros_confidence_select(entry.get("macros_confidence")),
            _amount_method_default_select(entry.get("default_amount_method")),
            hint="Where the macros come from and how sure you are about them.",
        ),
        _form_section(
            "Health scores",
            _searchable_autocomplete_input("Nutriscore", "nutriscore", [n.value for n in Nutriscore], allow_add=False, value=_input_value(entry.get("nutriscore"))),
            _labeled_input("NOVA (1-4)", "nova", "number", step="1", inputmode="numeric", min_value=NOVA_MIN, max_value=NOVA_MAX, value=_input_value(entry.get("nova"))),
            _labeled_input("Yuka (0-100)", "yuka", "number", step="1", inputmode="numeric", min_value=YUKA_MIN, max_value=YUKA_MAX, value=_input_value(entry.get("yuka"))),
            cols=3,
        ),
        _edit_actions(back_path),
        hx_post=f"/food/edit/catalog/{entry['id']}",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key=f"food_form_edit_catalog_{entry['id']}",
        cls="flex flex-col gap-4 w-full",
    )
    return _form_page_shell(form, result_id)


def EditManualPage(
    entry: dict,
    subtype_options: list[str] | None = None,
    origin_options: list[str] | None = None,
):
    """Full replacement of a reusable dish (H1). It opens in "per 100 g" mode
    with the stored values (measurement §5.4). Publishing is the detail page's
    action (decision 2026-10-09), and favorite is not part of the edit, as in
    catalog."""
    result_id = f"edit_manual_result_{entry['id']}"
    back_path = f"/food/item/manual_intake/{entry['id']}"
    nutrient_specs = (
        ("Calories/100g", "Calories (total)", "calories_100g"),
        ("Carbs/100g*", "Carbs (total)*", "carbs_100g"),
        ("Sugars/100g", "Sugars (total)", "sugars_100g"),
        ("Fats/100g", "Fats (total)", "fats_100g"),
        ("Saturated/100g", "Saturated (total)", "saturated_100g"),
        ("Proteins/100g", "Proteins (total)", "proteins_100g"),
        ("Fiber/100g", "Fiber (total)", "fiber_100g"),
    )
    form = Form(
        _edit_header("dish", _input_value(entry.get("name")), back_path, MANUAL_INTAKE_NAME_MAX_LENGTH),
        _form_section(
            "Basics",
            _manual_origin_input(origin_options, value=_input_value(entry.get("origin"))),
            _searchable_autocomplete_input(
                "Subtype",
                "subtype",
                subtype_options or [],
                allow_add=True,
                value=_input_value(entry.get("subtype")),
                maxlength=FOOD_SUBTYPE_MAX_LENGTH,
            ),
            Div(
                _manual_description_input(
                    _input_value(entry.get("description")),
                    textarea_id="edit_manual_description",
                ),
                cls="md:col-span-2",
            ),
        ),
        _form_section(
            "Nutrition",
            _nutrient_mode_select(f"edit_manual_{entry['id']}"),
            _manual_portion_input(value=_input_value(entry.get("default_portion"))),
        ),
        _form_section(
            "Macros",
            *[
                _manual_nutrient_input(per100, total, name, _input_value(entry.get(name)))
                for per100, total, name in nutrient_specs
            ],
            _manual_nutrient_input("Caffeine (mg/100 g)", "Caffeine (mg in total)", "caffeine", _input_value(entry.get("caffeine"))),
            _manual_nutrient_input("Alcohol (g/100 g)", "Alcohol (g in total)", "alcohol", _input_value(entry.get("alcohol"))),
            cols=3,
        ),
        _form_section(
            "Glycemic response",
            _glycemic_index_select(entry.get("glycemic_index")),
            _confidence_select(
                "IG confidence",
                "ig_confidence",
                entry.get("ig_confidence"),
                "How sure you are about the glycemic index. Needs a glycemic index.",
            ),
        ),
        _form_section(
            "Data quality",
            _macros_source_select(entry.get("macros_source")),
            _macros_confidence_select(entry.get("macros_confidence")),
            _amount_method_default_select(entry.get("default_amount_method")),
            hint="Where the macros come from and how sure you are about them.",
        ),
        _edit_actions(back_path),
        Script(src=asset_busted("/js/manual_intake_form.js"), defer="defer"),
        hx_post=f"/food/edit/manual_intake/{entry['id']}",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key=f"food_form_edit_manual_{entry['id']}",
        data_manual_convert="true",
        cls="flex flex-col gap-4 w-full",
    )
    return _form_page_shell(form, result_id)


def EditRecipePage(
    entry: dict,
):
    result_id = f"edit_recipe_result_{entry['id']}"
    back_path = f"/food/item/recipe/{entry['id']}"
    form = Form(
        _edit_header("recipe", _input_value(entry.get("name")), back_path, RECIPE_NAME_MAX_LENGTH),
        _form_section(
            "Basics",
            _labeled_select("Meal type", "meal_type", [meal_type.value for meal_type in RECIPE_MEAL_TYPES], selected_value=_input_value(entry.get("meal_type")), labels=MEAL_TYPE_LABELS),
            _recipe_extra_meal_types_field(entry.get("extra_meal_types") or ()),
            _recipe_servings_field(_input_value(entry.get("servings"))),
            Div(
                _label_with_help("Notes", "Optional instructions, comments, or context about this recipe.", for_id="edit_recipe_notes"),
                Textarea(
                    _input_value(entry.get("notes")),
                    id="edit_recipe_notes",
                    name="notes",
                    rows="8",
                    maxlength=str(RECIPE_NOTES_MAX_LENGTH),
                    cls=FORM_FIELD_CLS,
                ),
                cls="flex flex-col gap-1 md:col-span-2",
            ),
        ),
        _edit_actions(back_path),
        hx_post=f"/food/edit/recipe/{entry['id']}",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key=f"food_form_edit_recipe_{entry['id']}",
        cls="flex flex-col gap-4 w-full",
    )
    return _form_page_shell(form, result_id)
