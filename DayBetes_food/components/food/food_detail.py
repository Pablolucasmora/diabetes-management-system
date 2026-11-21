"""Detail page of a food, a dish or a recipe, with the recipe's plates and ingredients and the ingredient picker (frontend_conventions.md §9.4, §9.7)."""

import json
from fasthtml.common import *
from DayBetes_food.components.cart.cart_shared import CHECKBOX_CLS
from DayBetes_food.components.injection_zone import asset_busted
from DayBetes_food.components.navigation import back_js
from DayBetes_food.components.guide import GuideHelpButton
from DayBetes_food.components.food.food_actions import COPY_LABEL, COPY_QUESTION, EDIT_LABELS
from DayBetes_food.components.food.food_shared import (
    AMOUNT_METHOD_LABELS,
    INLINE_FIELD_CLS,
    NOT_GIVEN_LABEL,
    STORAGE_LABELS,
)
from DayBetes_food.components.modal import (
    close_modal_js,
    ConfirmActionModal,
    modal_confirm_button,
    open_modal_js,
)
from DayBetes_food.domain.food import INITIAL_AMOUNT_WITHOUT_SERVING_G
from DayBetes_food.components.food.recipe_add import RecipeAddModal, recipe_add_open_attrs
from DayBetes_food.domain.intake_plate import derive_plate_name
from DayBetes_food.domain.recipe_plate import RECIPE_PLATE_NAME_MAX_LENGTH
from DayBetes_food.domain.constants import (
    AmountInputUnit,
    ConservationMethod,
    CookingMethod,
    FoodEntryType,
    FoodPhysicalState,
    PortionOrigin,
    Ripeness,
    StorageLocation,
)
from DayBetes_food.domain.portion_detail import RIPENESS_CATEGORY
from DayBetes_food.components.food.food_widgets import (
    FILTER_ITEM_CLS,
    _food_back_button,
    _searchable_autocomplete_bootstrap_script,
    _searchable_compact_input,
)
from DayBetes_food.components.food.food_list import (
    AddButton,
    MealSelector,
    _entry_meta,
)


def _recipe_picker_plate_input(recipe_plate_id: int | None):
    return Input(type="hidden", id="recipe_ingredient_plate", name="recipe_plate_id", value=str(recipe_plate_id or ""))


def RecipeIngredientSearchInput(recipe_id: int):
    return Input(
        inputmode="text",
        placeholder="Search food to add",
        name="search",
        id="recipe_ingredient_search_input",
        data_skip_page_loading="true",
        cls="""
            web_input
            border border-line inset-shadow-none
            rounded-2xl
            md:w-xl lg:w-xl
            w-xs
            transition-all
            px-4 py-3 text-sm
        """,
        hx_get=f"/food/recipe/{recipe_id}/ingredients/list",
        hx_target="#recipe-ingredient-list",
        hx_trigger="keyup changed delay:300ms",
        hx_include="#recipe_ingredient_filter, #recipe_ingredient_plate",
        hx_swap="innerHTML",
    )


def RecipeMacrosGrid(recipe_id: int, summary: dict, **attrs):
    """Totals of the recipe. A macro no ingredient knows is an em dash; one only some
    know is the sum of those, and a line says so (measurement §2, §6.9.4)."""
    unknown = summary.get("partial_macros") or []
    return Div(
        Div(
            *_detail_macro_tiles(summary.get("per100") or {}, summary.get("default_amount_g") or 100.0),
            cls="grid grid-cols-2 md:grid-cols-3 gap-2",
        ),
        P(f"Some ingredients have no data for: {', '.join(unknown)}.", cls="text-xs text-gray-500") if unknown else "",
        id=f"food_detail_recipe_{recipe_id}_macros",
        cls="flex flex-col gap-2",
        **attrs,
    )


def RecipeDetailsGrid(recipe_id: int, summary: dict, **attrs):
    return Div(
        _detail_info_rows(summary.get("info_rows") or []),
        id=f"food_detail_recipe_{recipe_id}_details",
        **attrs,
    )


def RecipeSummaryOob(recipe_id: int, summary: dict) -> tuple:
    """The summary repainted by whatever changes the ingredients (frontend §6)."""
    return (
        RecipeMacrosGrid(recipe_id, summary, hx_swap_oob="true"),
        RecipeDetailsGrid(recipe_id, summary, hx_swap_oob="true"),
    )


def _float_or_zero(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _display_base_unit(entry_type: str, item: dict) -> str:
    """Display unit of a food: grams for now.

    Liquids/mashed/gel will show ml in the future (audit/deuda_pendiente.md);
    until then every food is shown in grams.
    """
    return "g"


def _detail_unit_options(base_amount: float | None, base_unit: str):
    """Unit selector options of the ingredient page.

    Factors come from the central enum (measurement §11); `data_factor` is
    presentation only: the form sends `amount_value` + `amount_unit` and the
    server converts them (decision 2026-09-22). `portion` uses the food's
    serving, which the server resolves again from the database. With no serving
    (`base_amount is None`) the `serving` option is not offered (H15)."""
    options = []
    if base_amount is not None:
        options.append(
            Option(
                f"serving ({base_amount:.0f}{base_unit})",
                value=AmountInputUnit.PORTION.value,
                selected=True,
                data_factor=f"{base_amount:.6f}",
                data_unit_label="serving",
            )
        )
    options.extend(
        [
            Option(
                f"{base_unit} (1{base_unit})",
                value=AmountInputUnit.GRAMS.value,
                selected=base_amount is None,
                data_factor=f"{AmountInputUnit.GRAMS.grams_factor:.6f}",
                data_unit_label=base_unit,
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


def _detail_macro_tiles(per100: dict, amount_g: float):
    specs = [
        ("calories_100g", "Calories", "kcal"),
        ("carbs_100g", "Carbs", "g"),
        ("sugars_100g", "Sugars", "g"),
        ("fats_100g", "Fats", "g"),
        ("saturated_100g", "Saturated", "g"),
        ("proteins_100g", "Proteins", "g"),
        ("fiber_100g", "Fiber", "g"),
    ]
    tiles = []
    for key, label, unit in specs:
        per100_value = per100.get(key)
        if per100_value is None:
            # Unknown is not 0 (measurement §2): paint an em dash.
            amount_text = "—"
            data_per100 = ""
        else:
            amount = (amount_g * float(per100_value)) / 100.0
            amount_text = f"{amount:.0f} {unit}" if unit == "kcal" else f"{amount:.1f} {unit}"
            data_per100 = f"{float(per100_value):.6f}"
        tiles.append(
            Div(
                Span(label, cls="text-xs text-gray-600"),
                Span(
                    amount_text,
                    data_detail_macro_key=key,
                    data_per100=data_per100,
                    data_unit=unit,
                    cls="text-base font-semibold text-gray-900",
                ),
                cls="web_container p-3 rounded-xl flex flex-col gap-1",
            )
        )
    return tiles


def _detail_info_rows(rows: list[tuple[str, str]]):
    blocks = []
    for label, value in rows:
        clean = (value or "").strip()
        if not clean:
            continue
        blocks.append(
            Div(
                Span(label, cls="text-xs text-gray-600"),
                Span(clean, cls="text-sm text-gray-900"),
                cls="web_container p-3 rounded-xl flex flex-col gap-1",
            )
        )
    if not blocks:
        return Div("No extra info yet.", cls="text-sm text-gray-500")
    return Div(*blocks, cls="grid grid-cols-1 md:grid-cols-2 gap-2")


def _recipe_portion_name(portion) -> str:
    return portion.source.name or f"Ingredient #{portion.id}"


def _recipe_portion_meta(portion) -> str:
    carbs = portion.source.carbs_100g
    entry_label = "Food" if portion.origin is PortionOrigin.CATALOG else "Manual"
    return f"{entry_label} · {carbs if carbs is not None else '-'} CH"


def _recipe_portion_base_amount(portion) -> float | None:
    """The food's serving in grams, or None when it has no serving (H15)."""
    unit_g = portion.source.unit_g
    return float(unit_g) if unit_g is not None else None


def _recipe_portion_base_unit(portion) -> str:
    item = {"category": portion.source.category, "subtype": portion.source.subtype}
    return _display_base_unit(portion.origin.value, item)


def _recipe_block_id(recipe_id: int) -> str:
    return f"recipe_ingredients_{recipe_id}"


def _recipe_portion_preparation(portion) -> str:
    parts = [item.value for item in (portion.cooking, portion.final_state, portion.conservation) if item]
    return " · ".join(parts)


def RecipeIngredientReadOnlyRow(portion):
    """What someone who cannot edit the recipe sees: they copy it or add it (§11.2.4)."""
    preparation = _recipe_portion_preparation(portion)
    return Div(
        Div(
            H3(_recipe_portion_name(portion), cls="text-left font-semibold"),
            P(_recipe_portion_meta(portion), cls="text-sm text-gray-700"),
            P(preparation, cls="text-xs text-gray-500") if preparation else "",
            cls="flex flex-col gap-0.5 min-w-0",
        ),
        Span(f"{_float_or_zero(portion.amount):.0f} g", cls="text-sm text-gray-700 shrink-0 ml-3"),
        cls="web_container food_entry flex items-start justify-between",
    )


def _recipe_cooked_weight_field(recipe_id: int, portion):
    """Same criterion as the cart: only with a factor, or on a portion that inherited
    the mark, so it can be removed (measurement §5.2)."""
    if portion.origin is not PortionOrigin.CATALOG:
        return ""
    if portion.source.cooking_factor is None and not portion.is_cooked_weight:
        return ""
    return Label(
        Input(
            type="checkbox",
            name="is_cooked_weight",
            value="true",
            checked=bool(portion.is_cooked_weight),
            cls=CHECKBOX_CLS,
            hx_post=f"/food/recipe/{recipe_id}/ingredient/{int(portion.id)}/cooked",
            hx_trigger="change",
            hx_target=f"#{_recipe_block_id(recipe_id)}",
            hx_swap="outerHTML",
            hx_push_url="false",
            data_skip_page_loading="true",
        ),
        Span("Weighed cooked", cls="text-xs text-gray-600"),
        cls="flex items-center gap-2",
    )


def _recipe_move_field(recipe_id: int, portion, plates: list, plate_labels: dict):
    if len(plates) < 2:
        return ""
    return Label(
        Span("Plate", cls="text-xs text-gray-600"),
        Select(
            *[
                Option(plate_labels[plate.id], value=str(plate.id), selected=plate.id == portion.recipe_plate_id)
                for plate in plates
            ],
            name="recipe_plate_id",
            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-xs",
            hx_post=f"/food/recipe/{recipe_id}/ingredient/{int(portion.id)}/plate",
            hx_trigger="change",
            hx_target=f"#{_recipe_block_id(recipe_id)}",
            hx_swap="outerHTML",
            hx_push_url="false",
            data_skip_page_loading="true",
        ),
        cls="flex items-center gap-2",
    )


def RecipeIngredientRow(recipe_id: int, portion, plates: list = (), plate_labels: dict | None = None):
    portion_id = int(portion.id or 0)
    base_amount = _recipe_portion_base_amount(portion)
    base_unit = _recipe_portion_base_unit(portion)
    grams_value = max(0.0, _float_or_zero(portion.amount))
    display_value = (grams_value / base_amount) if base_amount else grams_value
    display_id = f"recipe_portion_display_{portion_id}"
    select_id = f"recipe_portion_select_{portion_id}"
    grams_id = f"recipe_portion_grams_{portion_id}"
    side_unit_id = f"recipe_portion_side_{portion_id}"
    msg_id = f"recipe_portion_msg_{portion_id}"
    advanced_id = f"recipe_portion_advanced_{portion_id}"
    advanced_msg_id = f"recipe_portion_advanced_msg_{portion_id}"
    advanced_inner_id = f"recipe_portion_advanced_inner_{portion_id}"
    advanced_content_id = f"recipe_portion_advanced_content_{portion_id}"
    persist_key = f"recipe_portion_unit_{portion_id}"

    return Div(
        Div(
            Div(
                H3(_recipe_portion_name(portion), cls="text-left font-semibold"),
                P(_recipe_portion_meta(portion), cls="text-sm text-gray-700"),
                cls="flex flex-col gap-0.5 min-w-0",
            ),
            Div(
                Form(
                    Div(
                        Div(
                            Input(
                                type="text",
                                id=display_id,
                                name="amount_value",
                                inputmode="decimal",
                                value=f"{display_value:.2f}".replace(".", ","),
                                cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 w-16 text-base",
                                onclick="this.select()",
                                onchange=f"dbRecalcGrams('{display_id}','{select_id}','{grams_id}', true)",
                                onblur=f"dbRecalcGrams('{display_id}','{select_id}','{grams_id}', true)",
                            ),
                            Span("serving" if base_amount is not None else base_unit, id=side_unit_id, cls="text-xs text-gray-600 min-w-12 text-right"),
                            cls="flex items-center justify-end gap-2 w-full md:w-auto",
                        ),
                        Select(
                            *_detail_unit_options(base_amount, base_unit),
                            id=select_id,
                            name="amount_unit",
                            data_display_id=display_id,
                            data_grams_id=grams_id,
                            data_side_unit_id=side_unit_id,
                            data_persist_key=persist_key,
                            cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-xs w-full md:w-auto",
                            onchange=f"dbRecalcGrams('{display_id}','{select_id}','{grams_id}', true)",
                        ),
                        # Presentation-only: no `name`, it only fires the form's
                        # `change` trigger; the server converts `amount_value` +
                        # `amount_unit` itself (code_conventions.md 7.13).
                        Input(type="hidden", id=grams_id, value=f"{grams_value:.6f}"),
                        cls="flex flex-col items-end gap-2 md:flex-row md:items-center md:justify-end",
                    ),
                    Div(id=msg_id, cls="min-h-4 text-[10px] text-right text-gray-600"),
                    hx_post=f"/food/recipe/{recipe_id}/ingredient/{portion_id}/amount",
                    hx_trigger=f"change from:#{grams_id}",
                    hx_target=f"#{msg_id}",
                    hx_swap="innerHTML",
                    hx_push_url="false",
                    data_skip_page_loading="true",
                        cls="flex flex-col items-end gap-1",
                    ),
                    Div(
                        Button(
                            "Advanced",
                            type="button",
                            cls="web_button px-2 py-1 text-[11px]",
                            onclick=(
                                f"const el=document.getElementById('{advanced_id}');"
                                f"const inner=document.getElementById('{advanced_inner_id}');"
                                f"const content=document.getElementById('{advanced_content_id}');"
                                "if(!el) return;"
                                "const isOpen = el.getAttribute('data-open') === '1';"
                                "if(!isOpen){"
                                "el.setAttribute('data-open','1');"
                                "el.style.overflow='hidden';"
                                "var h = content ? content.scrollHeight : (inner ? inner.scrollHeight + 16 : 240);"
                                "el.style.maxHeight = (h + 2) + 'px';"
                                "el.style.opacity = '1';"
                                "setTimeout(function(){ if(el.getAttribute('data-open')==='1'){ el.style.overflow='visible'; } }, 320);"
                                "} else {"
                                "el.setAttribute('data-open','0');"
                                "el.style.overflow='hidden';"
                                "el.style.maxHeight = '0px';"
                                "el.style.opacity = '0';"
                                "}"
                            ),
                        ),
                    Button(
                        "Delete",
                        type="button",
                        cls="web_button px-2 py-1 text-[11px] border-red-300 text-red-700 hover:bg-red-50",
                        hx_post=f"/food/recipe/{recipe_id}/ingredient/{portion_id}/delete",
                        hx_target=f"#{_recipe_block_id(recipe_id)}",
                        hx_swap="outerHTML",
                        hx_push_url="false",
                        hx_disabled_elt="this",
                        data_skip_page_loading="true",
                        data_no_open="true",
                    ),
                    cls="flex items-center justify-end gap-2",
                ),
                cls="ml-3 flex flex-col items-end gap-1",
            ),
            cls="flex items-start justify-between",
        ),
        Div(
            _recipe_cooked_weight_field(recipe_id, portion),
            _recipe_move_field(recipe_id, portion, plates, plate_labels or {}),
            cls="flex flex-wrap items-center justify-between gap-2 empty:hidden",
        ),
        Div(
            Form(
                Div(
                    Div(
                        _searchable_compact_input(
                            name="cooking",
                            options=[s.value for s in CookingMethod],
                            value=(portion.cooking.value if portion.cooking else ""),
                            placeholder="Cooking",
                            allow_add=False,
                            autosave=True,
                        ),
                        cls="flex flex-col gap-1 min-w-0",
                    ),
                    Div(
                        _searchable_compact_input(
                            name="final_state",
                            options=[s.value for s in FoodPhysicalState],
                            value=(portion.final_state.value if portion.final_state else ""),
                            placeholder="Final state",
                            allow_add=False,
                            autosave=True,
                        ),
                        cls="flex flex-col gap-1 min-w-0",
                    ),
                    Div(
                        _searchable_compact_input(
                            name="conservation",
                            options=[s.value for s in ConservationMethod],
                            value=(portion.conservation.value if portion.conservation else ""),
                            placeholder="Conservation",
                            allow_add=False,
                            autosave=True,
                            ),
                            cls="flex flex-col gap-1 min-w-0 col-span-2 xl:col-span-1",
                        ),
                    id=advanced_inner_id,
                    cls="grid grid-cols-2 xl:grid-cols-3 gap-2",
                ),
                Div(id=advanced_msg_id, cls="text-[10px] text-right text-gray-600"),
                hx_post=f"/food/recipe/{recipe_id}/ingredient/{portion_id}/advanced",
                hx_trigger="submit",
                hx_target=f"#{advanced_msg_id}",
                hx_swap="innerHTML",
                hx_push_url="false",
                data_skip_page_loading="true",
                id=advanced_content_id,
                cls="flex flex-col gap-0 w-full max-w-full min-w-0",
            ),
            id=advanced_id,
            data_open="0",
            cls="w-full max-w-full relative z-0 transition-all duration-300 ease-out overflow-hidden",
            style="max-height:0px;opacity:0;",
        ),
        cls="web_container food_entry flex flex-col gap-1",
    )


def _recipe_add_ingredient_button(recipe_id: int, recipe_plate_id: int | None = None):
    query = f"?recipe_plate_id={recipe_plate_id}" if recipe_plate_id else ""
    return Button(
        "Add ingredient",
        type="button",
        cls="web_button px-3 py-2 text-xs",
        hx_get=f"/food/recipe/{recipe_id}/ingredients/form{query}",
        hx_target="#main_content",
        hx_swap="innerHTML",
        hx_push_url="true",
        **{"hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });"},
    )


def _recipe_plate_action(label: str, aria: str, path: str, recipe_id: int):
    return Button(
        label,
        type="button",
        aria_label=aria,
        cls="web_button px-2 py-1 text-xs",
        hx_post=path,
        hx_target=f"#{_recipe_block_id(recipe_id)}",
        hx_swap="outerHTML",
        hx_push_url="false",
        hx_disabled_elt="this",
        data_skip_page_loading="true",
    )


def _recipe_plate_header(recipe_id: int, plate, label: str):
    return Div(
        Input(
            type="text",
            name="name",
            value=plate.name or "",
            placeholder=label,
            maxlength=str(RECIPE_PLATE_NAME_MAX_LENGTH),
            aria_label="Plate name",
            cls="min-w-0 flex-1 font-semibold bg-transparent border-0 px-0 py-0 focus:outline-none",
            hx_post=f"/food/recipe/plate/{plate.id}/name",
            hx_trigger="change",
            hx_target=f"#{_recipe_block_id(recipe_id)}",
            hx_swap="outerHTML",
            hx_push_url="false",
            data_skip_page_loading="true",
        ),
        _recipe_plate_action("↑", "Move plate up", f"/food/recipe/plate/{plate.id}/up", recipe_id),
        _recipe_plate_action("↓", "Move plate down", f"/food/recipe/plate/{plate.id}/down", recipe_id),
        _recipe_plate_action("✕", "Delete plate", f"/food/recipe/plate/{plate.id}/delete", recipe_id),
        cls="flex items-center gap-1.5",
    )


def RecipeIngredientsBlock(recipe_id: int, portions: list, plates: list = (), can_edit: bool = False):
    """With one plate the concept does not show (§9.7). Repainted whole by every
    action that changes the plates or their ingredients."""
    by_plate = {plate.id: [p for p in portions if p.recipe_plate_id == plate.id] for plate in plates}
    labels = {
        plate.id: plate.name or derive_plate_name([_recipe_portion_name(p) for p in by_plate[plate.id]])
        for plate in plates
    }

    def row(portion):
        if not can_edit:
            return RecipeIngredientReadOnlyRow(portion)
        return RecipeIngredientRow(recipe_id, portion, plates, labels)

    several = len(plates) > 1
    sections = []
    for plate in plates:
        rows = by_plate[plate.id]
        if several and not rows and not can_edit:
            continue
        header = ""
        if several:
            header = (
                Div(
                    _recipe_plate_header(recipe_id, plate, labels[plate.id]),
                    _recipe_add_ingredient_button(recipe_id, plate.id),
                    cls="flex flex-col items-start gap-1.5 [&>:first-child]:w-full",
                )
                if can_edit
                else P(labels[plate.id], cls="font-semibold text-sm")
            )
        body = [row(portion) for portion in rows] or ([P("No ingredients in this plate.", cls="text-sm text-gray-500")] if several else [])
        sections.append(Div(header, *body, cls="flex flex-col gap-2"))
    if not any(by_plate.values()) and not several:
        sections = [P("No ingredients yet.", cls="text-sm text-gray-500")]
    return Div(
        Div(
            Div(
                H2("Ingredients", cls="font-semibold text-gray-900"),
                GuideHelpButton("recipe_preparation", "preparation"),
                cls="flex items-center gap-1.5",
            ),
            _recipe_add_ingredient_button(recipe_id) if can_edit and not several else "",
            cls="flex items-center justify-between gap-3",
        ),
        Div(*sections, cls="flex flex-col gap-3"),
        (
            Button(
                "+ Add plate",
                type="button",
                cls="web_button w-full px-2 py-2 text-sm border-dashed",
                hx_post=f"/food/recipe/{recipe_id}/plate",
                hx_target=f"#{_recipe_block_id(recipe_id)}",
                hx_swap="outerHTML",
                hx_push_url="false",
                hx_disabled_elt="this",
                data_skip_page_loading="true",
            )
            if can_edit and plates
            else ""
        ),
        id=_recipe_block_id(recipe_id),
        cls="flex flex-col gap-2 w-full",
    )


def RecipeNotesSection(notes: str | None):
    if not notes:
        return ""
    return Div(
        H2("Notes", cls="font-semibold text-gray-900"),
        P(notes, cls="web_container p-3 rounded-xl text-sm text-gray-900 whitespace-pre-line break-words"),
        cls="flex flex-col gap-2 w-full",
    )


def _amount_method_field(root_id: str, value: str | None):
    """`Amount from` of the food page, set before adding the food (U2, study
    §6.3). It starts on the food's `default_amount_method` and is what the new
    portion is born with (measurement_conventions.md §6.11). The empty option
    is "not given" (§6). The `Log food` button includes it by its id."""
    field_id = f"{root_id}_amount_method"
    return Div(
        Div(
            Div(
                Label("Amount from", cls="text-sm font-medium text-gray-800", **{"for": field_id}),
                GuideHelpButton("amount_method", "Amount from"),
                cls="flex items-center gap-1.5",
            ),
            P("How you get the amount this time.", cls="text-xs text-gray-500"),
            cls="flex flex-col min-w-0 flex-1",
        ),
        Select(
            Option(NOT_GIVEN_LABEL, value="", selected=not value),
            *[
                Option(label, value=method.value, selected=method.value == value)
                for method, label in AMOUNT_METHOD_LABELS.items()
            ],
            id=field_id,
            name="amount_method",
            cls=f"{INLINE_FIELD_CLS} max-w-[55%]",
        ),
        cls="web_container w-full px-4 py-3 flex items-center gap-3",
    )


def FoodDetailPage(
    user_id: int,
    entry_type: str,
    entry: dict,
    summary: dict,
    recipe_portions: list | None = None,
    recipe_plates: list | None = None,
    tags_block="",
    events: list | None = None,
    plate_options: list | None = None,
    selected_plate_id: int | None = None,
    can_edit: bool = True,
    can_delete: bool = False,
    is_archived: bool = False,
    can_archive: bool | None = None,
    can_publish: bool = False,
    is_published: bool = False,
    is_library: bool = False,
    has_serving: bool = True,
    cooking_factor: float | None = None,
):
    can_archive = can_edit if can_archive is None else can_archive
    # catalog and manual_intake are archived (§11.2.2, §11.2.3) under can_archive;
    # recipe keeps can_delete.
    archivable = entry_type in ("catalog", "manual_intake")
    can_remove = can_archive if archivable else can_delete
    base_unit = _display_base_unit(entry_type, entry)
    default_serving = summary.get("default_amount_g")
    # R3: the food page uses 100 g as the initial amount when the food has no
    # serving. It is not a serving: the `serving` option is not offered.
    if archivable and default_serving is None:
        serving_amount = None
        default_amount = INITIAL_AMOUNT_WITHOUT_SERVING_G
    else:
        serving_amount = max(1.0, _float_or_zero(default_serving) or 100.0)
        default_amount = serving_amount
    amount_display = f"{default_amount:.2f}".replace(".", ",")
    side_unit_label = "serving" if serving_amount is not None else base_unit
    per100 = summary.get("per100") or {}
    info_rows = summary.get("info_rows") or []
    subtitle = summary.get("subtitle") or ""
    state_text = None
    if archivable:
        if is_library:
            state_text = "General library"
        elif is_published:
            state_text = "Published"
        else:
            state_text = "Personal"
    if is_archived:
        state_text = (
            "Archived: removed from the catalog. You can keep using it."
            if entry_type == "catalog"
            else "Archived: removed from searches. You can keep using it."
        )
    edit_label = EDIT_LABELS[FoodEntryType(entry_type)] if can_edit else COPY_LABEL
    edit_href = {
        "catalog": f"/food/edit/catalog/{entry['id']}/form",
        "manual_intake": f"/food/edit/manual_intake/{entry['id']}/form",
        "recipe": f"/food/edit/recipe/{entry['id']}/form",
    }.get(entry_type, "/food")
    copy_confirm_id = f"copy_confirm_{entry_type}_{entry['id']}"
    delete_confirm_id = f"delete_confirm_{entry_type}_{entry['id']}"
    delete_title = {
        "catalog": "Archive food",
        "manual_intake": "Archive dish",
        "recipe": "Delete recipe",
    }.get(entry_type, "Delete item")
    delete_question = {
        "catalog": "This food will be removed from the catalog and from everyone's searches. Anyone who already has it in favorites or in a recipe can keep using it. This cannot be undone. Continue?",
        "manual_intake": "This dish will be removed from your lists and from everyone's searches. Anyone who already has it in favorites or in a recipe can keep using it. This cannot be undone. Continue?",
        "recipe": "This recipe will be deleted, also from the favorites of anyone who has it. The meals you already logged do not change. Continue?",
    }.get(entry_type, "Are you sure you want to delete this item?")

    root_id = f"food_detail_{entry_type}_{entry['id']}"
    display_id = f"{root_id}_display"
    grams_id = f"{root_id}_grams"
    select_id = f"{root_id}_select"
    side_unit_id = f"{root_id}_side_unit"
    plate_value_id = f"{root_id}_plate_value"
    plate_unit_id = f"{root_id}_plate_unit"
    plate_unit_btn_id = f"{root_id}_plate_unit_btn"
    plate_grams_id = f"{root_id}_plate_grams"
    plate_equivalent_id = f"{root_id}_plate_equivalent"
    leftovers_id = f"{root_id}_leftovers"
    msg_id = f"{root_id}_msg"
    advanced_id = f"{root_id}_advanced"
    advanced_inner_id = f"{root_id}_advanced_inner"
    form_id = f"{root_id}_form"
    persist_key = f"food_detail_amount_{entry_type}_{entry['id']}"

    recipe_mode = entry_type == "recipe"
    recipe_id = int(entry["id"]) if recipe_mode else 0
    # A recipe with several plates creates its own: it cannot go into a chosen one (§7.7).
    used_plates = {p.recipe_plate_id for p in recipe_portions or []}
    meal_selector = MealSelector(
        events or [],
        selected_id=(events[0].id if events else None),
        plate_options=plate_options,
        selected_plate_id=selected_plate_id,
        show_plates=not (recipe_mode and len(used_plates) > 1),
    )
    recipe_ingredients = (
        RecipeIngredientsBlock(recipe_id, recipe_portions or [], recipe_plates or [], can_edit) if recipe_mode else ""
    )
    action_button = (
        Button(
            "Add to meal",
            type="button",
            cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-black text-white border-black",
            **recipe_add_open_attrs(recipe_id),
        )
        if recipe_mode
        else Button(
            "Log food",
            type="button",
            cls="web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl bg-black text-white border-black",
            hx_post=f"/food/log/{entry_type}/{entry['id']}",
            hx_target=f"#{msg_id}",
            hx_swap="innerHTML",
            hx_push_url="false",
            hx_include=f"#meal_selector, #plate_selector, #{form_id}, #{root_id}_amount_method",
            data_skip_page_loading="true",
        )
    )
    # The whole amount into a new container, without plating (frontend §9.4).
    storage_buttons = (
        Div(
            *[
                Button(
                    f"Save to {STORAGE_LABELS[location].lower()}",
                    type="button",
                    cls="web_button w-full px-4 py-2 text-sm rounded-2xl",
                    hx_post=f"/food/fridge/store/{entry_type}/{entry['id']}",
                    hx_vals=json.dumps({"location": location.value}),
                    hx_target=f"#{msg_id}",
                    hx_swap="innerHTML",
                    hx_push_url="false",
                    hx_include=f"#{form_id}, #{root_id}_amount_method",
                    data_skip_page_loading="true",
                    **{"hx-disabled-elt": "this"},
                )
                for location in StorageLocation
            ],
            cls="w-full grid grid-cols-2 gap-3",
        )
        if archivable
        else ""
    )

    return Div(
        Div(_food_back_button(), cls="w-full flex justify-start"),
        Div(
            Div(
                Div(
                    H1(entry.get("name") or "-", cls="text-2xl font-bold text-gray-900"),
                    P(subtitle, cls="text-sm text-gray-600"),
                    (
                        P(state_text, cls="text-xs font-semibold text-amber-700")
                        if is_archived
                        else (P(state_text, cls="text-xs text-gray-500") if state_text else "")
                    ),
                    # The user's own tags on this entry (frontend_conventions.md §9.4.1).
                    tags_block,
                    cls="flex flex-col gap-1",
                ),
                (
                    Button(
                        Img(src="/images/content/delete.svg", alt="", cls="w-4 h-4"),
                        type="button",
                        aria_label=delete_title,
                        title=delete_title,
                        cls="""
                            web_button p-2
                            border-red-600/40 shadow-none
                            w-9 h-9
                            flex items-center justify-center
                            hover:bg-red-50
                        """,
                        style="color:#b91c1c;",
                        onclick=open_modal_js(delete_confirm_id),
                    )
                    if can_remove
                    else ""
                ),
                cls="flex items-start justify-between gap-3",
            ),
            cls="flex flex-col gap-1 w-full",
        ),
        meal_selector,
        "" if recipe_mode else Div(
            Form(
                Div(
                    Label(
                        "Food amount",
                        **{"for": display_id},
                        style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;",
                    ),
                    Input(
                        type="text",
                        id=display_id,
                        name="amount_value",
                        inputmode="decimal",
                        value=amount_display,
                        aria_label="Food amount",
                        cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 w-24 text-base",
                        onchange=f"dbFoodDetailRefresh('{root_id}')",
                        onclick="this.select()",
                    ),
                    Span(side_unit_label, id=side_unit_id, cls="text-xs text-gray-600"),
                    Label(
                        "Food unit selector",
                        **{"for": select_id},
                        style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;",
                    ),
                    Select(
                        *_detail_unit_options(serving_amount, base_unit),
                        id=select_id,
                        name="amount_unit",
                        data_display_id=display_id,
                        data_grams_id=grams_id,
                        data_side_unit_id=side_unit_id,
                        data_persist_key=f"food_detail_unit_{entry_type}_{entry['id']}",
                        aria_label="Food unit selector",
                        cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 text-xs md:text-sm justify-self-end",
                        onchange=f"dbFoodDetailOnUnitChange('{root_id}')",
                    ),
                    # Presentation-only helpers for food_detail.js: they have no
                    # `name`, so they are not submitted; the server converts the
                    # typed values itself (code_conventions.md 7.13).
                    Input(type="hidden", id=grams_id, value=f"{default_amount:.6f}"),
                    cls="flex items-center gap-2",
                ),
                Div(
                    Span("To plate", cls="text-xs text-gray-600"),
                    Label(
                        "Amount to plate",
                        **{"for": plate_value_id},
                        style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;",
                    ),
                    Input(
                        type="text",
                        id=plate_value_id,
                        name="plate_value",
                        inputmode="decimal",
                        value="100",
                        aria_label="Amount to plate",
                        cls="web_input bg-white/60 rounded-lg border border-gray-300 px-2 py-1 w-16 md:w-20 text-base",
                        oninput=f"dbFoodDetailPlateRefresh('{root_id}')",
                        onchange=f"dbFoodDetailPlateRefresh('{root_id}')",
                        onclick="this.select()",
                    ),
                    Button(
                        "%",
                        type="button",
                        id=plate_unit_btn_id,
                        aria_label="Toggle to plate unit",
                        onclick=f"dbFoodDetailTogglePlateUnit('{root_id}')",
                        cls="""
                            web_button px-2 py-1 text-sm min-w-10
                            border border-gray-300 bg-white/85
                        """,
                    ),
                    Input(type="hidden", id=plate_unit_id, name="plate_unit", value=AmountInputUnit.PERCENT.value),
                    Input(type="hidden", id=plate_grams_id, value=f"{default_amount:.6f}"),
                    cls="flex items-center gap-2",
                ),
                P(
                    f"Total amount (plate amount): {default_amount:.1f} ({default_amount:.1f}) {base_unit}",
                    id=plate_equivalent_id,
                    data_detail_plate_equivalent="true",
                    cls="text-xs text-gray-600",
                ),
                P(
                    f"Will be saved in fridge: {0.0:.1f} {base_unit}",
                    id=leftovers_id,
                    data_detail_leftovers="true",
                    cls="text-xs text-gray-600",
                ),
                (
                    Div(
                        Label(
                            "Cooked weight",
                            cls="text-xs text-gray-600",
                            **{"for": f"is_cooked_weight_{root_id}"},
                        ),
                        GuideHelpButton("cooked_weight", "Cooked weight"),
                        Input(
                            type="checkbox",
                            name="is_cooked_weight",
                            id=f"is_cooked_weight_{root_id}",
                            value="true",
                            cls=CHECKBOX_CLS,
                            onchange=f"dbFoodDetailPlateRefresh('{root_id}')",
                        ),
                        cls="flex items-center gap-2",
                    )
                    if entry_type == "catalog" and cooking_factor is not None
                    else ""
                ),
                Div(
                    Button(
                        "Advanced",
                        type="button",
                        cls="web_button px-2 py-1 text-[11px] w-fit",
                        onclick=(
                            f"const el=document.getElementById('{advanced_id}');"
                            f"const inner=document.getElementById('{advanced_inner_id}');"
                            "if(!el) return;"
                            "const isOpen = el.getAttribute('data-open') === '1';"
                            "if(!isOpen){"
                            "el.setAttribute('data-open','1');"
                            "el.style.overflow='hidden';"
                            "el.style.maxHeight = (inner ? (inner.scrollHeight + 8) : 220) + 'px';"
                            "el.style.opacity = '1';"
                            "setTimeout(function(){ if(el.getAttribute('data-open')==='1'){ el.style.overflow='visible'; } }, 320);"
                            "} else {"
                            "el.setAttribute('data-open','0');"
                            "el.style.overflow='hidden';"
                            "el.style.maxHeight = '0px';"
                            "el.style.opacity = '0';"
                            "}"
                        ),
                    ),
                    GuideHelpButton("preparation", "preparation"),
                    cls="flex items-center justify-end gap-1.5",
                ),
                Div(
                    Div(
                        Div(
                            _searchable_compact_input(
                                name="cooking",
                                options=[s.value for s in CookingMethod],
                                value="",
                                placeholder="Cooking",
                                allow_add=False,
                            ),
                            cls="flex flex-col gap-1",
                        ),
                        Div(
                            # Starts at the food's initial state (measurement §6.11).
                            _searchable_compact_input(
                                name="final_state",
                                options=[s.value for s in FoodPhysicalState],
                                value=(entry.get("initial_state") or "") if entry_type == "catalog" else "",
                                placeholder="Final state",
                                allow_add=False,
                            ),
                            cls="flex flex-col gap-1",
                        ),
                        Div(
                            _searchable_compact_input(
                                name="conservation",
                                options=[s.value for s in ConservationMethod],
                                value="",
                                placeholder="Conservation",
                                allow_add=False,
                            ),
                            cls="flex flex-col gap-1",
                        ),
                        # A fruit only (study §6.3): kept when logging it to a meal, not in a container.
                        Div(
                            _searchable_compact_input(
                                name="ripeness",
                                options=[r.value for r in Ripeness],
                                value="",
                                placeholder="Ripeness",
                                allow_add=False,
                            ),
                            cls="flex flex-col gap-1",
                        )
                        if entry_type == "catalog" and entry.get("category") == RIPENESS_CATEGORY.value
                        else None,
                        id=advanced_inner_id,
                        cls="grid grid-cols-2 md:grid-cols-3 gap-2",
                    ),
                    id=advanced_id,
                    data_open="0",
                    cls="w-full relative z-0 transition-all duration-300 ease-out overflow-hidden",
                    style="max-height:0px;opacity:0;",
                ),
                id=form_id,
                cls="web_container p-3 rounded-2xl flex flex-col gap-2",
            ),
            cls="w-full",
        ),
        _amount_method_field(root_id, entry.get("default_amount_method")) if not recipe_mode else "",
        Div(
            H2("Macros Summary", cls="font-semibold text-gray-900"),
            (
                RecipeMacrosGrid(recipe_id, summary)
                if recipe_mode
                else Div(
                    *_detail_macro_tiles(per100, default_amount),
                    id=f"{root_id}_macros",
                    data_stagger="true",
                    cls="grid grid-cols-2 md:grid-cols-3 gap-2",
                )
            ),
            cls="flex flex-col gap-2 w-full",
        ),
        Div(
            H2("Details", cls="font-semibold text-gray-900"),
            RecipeDetailsGrid(recipe_id, summary) if recipe_mode else _detail_info_rows(info_rows),
            cls="flex flex-col gap-2 w-full",
        ),
        recipe_ingredients,
        RecipeNotesSection(entry.get("notes")) if recipe_mode else "",
        *(RecipeAddModal() if recipe_mode else ()),
        Div(
            Button(
                edit_label,
                type="button",
                cls="""
                    web_button w-full px-4 py-3 text-sm md:text-base rounded-2xl
                    bg-white/85 text-gray-800 border border-gray-300
                    shadow-[0_6px_20px_rgba(17,24,39,0.08)]
                """,
                **(
                    {
                        "hx_get": edit_href,
                        "hx_target": "#main_content",
                        "hx_swap": "innerHTML",
                        "hx_push_url": "true",
                        "hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });",
                    }
                    if can_edit
                    else
                    {
                        "onclick": open_modal_js(copy_confirm_id),
                    }
                ),
            ),
            action_button,
            cls="w-full grid grid-cols-2 gap-3",
        ),
        storage_buttons,
        # Anyone who sees the item can copy it, the owner too (decision
        # 2026-10-27). Without edit rights the copy takes the Edit slot.
        (
            Div(
                Button(
                    COPY_LABEL,
                    type="button",
                    cls="""
                        web_button w-full px-4 py-2 text-sm rounded-2xl
                        bg-white/85 text-gray-800 border border-gray-300
                    """,
                    onclick=open_modal_js(copy_confirm_id),
                ),
                cls="w-full",
            )
            if can_edit
            else ""
        ),
        (
            Div(
                Button(
                    "Unpublish" if is_published else "Publish",
                    type="button",
                    cls="""
                        web_button w-full px-4 py-2 text-sm rounded-2xl
                        bg-white/85 text-gray-800 border border-gray-300
                    """,
                    hx_post=f"/food/{'unpublish' if is_published else 'publish'}/{entry_type}/{entry['id']}",
                    hx_swap="none",
                    data_skip_page_loading="true",
                ),
                cls="w-full",
            )
            if can_publish
            else ""
        ),
        ConfirmActionModal(
            modal_id=copy_confirm_id,
            title=COPY_LABEL,
            question=COPY_QUESTION,
            yes_button=modal_confirm_button(
                "Yes",
                danger=False,
                hx_post=f"/food/copy/{entry_type}/{entry['id']}",
                hx_swap="none",
                hx_push_url="false",
                data_skip_page_loading="true",
                onclick=close_modal_js(copy_confirm_id),
            ),
        ),
        (
            ConfirmActionModal(
                modal_id=delete_confirm_id,
                title=delete_title,
                question=delete_question,
                yes_button=modal_confirm_button(
                    "Yes",
                    danger=True,
                    hx_post=(
                        f"/food/archive/{entry_type}/{entry['id']}"
                        if archivable
                        else f"/food/delete/recipe/{entry['id']}"
                    ),
                    hx_swap="none",
                    hx_push_url="false",
                    data_skip_page_loading="true",
                    onclick=close_modal_js(delete_confirm_id),
                ),
            )
            if can_remove
            else ""
        ),
        Div(id=msg_id, cls="min-h-6 text-xs"),
        _searchable_autocomplete_bootstrap_script(),
        Script(src=asset_busted("/js/cart_units.js"), defer="defer"),
        Script(src=asset_busted("/js/food_detail.js"), defer="defer"),
        data_food_detail=None if recipe_mode else "true",
        # Without a saved copy: coming back from its ingredient search must show what
        # was added there (frontend_conventions.md §5, §6).
        hx_history="false" if recipe_mode else None,
        data_detail_display_id=display_id,
        data_detail_select_id=select_id,
        data_detail_grams_id=grams_id,
        data_detail_side_unit_id=side_unit_id,
        data_detail_plate_value_id=plate_value_id,
        data_detail_plate_unit_id=plate_unit_id,
        data_detail_plate_unit_btn_id=plate_unit_btn_id,
        data_detail_plate_grams_id=plate_grams_id,
        data_detail_plate_equivalent_id=plate_equivalent_id,
        data_detail_leftovers_id=leftovers_id,
        data_detail_base_unit=base_unit,
        # Only emit the factor when the food really has one; the calculation
        # treats a missing factor as neutral (decision 2026-09-24).
        data_detail_cooking_factor=(
            str(cooking_factor) if entry_type == "catalog" and cooking_factor is not None else None
        ),
        data_detail_persist_key=persist_key,
        data_hide_cart="true",
        # Its blocks come in one after another (frontend_conventions.md §10).
        data_stagger="true",
        id=root_id,
        cls="""
            flex flex-col items-center
            gap-4
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-xs
            w-full mx-auto
            md:mb-28 lg:mb-28 mb-24
        """,
    )


def RecipeIngredientPickerCard(food: dict, recipe_id: int, recipe_name: str, recipe_plate_id: int | None = None):
    query = f"?recipe_plate_id={recipe_plate_id}" if recipe_plate_id else ""
    add_path = f"/food/recipe/{recipe_id}/ingredients/add/{food['entry_type']}/{food['id']}{query}"
    subtitle = ""
    if food.get("entry_type") == "catalog":
        subtitle = (food.get("brand") or "").strip()
    elif food.get("entry_type") == "manual_intake":
        subtitle = (food.get("origin") or "").strip()
    return Div(
        Div(
            H1(Span(food["name"]), cls="text-left text-[15px] font-semibold leading-snug"),
            Div(Span(subtitle, cls="truncate"), cls="flex items-center text-xs text-gray-500 min-w-0") if subtitle else "",
            P(_entry_meta(food), cls="text-xs text-gray-700 mt-0.5"),
            cls="flex flex-col min-w-0",
        ),
        Div(
            AddButton(
                label="+",
                include_meal_selector=False,
                hx_post=add_path,
                hx_disabled_elt="this",
                data_recipe_name=recipe_name,
                **{
                    "hx-on:htmx:after-request": (
                        "if(event.detail.successful&&window.dbShowAppNotice)"
                        "window.dbShowAppNotice('Added to '+this.dataset.recipeName);"
                    )
                },
            ),
            cls="flex items-center gap-2 ml-3",
        ),
        cls="web_container food_entry rounded-2xl flex items-center justify-between",
    )


def _recipe_picker_filters(recipe_id: int):
    """`Food` and `Favs`: the same two lists of Food, without recipes (frontend §9.7)."""
    buttons = []
    for text, value in (("Food", "food"), ("Favs", "favs")):
        buttons.append(
            Button(
                text,
                type="button",
                cls=f"{FILTER_ITEM_CLS} {'bg-black text-white shadow-md' if value == 'food' else 'bg-transparent text-gray-700'}",
                data_recipe_picker_filter="true",
                data_skip_page_loading="true",
                hx_get=f"/food/recipe/{recipe_id}/ingredients/list",
                hx_target="#recipe-ingredient-list",
                hx_swap="innerHTML",
                hx_include="#recipe_ingredient_search_input, #recipe_ingredient_filter, #recipe_ingredient_plate",
                **{
                    "hx-on:click": (
                        f"document.getElementById('recipe_ingredient_filter').value='{value}';"
                        "document.querySelectorAll('[data-recipe-picker-filter]').forEach(function(btn){"
                        "btn.classList.remove('bg-black','text-white','shadow-md');"
                        "btn.classList.add('bg-transparent','text-gray-700');"
                        "});"
                        "this.classList.remove('bg-transparent','text-gray-700');"
                        "this.classList.add('bg-black','text-white','shadow-md');"
                    )
                },
            )
        )
    return Div(
        Input(type="hidden", id="recipe_ingredient_filter", name="filter", value="food"),
        *buttons,
        cls="flex items-center gap-1.5",
    )


def RecipeIngredientPickerPage(recipe_entry: dict, list_nodes: list, recipe_plate_id: int | None = None):
    """The search of Food to pick ingredients, without the island or the buttons to
    create or scan: only foods, never recipes (frontend_conventions.md §9.7)."""
    recipe_id = int(recipe_entry.get("id") or 0)
    return Div(
        # Inside the page, so the island comes back on its own when the page is left.
        Style("#floating_island{display:none}"),
        Div(
            Button(
                "Back to recipe",
                type="button",
                cls="web_button self-start px-3 py-1.5 text-sm",
                onclick=back_js(f"/food/item/recipe/{recipe_id}"),
            ),
            cls="w-full flex justify-start",
        ),
        H1(f"Add ingredient to {recipe_entry.get('name') or 'recipe'}", cls="text-xl font-bold text-gray-900 w-full"),
        RecipeIngredientSearchInput(recipe_id),
        _recipe_picker_filters(recipe_id),
        _recipe_picker_plate_input(recipe_plate_id),
        Div(
            *list_nodes,
            id="recipe-ingredient-list",
            cls="w-full flex flex-col items-center gap-2",
        ),
        data_hide_cart="true",
        cls="""
            flex flex-col items-center
            gap-4
            md:mt-7 lg:mt-7 mt-2
            md:w-md lg:w-md w-xs
            w-full mx-auto
            md:mb-28 lg:mb-28 mb-24
        """,
    )
