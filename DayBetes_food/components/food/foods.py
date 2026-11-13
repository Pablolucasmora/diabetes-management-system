import json
from dataclasses import dataclass

from fasthtml.common import *

from DayBetes_food.components.cart.cart_shared import CHECKBOX_CLS
from DayBetes_food.components.data_sources import ciqual_attribution, off_attribution
from DayBetes_food.components.injection_zone import asset_busted
from DayBetes_food.components.navigation import back_js
from DayBetes_food.components.food.food_actions import (
    COPY_LABEL,
    COPY_QUESTION,
    EDIT_LABELS,
    FoodActionsTrigger,
    favorite_button_id,
    food_card_id,
)
from DayBetes_food.components.food.food_shared import (
    AMOUNT_METHOD_LABELS,
    FORM_FIELD_CLS,
    INLINE_FIELD_CLS,
    MACROS_SOURCE_LABELS,
    NOT_GIVEN_LABEL,
    STORAGE_LABELS,
)
from DayBetes_food.components.food.rescue import RescueModal, rescue_open_attrs
from DayBetes_food.components.modal import (
    ModalLayer,
    close_modal_js,
    ConfirmActionModal,
    modal_confirm_button,
    modal_secondary_button,
    open_modal_js,
)
from DayBetes_food.domain.catalog import (
    CATALOG_BARCODE_MAX_LENGTH,
    CATALOG_NAME_MAX_LENGTH,
    CatalogItemRead,
)
from DayBetes_food.domain.food import (
    FOOD_SUBTYPE_MAX_LENGTH,
    INITIAL_AMOUNT_WITHOUT_SERVING_G,
)
from DayBetes_food.components.food.recipe_add import RecipeAddModal, recipe_add_open_attrs
from DayBetes_food.components.stats.stats_shared import MEAL_TYPE_LABELS
from DayBetes_food.domain.intake_plate import derive_plate_name
from DayBetes_food.domain.recipe import RECIPE_MEAL_TYPES, RECIPE_NAME_MAX_LENGTH, RECIPE_NOTES_MAX_LENGTH, RecipeRead
from DayBetes_food.domain.recipe_plate import RECIPE_PLATE_NAME_MAX_LENGTH
from DayBetes_food.domain.manual_intake import (
    MANUAL_INTAKE_DESCRIPTION_MAX_LENGTH,
    MANUAL_INTAKE_NAME_MAX_LENGTH,
    MANUAL_INTAKE_ORIGIN_MAX_LENGTH,
    ManualIntakeRead,
)
from DayBetes_food.domain.constants import (
    NOVA_MAX,
    NOVA_MIN,
    YUKA_MAX,
    YUKA_MIN,
    AmountInputUnit,
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodEntryType,
    FoodPhysicalState,
    AmountMethod,
    GlycemicIndex,
    MacrosSource,
    Nutriscore,
    NutrientEntryMode,
    PortionOrigin,
    Ripeness,
    StorageLocation,
)
from DayBetes_food.domain.nutrition import SMART_MACROS_MAX_LENGTH
from DayBetes_food.domain.portion_detail import RIPENESS_CATEGORY
from DayBetes_food.time_utils import to_local


def catalog_entry_view(item: CatalogItemRead) -> dict:
    """The only adapter from CatalogItemRead to the dict the shared food
    components expect (debt: they will become dataclasses when manual_intake and
    recipe have theirs)."""
    return {
        "entry_type": "catalog",
        "id": item.id,
        "name": item.name,
        "brand": item.brand,
        "brand_id": item.brand_id,
        "category": item.category.value,
        "initial_state": item.initial_state.value if item.initial_state else None,
        "nutriscore": item.nutriscore.value if item.nutriscore else None,
        "subtype": item.subtype,
        "nova": item.nova,
        "yuka": item.yuka,
        "default_portion": item.default_portion,
        "calories_100g": item.calories_100g,
        "carbs_100g": item.carbs_100g,
        "sugars_100g": item.sugars_100g,
        "fats_100g": item.fats_100g,
        "saturated_100g": item.saturated_100g,
        "proteins_100g": item.proteins_100g,
        "fiber_100g": item.fiber_100g,
        "caffeine": item.caffeine,
        "alcohol": item.alcohol,
        "barcode": item.barcode,
        "cooking_factor": item.cooking_factor,
        "macros_source": item.macros_source.value if item.macros_source else None,
        "default_amount_method": item.default_amount_method.value if item.default_amount_method else None,
        "macros_confidence": item.macros_confidence,
        "is_published": item.is_published,
        "created_by": item.created_by,
        "origin_root_id": item.origin_root_id,
        "deleted_at": item.deleted_at,
        "favorite": item.is_favorite,
        "can_edit": item.can_edit,
        "is_listable": item.is_listable,
    }


def manual_intake_entry_view(item: ManualIntakeRead) -> dict:
    """The only adapter from ManualIntakeRead to the dict the shared food
    components expect (same debt as catalog_entry_view)."""
    return {
        "entry_type": "manual_intake",
        "id": item.id,
        "name": item.name,
        "origin": item.origin,
        "description": item.description,
        "subtype": item.subtype,
        "default_portion": item.default_portion,
        "calories_100g": item.calories_100g,
        "carbs_100g": item.carbs_100g,
        "sugars_100g": item.sugars_100g,
        "fats_100g": item.fats_100g,
        "saturated_100g": item.saturated_100g,
        "proteins_100g": item.proteins_100g,
        "fiber_100g": item.fiber_100g,
        "caffeine": item.caffeine,
        "alcohol": item.alcohol,
        "glycemic_index": item.glycemic_index.value if item.glycemic_index else None,
        "ig_confidence": item.ig_confidence,
        "macros_confidence": item.macros_confidence,
        "macros_source": item.macros_source.value if item.macros_source else None,
        "default_amount_method": item.default_amount_method.value if item.default_amount_method else None,
        "is_published": item.is_published,
        "created_by": item.created_by,
        "origin_root_id": item.origin_root_id,
        "deleted_at": item.deleted_at,
        "favorite": item.is_favorite,
        "can_edit": item.can_edit,
        "is_listable": item.is_listable,
    }


def recipe_entry_view(item: RecipeRead) -> dict:
    """The only adapter from RecipeRead to the dict the shared food components
    expect (same debt as catalog_entry_view)."""
    return {
        "entry_type": "recipe",
        "id": item.id,
        "created_by": item.user_id,
        "origin_root_id": item.origin_root_id,
        "name": item.name,
        "meal_type": item.meal_type.value if item.meal_type else None,
        "extra_meal_types": [meal_type.value for meal_type in item.extra_meal_types],
        "notes": item.notes,
        "servings": item.servings,
        "is_published": item.is_published,
        "favorite": item.is_favorite,
        "can_edit": item.can_edit,
    }


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


def meal_option_label(event) -> str:
    """Text of a meal in the meal selector. Also sent with `mealCreated`, so that the
    option the page adds reads the same as the one a reload would draw (§7.7)."""
    local_meal_time = to_local(event.meal_time)
    return event.name or (f"Meal {local_meal_time.strftime('%H:%M')}" if local_meal_time else f"Meal {event.id}")


def MealSelector(
    events: list,
    selected_id: int = None,
    plate_options: list = None,
    selected_plate_id: int = None,
    show_plates: bool = True,
):
    """`show_plates=False` for a recipe with several plates, which creates its own (§7.7)."""
    options = []
    for event in events:
        options.append(
            Option(
                meal_option_label(event),
                value=str(event.id),
                selected=(event.id == selected_id),
            )
        )

    if not options:
        options = [Option("- No meals yet -", value="", cls="text-gray-500/50")]

    options.append(Option("New Meal", value="0", selected=(selected_id == 0)))

    return Div(
        Label("Add to", cls="web_section_label shrink-0", **{"for": "meal_selector"}),
        Select(
            *options,
            id="meal_selector",
            name="intake_event_id",
            data_skip_page_loading="true",
            aria_label="Meal selector",
            # Changing the meal changes its plates: the plate selector is
            # redrawn with the chosen event's plates (§7.7).
            **(
                {
                    "hx_get": "/food/plate_selector",
                    "hx_trigger": "change",
                    "hx_target": "#plate_selector_box",
                    "hx_swap": "innerHTML",
                    "hx_include": "this",
                }
                if show_plates
                else {}
            ),
            **{
                "hx-on:change": (
                    "var box=document.getElementById('meal_name_input');"
                    "var input=document.getElementById('meal_name_input_text');"
                    "if(!box||!input) return;"
                    "if(this.value==='0'){"
                    "box.classList.remove('hidden');"
                    "setTimeout(function(){input.focus();},0);"
                    "} else {"
                    "box.classList.add('hidden');"
                    "input.value='';"
                    "}"
                )
            },
            style="color: gray" if not events else "",
            cls="""
            bg-white border border-line px-2 py-1.5
            md:text-sm lg:text-sm text-xs
            rounded-lg focus:outline-none
            lg:w-40 md:w-40 w-32
            cursor-pointer
            """,
        ),
        Div(
            Div(
                Input(
                    placeholder="Meal name",
                    name="meal_name",
                    id="meal_name_input_text",
                    autofocus="autofocus" if selected_id == 0 else None,
                    data_skip_page_loading="true",
                    cls="""
                    border-[1px] px-2 py-1
                    md:text-sm lg:text-sm text-base
                    shadow-sm rounded-md focus:outline-none
                    border-gray-300 w-full
                    """,
                    hx_post="/create_named_event",
                    hx_trigger="keyup[keyCode==13]",
                    hx_target="#meal_name_input",
                    hx_swap="none",
                    hx_push_url="false",
                    hx_include="this",
                    **on_after("add_meal_btn")
                ),
                Button(
                    "Add",
                    id="add_meal_btn",
                    data_skip_page_loading="true",
                    cls="""
                    border-[1px] px-2 py-1
                    md:text-sm lg:text-sm text-xs
                    shadow-sm rounded-md cursor-pointer
                    border-gray-300 hover:bg-gray-200
                    transition-colors duration-300
                    """,
                    hx_post="/create_named_event",
                    hx_target="#meal_name_input",
                    hx_swap="none",
                    hx_push_url="false",
                    hx_include="#meal_name_input_text",
                    **on_after()
                ),
                cls="flex gap-2 w-full",
            ),
            id="meal_name_input",
            cls=f"lg:w-40 md:w-40 w-32 bg-transparent {'hidden' if selected_id != 0 else ''}",
        ),
        (
            Div(
                PlateSelector(plate_options or [], selected_id=selected_plate_id),
                id="plate_selector_box",
            )
            if show_plates
            else ""
        ),
        cls="flex items-center justify-center gap-2  md:w-xl lg:w-xl w-xs mb-3",
    )


def PlateSelector(plate_options: list, selected_id: int = None):
    """Plate selector, next to the meal selector (§7.7).

    `plate_options` are `(id, label)` pairs already resolved by the route: a
    plate's shown name can be derived from its ingredients
    (measurement_conventions.md §4.6.3), and that is a query, which does not
    belong in the component (§1.4).

    There is always a specific plate selected —the last one used, resolved by
    the route— so that the control does not lie about where the food will
    land (§6). With no event selected, no control is drawn.
    """
    if not plate_options:
        return ""

    options = []
    for plate_id, label in plate_options:
        options.append(Option(label, value=str(plate_id), selected=(plate_id == selected_id)))
    options.append(Option("+ New plate", value="0", selected=(selected_id == 0)))

    return Div(
        Select(
            *options,
            id="plate_selector",
            name="plate_id",
            data_skip_page_loading="true",
            aria_label="Plate selector",
            cls="""
            bg-white border border-line px-2 py-1.5
            md:text-sm lg:text-sm text-xs
            rounded-lg focus:outline-none
            lg:w-40 md:w-40 w-32
            cursor-pointer
            """,
        ),
        cls="flex flex-col",
    )


# Every control of the Food header sends the whole state of the list.
_FOOD_LIST_INCLUDE = (
    "#food_search_input, #food_filter, #food_search_mode, #food_food_mode, "
    "#food_favs_mode, #food_recipes_mode, #food_recipes_meal"
)


def _mode_tabs(group: str, tabs: tuple[tuple[str, str], ...], *, hidden: bool = True):
    """Underlined tabs of one pill of the Food header (frontend_conventions.md §9.3).
    The first one starts selected; choosing one writes its value in
    #food_<group>_mode and reloads the list."""
    width = {2: "w-1/2", 3: "w-1/3"}[len(tabs)]
    columns = []
    for index, (label, value) in enumerate(tabs):
        selected = index == 0
        align = "text-left" if index == 0 else ("text-right" if index == len(tabs) - 1 else "text-center")
        columns.append(
            Div(
                Button(
                    label,
                    type="button",
                    data_skip_page_loading="true",
                    **{f"data_{group}_mode_btn": "true", f"data_{group}_mode_value": value},
                    cls=(
                        "inline-flex px-0 pb-1.5 text-sm "
                        f"{'font-bold text-black' if selected else 'font-medium text-gray-400'} "
                        f"{align} transition-colors duration-150 cursor-pointer"
                    ),
                    style=(
                        "transform: translateX(0); border-bottom: 2px solid "
                        f"{'#111827' if selected else 'transparent'};"
                    ),
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include=_FOOD_LIST_INCLUDE,
                    **{
                        "hx-on:click": (
                            f"var mode='{value}';"
                            f"var modeInput=document.getElementById('food_{group}_mode');"
                            "if(modeInput){modeInput.value=mode;}"
                            f"document.querySelectorAll('[data-{group}-mode-btn]').forEach(function(btn){{"
                            "btn.classList.remove('text-black','font-bold');"
                            "btn.classList.add('text-gray-400','font-medium');"
                            "btn.style.borderBottom='2px solid transparent';"
                            "});"
                            "this.classList.remove('text-gray-400');"
                            "this.classList.remove('font-medium');"
                            "this.classList.add('text-black','font-bold');"
                            "this.style.borderBottom='2px solid #111827';"
                        ),
                    },
                ),
                cls=f"{width} flex items-end justify-center",
            )
        )
    return Div(
        *columns,
        id=f"food_{group}_tabs",
        cls=f"{'hidden ' if hidden else ''}w-full flex items-end justify-between mt-2",
    )


# The pills of the Food header (frontend_conventions.md §9.3), as `(label, filter)`.
FOOD_FILTERS = (("Search", "all"), ("Food", "food"), ("Recipes", "recipes"), ("Favs", "favs"), ("Fridge", "fridge"))


def Filters(selected: str = "all"):
    """`selected` is the pill the page opens on: `fridge` from the button of the
    home page (§9.2), `all` otherwise."""
    buttons = []
    for text, value in FOOD_FILTERS:
        buttons.append(
            Button(
                text,
                cls=(
                    f"{FILTER_ITEM_CLS} {'bg-black text-white shadow-md' if value == selected else 'bg-transparent text-gray-700'}"
                    # The Fridge pill looks frosted (frontend_conventions.md §9.8).
                    f"{' food_filter_fridge' if value == 'fridge' else ''}"
                ),
                data_food_filter_btn="true",
                data_filter_value=value,
                data_skip_page_loading="true",
                hx_get="/food/list",
                hx_target="#food-list",
                hx_swap="innerHTML",
                hx_include=_FOOD_LIST_INCLUDE,
                **{
                    "hx-on:click": (
                        f"document.getElementById('food_filter').value='{value}';"
                        "document.querySelectorAll('[data-food-filter-btn]').forEach(function(btn){"
                        "btn.classList.remove('bg-black','text-white','shadow-md');"
                        "btn.classList.add('bg-transparent','text-gray-700');"
                        "});"
                        "this.classList.remove('bg-transparent','text-gray-700');"
                        "this.classList.add('bg-black','text-white','shadow-md');"
                        "var searchTabs=document.getElementById('food_search_tabs');"
                        "if(searchTabs){"
                        "if(this.dataset.filterValue==='all'){"
                        "searchTabs.classList.remove('hidden');"
                        "}else{"
                        "searchTabs.classList.add('hidden');"
                        "}"
                        "}"
                        "var foodTabs=document.getElementById('food_food_tabs');"
                        "if(foodTabs){"
                        "if(this.dataset.filterValue==='food'){"
                        "foodTabs.classList.remove('hidden');"
                        "}else{"
                        "foodTabs.classList.add('hidden');"
                        "}"
                        "}"
                        "var favsTabs=document.getElementById('food_favs_tabs');"
                        "if(favsTabs){"
                        "if(this.dataset.filterValue==='favs'){"
                        "favsTabs.classList.remove('hidden');"
                        "}else{"
                        "favsTabs.classList.add('hidden');"
                        "}"
                        "}"
                        "var recipesTabs=document.getElementById('food_recipes_tabs');"
                        "if(recipesTabs){"
                        "if(this.dataset.filterValue==='recipes'){"
                        "recipesTabs.classList.remove('hidden');"
                        "}else{"
                        "recipesTabs.classList.add('hidden');"
                        "}"
                        "}"
                        # Only the lists that have something to filter offer the button (§9.3).
                        "var filtersButton=document.getElementById('food_filters_button');"
                        "if(filtersButton){"
                        "filtersButton.classList.toggle('hidden',this.dataset.filterValue!=='recipes');"
                        "}"
                    ),
                },
            )
        )

    return Div(
        Input(type="hidden", id="food_filter", name="filter", value=selected),
        Input(type="hidden", id="food_search_mode", name="search_mode", value="recommended"),
        Input(type="hidden", id="food_food_mode", name="food_mode", value="catalog"),
        Input(type="hidden", id="food_favs_mode", name="favs_mode", value="catalog"),
        Input(type="hidden", id="food_recipes_mode", name="recipes_mode", value="mine"),
        Input(type="hidden", id="food_recipes_meal", name="meal_type", value=""),
        Div(
            *buttons,
            cls="""
                relative
                flex items-center justify-between
                md:gap-3 lg:gap-3 gap-1.5
                w-full
                rounded-full
            """,
        ),
        _mode_tabs("search", (("Recommended", "recommended"), ("Global", "global")), hidden=selected != "all"),
        _mode_tabs("food", (("Catalog", "catalog"), ("Manual", "manual"))),
        _mode_tabs("recipes", (("Mine", "mine"), ("Discover", "discover"))),
        _mode_tabs("favs", (("Catalog", "catalog"), ("Manual", "manual"), ("Recipes", "recipes"))),
        cls="md:w-xl lg:w-xl w-xs transition-all",
    )


def _food_filters_button():
    """Inside the search box, on the right. It opens the filters pop-up (§9.3)."""
    return Button(
        Img(src="/images/ui/filter.svg", alt="", cls="w-5 h-5"),
        # Marks that a filter is on: from outside the pop-up it would not show.
        Span(
            id="food_filters_active",
            cls="hidden absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-danger border border-white",
        ),
        type="button",
        id="food_filters_button",
        aria_label="Filters",
        title="Filters",
        cls="""
            hidden absolute right-1.5 top-1/2 -translate-y-1/2
            web_button web_button_primary
            rounded-xl w-9 h-9
            flex items-center justify-center
        """,
        onclick="dbOpenFoodFilters()",
    )


def _meal_type_pill(meal, *, checked: bool = False, **input_attrs):
    """A pill that can be on or off: several meal types can be chosen at once."""
    return Label(
        Input(type="checkbox", value=meal.value, checked=checked, cls="peer sr-only", **input_attrs),
        Span(
            MEAL_TYPE_LABELS.get(meal.value, meal.value),
            cls="""
                block px-3 py-1.5 rounded-full text-sm cursor-pointer
                bg-control border border-line text-stone-900
                peer-checked:bg-ink peer-checked:border-ink peer-checked:text-white
                peer-focus-visible:ring-2 peer-focus-visible:ring-ink/40
                transition-colors
            """,
        ),
    )


def FoodFiltersModal():
    """The filters of the lists of Food. New filters go here: a control in the pop-up
    (a draft) and a hidden field that the list requests include (static/js/food_filters.js)."""
    return (
        ModalLayer(
            Div(
                P("Filters", cls="text-lg font-semibold"),
                modal_secondary_button("Reset", aria_label="Remove every filter", onclick="dbResetFoodFilters()"),
                cls="flex items-center justify-between gap-3",
            ),
            Fieldset(
                Legend("Meal type", cls="text-xs text-gray-600 mb-1.5"),
                Div(
                    *[_meal_type_pill(meal, data_food_filter_meal="true") for meal in RECIPE_MEAL_TYPES],
                    cls="flex flex-wrap gap-1.5",
                ),
            ),
            Div(
                modal_secondary_button("Cancel", onclick=close_modal_js("food_filters_modal")),
                modal_confirm_button(
                    "Confirm",
                    hx_get="/food/list",
                    hx_target="#food-list",
                    hx_swap="innerHTML",
                    hx_include=(
                        "#food_search_input, #food_filter, #food_search_mode, #food_food_mode, "
                        "#food_favs_mode, #food_recipes_mode, #food_recipes_meal"
                    ),
                    data_skip_page_loading="true",
                    **{"hx-on:click": "dbApplyFoodFilters()"},
                ),
                cls="flex items-center gap-2 justify-end",
            ),
            modal_id="food_filters_modal",
        ),
        Script(src=asset_busted("/js/food_filters.js"), defer="defer"),
    )


def SearchInput():
    return Div(
        Input(
            inputmode="text",
            placeholder="What did you eat?",
            name="search",
            id="food_search_input",
            data_skip_page_loading="true",
            cls="""
                web_input
                border border-line inset-shadow-none
                rounded-2xl
                w-full
                transition-all
                pl-4 pr-13 py-3 text-sm
            """,
            hx_get="/food/list",
            hx_target="#food-list",
            hx_trigger="keyup changed delay:500ms",
            hx_include="#food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode, #food_recipes_meal",
            hx_swap="innerHTML",
        ),
        _food_filters_button(),
        cls="relative md:w-xl lg:w-xl w-xs",
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
    return Script(
        """
        (function () {
          if (window.__dbSearchableAutocompleteBootstrapped) return;
          window.__dbSearchableAutocompleteBootstrapped = true;

          function normalize(v) { return String(v || "").trim(); }
          function storageKeyFor(input) {
            if (!input) return "";
            var form = input.form;
            var action = form && form.getAttribute ? (form.getAttribute("hx-post") || form.getAttribute("action") || "") : "";
            return "dbSearchableValue::" + window.location.pathname + window.location.search + "::" + (input.name || "") + "::" + action;
          }
          function persistValue(input) {
            if (!input || !window.localStorage) return;
            var key = storageKeyFor(input);
            if (!key) return;
            window.localStorage.setItem(key, String(input.value || ""));
          }
          function restoreValue(input) {
            if (!input || !window.localStorage) return;
            var key = storageKeyFor(input);
            if (!key) return;
            var saved = window.localStorage.getItem(key);
            if (saved == null) return;
            if (!normalize(input.value)) {
              input.value = saved;
            }
          }
          function escapeHtml(v) {
            return String(v || "")
              .replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#39;");
          }

          function bindOne(root) {
            if (!root || root.dataset.searchableBound === "1") return;
            root.dataset.searchableBound = "1";

            var input = root.querySelector("[data-searchable-input='true']");
            var box = root.querySelector("[data-searchable-suggestions='true']");
            var addedFlag = root.querySelector("[data-searchable-added-flag='true']");
            if (!input || !box) return;
            // The open list has to rise above the cards below it, which
            // means raising its glass ancestors too (dropdown_layer.js).
            function raise(on) {
              if (window.dbRaiseDropdown) window.dbRaiseDropdown(root, on);
            }

            var options = [];
            try { options = JSON.parse(root.dataset.searchableOptions || "[]"); }
            catch (_) { options = []; }
            var allowAdd = root.dataset.searchableAllowAdd === "1";
            var caseMode = root.dataset.searchableCaseMode || "lower";
            restoreValue(input);

            function formatByCaseMode(v) {
              var text = normalize(v);
              if (!text) return "";
              if (caseMode === "title") {
                var words = text.toLowerCase().split(/\\s+/);
                for (var i = 0; i < words.length; i += 1) {
                  var w = words[i];
                  if (!w) continue;
                  words[i] = w.charAt(0).toUpperCase() + w.slice(1);
                }
                return words.join(" ");
              }
              return text.toLowerCase();
            }

            function closeBox() {
              box.style.display = "none";
              box.innerHTML = "";
              raise(false);
            }

            function setAddedFlag(value) {
              if (!addedFlag) return;
              addedFlag.value = value ? "1" : "0";
            }

            function similarityScore(nameLower, qLower) {
              if (!qLower) return 0;
              if (nameLower === qLower) return 1000;
              if (nameLower.indexOf(qLower) === 0) return 800;
              if (nameLower.indexOf(qLower) !== -1) return 600;

              var qSet = new Set(qLower.split(""));
              var nSet = new Set(nameLower.split(""));
              var inter = 0;
              qSet.forEach(function (ch) { if (nSet.has(ch)) inter += 1; });
              var union = new Set([].concat(Array.from(qSet), Array.from(nSet))).size || 1;
              return Math.floor((inter / union) * 300);
            }

            function render() {
              var q = normalize(input.value);
              var qLower = q.toLowerCase();
              var matches = [];

              for (var i = 0; i < options.length; i += 1) {
                var name = normalize(options[i]);
                if (!name) continue;
                var lower = name.toLowerCase();
                var score = similarityScore(lower, qLower);
                if (!q || score > 0) matches.push({ name: name, score: score });
              }

              matches.sort(function (a, b) {
                if (b.score !== a.score) return b.score - a.score;
                return a.name.localeCompare(b.name);
              });

              var rows = [];
              for (var j = 0; j < matches.length; j += 1) {
                var label = matches[j].name;
                var safe = escapeHtml(label);
                rows.push(
                  "<li class='border-b border-gray-200'>" +
                  "<button type='button' data-searchable-pick='" +
                  safe +
                  "' class='w-full text-left px-3 py-2 bg-white hover:bg-gray-200 text-sm text-gray-800 transition-colors'>" +
                  safe +
                  "</button></li>"
                );
              }

              var exactExists = options.some(function (x) {
                return normalize(x).toLowerCase() === qLower;
              });

              if (allowAdd && q && !exactExists) {
                rows.push(
                  "<li class='border-b border-gray-200'>" +
                  "<button type='button' data-searchable-add='true' class='w-full text-left px-3 py-2 bg-white hover:bg-gray-200 text-sm font-semibold text-gray-800 transition-colors'>Add: '" +
                  escapeHtml(q) +
                  "'</button></li>"
                );
              }

              if (rows.length) {
                box.innerHTML = (
                  "<div data-searchable-scroll='true' class='p-0 max-h-44 overflow-y-auto' " +
                  "style='-webkit-overflow-scrolling:touch;overscroll-behavior:contain;touch-action:pan-y;'>" +
                  "<ul>" + rows.join("") + "</ul></div>"
                );
                var items = box.querySelectorAll("li");
                if (items.length > 0) items[items.length - 1].classList.remove("border-b", "border-gray-200");
                var scrollArea = box.querySelector("[data-searchable-scroll='true']");
                if (scrollArea) {
                  scrollArea.addEventListener("wheel", function (ev) { ev.stopPropagation(); }, { passive: true });
                  scrollArea.addEventListener("touchmove", function (ev) { ev.stopPropagation(); }, { passive: true });
                }
                raise(true);
              } else {
                box.innerHTML = "";
                raise(false);
              }
              box.style.display = rows.length ? "block" : "none";
            }

            box.addEventListener("click", function (ev) {
              var target = ev.target;
              if (!target) return;
              if (target.dataset && target.dataset.searchableAdd === "true") {
                var q = normalize(input.value);
                if (!q) return;
                var qLower = q.toLowerCase();
                var exists = options.some(function (x) { return normalize(x).toLowerCase() === qLower; });
                var formatted = formatByCaseMode(q);
                if (!exists) options.push(formatted);
                input.value = formatted;
                setAddedFlag(true);
                persistValue(input);
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
                input.dispatchEvent(new CustomEvent("db-searchable-commit", { bubbles: true }));
                setAddedFlag(true);
                closeBox();
                return;
              }
              var pick = target.dataset ? target.dataset.searchablePick : "";
              if (pick) {
                input.value = pick;
                setAddedFlag(false);
                persistValue(input);
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
                input.dispatchEvent(new CustomEvent("db-searchable-commit", { bubbles: true }));
                closeBox();
              }
            });

            input.addEventListener("focus", render);
            input.addEventListener("input", function () {
              setAddedFlag(false);
              persistValue(input);
              render();
            });
            input.addEventListener("change", function () { persistValue(input); });
            input.addEventListener("keydown", function (ev) {
              if (ev.key === "Escape") closeBox();
            });
            document.addEventListener("click", function (ev) {
              var target = ev.target;
              if (!root.contains(target)) {
                closeBox();
                return;
              }
              if (target !== input && !box.contains(target)) {
                closeBox();
              }
            });
          }

          function bindAll() {
            var roots = document.querySelectorAll("[data-searchable-autocomplete='true']");
            for (var i = 0; i < roots.length; i += 1) bindOne(roots[i]);
          }

          if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", bindAll);
          } else {
            bindAll();
          }
          document.body.addEventListener("htmx:afterSwap", bindAll);
        })();
        """
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


def _tristate_select(label: str, name: str, selected: bool | None, labels: dict, help_text: str = ""):
    """Three states, three options (frontend §6): "" = unknown, "true", "false".
    The real stored state is the one marked selected (§7.14)."""
    select_id = f"field_{name}"
    return Div(
        _label_with_help(label, help_text or f"What to select in {label}", for_id=select_id),
        Select(
            Option("- Unknown", value="", selected=selected is None),
            Option(labels[True], value="true", selected=selected is True),
            Option(labels[False], value="false", selected=selected is False),
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


def QuickCreateButtons(assistant_enabled: bool = False):
    # Solid, not glass: they sit inside the glass header, and Safari paints
    # coloured seams with a backdrop-filter nested in another one
    # (frontend_conventions.md §8).
    menu_button_cls = """
        bg-surface border border-line-soft cursor-pointer
        shadow-[0_4px_14px_rgba(80,60,40,0.14)]
        h-12 w-12 md:h-14 md:w-14 p-3 md:p-4
        rounded-3xl md:rounded-4xl
        flex items-center justify-center
        transition-transform duration-150
        hover:scale-[1.04]
        active:scale-95
    """
    menu_panel_cls = """
        absolute top-full right-0 z-10 mt-3 bg-surface
        w-[min(52vw,calc(100vw-1.5rem))]
        min-w-[24rem]
        rounded-3xl
        border border-line-soft
        shadow-[0_12px_40px_rgba(80,60,40,0.18)]
        p-3
        grid grid-cols-2 gap-2
        auto-rows-fr
    """
    # Solid options: no glass inside a panel (frontend_conventions.md §8).
    option_button_cls = """
        w-full h-full min-h-0 px-3 py-3 rounded-2xl
        text-left cursor-pointer
        bg-control border border-line hover:bg-line-soft
        transition-colors duration-150
        flex flex-col items-start justify-between gap-1
    """
    return Div(
        Div(
            Div(
                # Opens the rescue pop-up (frontend_conventions.md §9.6).
                Button(
                    Img(src="/images/content/power_icon.svg", alt="", cls="h-6 w-6"),
                    type="button",
                    aria_label="Log a rescue",
                    cls=menu_button_cls,
                    id="food_rescue_button",
                    **rescue_open_attrs(),
                ),
                RescueModal(),
                cls="relative flex justify-start",
            ),
            # The assistant, as a tab hanging from the top edge of the page:
            # it is pulled up over the header's top padding and has no top
            # border, only rounded bottom corners (frontend_conventions.md §9.3).
            Button(
                Img(src="/images/ui/Logo_DiaBot.svg", alt="", cls="h-8 md:h-11 w-auto max-w-full"),
                type="button",
                aria_label="Tell the assistant",
                data_food_assistant_tab="true",
                cls="""
                    self-start flex-none w-40 md:w-56 min-w-0 mx-3 md:mx-5
                    -mt-2 md:-mt-7 h-14 md:h-[5.25rem] pt-2 md:pt-7 pb-3 md:pb-5 px-3
                    bg-surface border border-t-0 border-line-soft
                    shadow-[0_4px_14px_rgba(80,60,40,0.14)]
                    rounded-b-2xl md:rounded-b-3xl
                    text-sm font-semibold text-gray-900 cursor-pointer
                    flex items-center justify-center
                    transition-transform duration-150 active:scale-[0.98]
                """,
                hx_get="/assistant",
                hx_target="#main_content",
                hx_push_url="true",
                **{"hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });"},
            ) if assistant_enabled else "",
            Div(
                Button(
                    Img(src="/images/ui/plus_icon.svg", alt="", cls="h-6 w-6"),
                    type="button",
                    aria_label="Open add menu",
                    cls=menu_button_cls,
                    id="food_quick_create_toggle",
                    aria_controls="food_quick_create_menu",
                    aria_expanded="false",
                ),
                Div(
                    Button(
                        Div(
                            Span("New food", cls="font-semibold text-gray-900"),
                            Span("Packaged, with its label", cls="text-[11px] text-gray-500"),
                            cls="flex flex-col items-start gap-0.5",
                        ),
                        type="button",
                        cls=option_button_cls,
                        hx_get="/food/create/catalog/form",
                        hx_target="#main_content",
                        hx_swap="innerHTML",
                        hx_push_url="true",
                    ),
                    Button(
                        Div(
                            Span("Quick add", cls="font-semibold text-gray-900"),
                            Span("Only carbs, one-off", cls="text-[11px] text-gray-500"),
                            cls="flex flex-col items-start gap-0.5",
                        ),
                        type="button",
                        cls=option_button_cls,
                        hx_get="/food/quick_add/form",
                        hx_target="#main_content",
                        hx_swap="innerHTML",
                        hx_push_url="true",
                        **{"hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });"},
                    ),
                    Button(
                        Div(
                            Span("New dish", cls="font-semibold text-gray-900"),
                            Span("Homemade or eaten out", cls="text-[11px] text-gray-500"),
                            cls="flex flex-col items-start gap-0.5",
                        ),
                        type="button",
                        cls=option_button_cls,
                        hx_get="/food/create/manual_intake/form",
                        hx_target="#main_content",
                        hx_swap="innerHTML",
                        hx_push_url="true",
                    ),
                    Button(
                        Div(
                            Span("New recipe", cls="font-semibold text-gray-900"),
                            Span("Several foods together", cls="text-[11px] text-gray-500"),
                            cls="flex flex-col items-start gap-0.5",
                        ),
                        type="button",
                        cls=option_button_cls,
                        hx_get="/food/create/recipe/form",
                        hx_target="#main_content",
                        hx_swap="innerHTML",
                        hx_push_url="true",
                    ),
                    Button(
                        Div(
                            Div(
                                Span("Scanner", cls="font-semibold text-gray-900"),
                                Span("Open the barcode scanner", cls="text-[11px] text-gray-500"),
                                cls="flex flex-col items-start gap-0.5",
                            ),
                            cls="flex flex-col items-start gap-2",
                        ),
                        type="button",
                        cls=option_button_cls,
                        hx_get="/scanner",
                        hx_target="#main_content",
                        hx_swap="innerHTML",
                        hx_push_url="true",
                    ),
                    id="food_quick_create_menu",
                    role="menu",
                    aria_label="Create food menu",
                    cls=menu_panel_cls,
                    style=(
                        "width:min(22rem,calc(100vw - 1.5rem));min-width:10rem;"
                        "visibility:hidden; opacity:0; transform:translateY(-8px) scale(0.97);"
                        "pointer-events:none;"
                        "transition: opacity 180ms ease, transform 180ms ease;"
                    ),
                ),
                cls="relative flex justify-end",
            ),
            cls="relative w-full flex items-center justify-between",
        ),
        # Above the menu scrim of the header (food_main.py), so the buttons
        # and their panels stay sharp while everything else is blurred.
        cls="relative z-[2] w-full flex justify-end px-3 md:px-5 lg:px-5 mb-2 md:mb-0",
        data_quick_create_root="true",
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
            "macros_source",
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
                _macros_confidence_select(None),
                _amount_method_default_select(None),
            ),
            open_=details_open,
        ),
        _favorite_row(),
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
):
    """Reusable dish (code_conventions.md §11.2.3): name and carbs required."""
    result_id = "create_manual_result_page"
    form = Form(
        _form_header("New dish", _name_title_input("", "Name of the dish", MANUAL_INTAKE_NAME_MAX_LENGTH)),
        _form_section(
            "About the dish",
            _manual_origin_input(origin_options),
            _searchable_autocomplete_input(
                "Subtype",
                "subtype",
                subtype_options or [],
                help_text="Specific subtype. Optional.",
                allow_add=True,
                maxlength=FOOD_SUBTYPE_MAX_LENGTH,
            ),
            step=1,
        ),
        _form_section(
            "Nutrition",
            _nutrient_mode_select("manual"),
            _manual_portion_input(),
            _smart_macros_block(
                "manual",
                label="Macros per 100 g",
                label_total="Macros of one serving",
            ),
            P("Carbs are required: write 0hc if the dish has no carbs.", cls="text-xs text-gray-500 md:col-span-2 -mt-1"),
            step=2,
        ),
        _optional_section(
            "More details",
            "Description, glycemic response, caffeine, data quality",
            _form_subgroup("Description", _manual_description_input(), cols=1),
            _form_subgroup(
                "Glycemic response",
                _glycemic_index_select(None),
                _confidence_select(
                    "IG confidence",
                    "ig_confidence",
                    None,
                    "How sure you are about the glycemic index. Needs a glycemic index.",
                ),
            ),
            _form_subgroup(
                "Other nutrients",
                _manual_nutrient_input("Caffeine (mg/100 g)", "Caffeine (mg in total)", "caffeine"),
                _manual_nutrient_input("Alcohol (g/100 g)", "Alcohol (g in total)", "alcohol"),
            ),
            _form_subgroup(
                "Data quality",
                _macros_source_select(None),
                _macros_confidence_select(None),
                _amount_method_default_select(None),
            ),
        ),
        _favorite_row(),
        _form_submit("Create dish"),
        Script(src=asset_busted("/js/manual_intake_form.js"), defer="defer"),
        hx_post="/food/create/manual_intake",
        hx_target=f"#{result_id}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_draft_key="food_form_create_manual_page",
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
        _favorite_row(),
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


def FavoriteButton(entry_type: FoodEntryType, entry_id: int, favorite: bool):
    """The star says the state it asks for, worked out here from the saved row,
    so repeating a request cannot undo it (frontend §9.3.2)."""
    icon = "/images/content/fav_icon.svg" if favorite else "/images/content/not_fav_icon.svg"
    label = "Remove from favorites" if favorite else "Add to favorites"
    return Button(
        Img(src=icon, cls="w-4 h-4", alt=""),
        id=favorite_button_id(entry_type, entry_id),
        type="button",
        aria_label=label,
        title=label,
        cls="""
            web_button p-2
            bg-transparent border-transparent shadow-none
            w-9 h-9
            flex items-center justify-center
            hover:bg-control
        """,
        hx_post=f"/food/favorite/{entry_type.value}/{entry_id}",
        hx_vals=json.dumps({"favorite": "false" if favorite else "true"}),
        hx_target="this",
        hx_swap="outerHTML",
        hx_trigger="click consume",
        hx_push_url="false",
        hx_disabled_elt="this",
        **{"hx-on:click": "event.stopPropagation();"},
        data_skip_page_loading="true",
        data_no_open="true",
    )


def AddButton(label: str = "+", include_meal_selector: bool = True, **attrs):
    if include_meal_selector:
        # The plate selector travels with the meal selector: the food has to
        # know which plate it goes to, not only which event (§7.7). If it is
        # not being shown, the selector does not exist and the request goes
        # out without plate_id, which is exactly "the default plate".
        attrs.setdefault("hx_include", "#meal_selector, #plate_selector")
    else:
        attrs.pop("hx_include", None)
    attrs.setdefault("data_skip_page_loading", "true")
    attrs.setdefault("hx_target", "this")
    attrs.setdefault("hx_trigger", "click consume")
    attrs.setdefault("hx_push_url", "false")
    attrs.setdefault("data_no_open", "true")
    attrs.setdefault("type", "button")
    button_cls = attrs.pop(
        "cls",
        """
            web_button web_button_primary
            rounded-xl
            w-9 h-9
            flex items-center justify-center
            transition-colors duration-300
            text-lg leading-none
        """,
    )
    return Button(
        label,
        cls=button_cls,
        hx_swap=attrs.pop("hx_swap", "none"),
        **{key: value + attrs.pop(key, "") for key, value in on_after(reload_page=False).items()},
        **attrs,
    )


def _entry_meta(food):
    if food["entry_type"] in ("catalog", "manual_intake"):
        carbs = food.get("carbs_100g")
        return f"{carbs if carbs is not None else '-'} g carbs / 100 g"
    return "Recipe"


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
            H2("Ingredients", cls="font-semibold text-gray-900"),
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
            Label("Amount from", cls="text-sm font-medium text-gray-800", **{"for": field_id}),
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
                    cls="flex justify-end",
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


def FoodCard(food):
    entry_type = FoodEntryType(food["entry_type"])
    add_path = f"/add_food/{food['id']}"
    add_label = "+"
    if food["entry_type"] == "manual_intake":
        add_path = f"/add_manual_intake/{food['id']}"

    archived_badge = (
        Span("Archived", cls="text-[10px] font-semibold text-amber-700")
        if food.get("entry_type") in ("catalog", "manual_intake") and food.get("deleted_at") is not None
        else ""
    )
    owned_badge = (
        Span("Mine", cls="text-[10px] font-semibold text-muted bg-control rounded-full px-1.5 py-0.5")
        if food.get("is_owned")
        else ""
    )
    subtitle = ""
    if food.get("entry_type") == "catalog":
        subtitle = (food.get("brand") or "").strip()
    elif food.get("entry_type") == "manual_intake":
        subtitle = (food.get("origin") or "").strip()

    title_node = H1(
        Span(food["name"]),
        archived_badge,
        cls="text-left text-[15px] font-semibold leading-snug flex flex-wrap items-center gap-1.5",
    )
    subtitle_node = (
        Div(
            Span(subtitle, cls="truncate") if subtitle else "",
            owned_badge,
            cls="flex items-center gap-1.5 text-xs text-gray-500 min-w-0",
        )
        if subtitle or owned_badge
        else ""
    )

    return Div(
        Div(
            title_node,
            subtitle_node,
            P(_entry_meta(food), cls="text-xs text-gray-700 mt-0.5"),
            cls="flex flex-col min-w-0",
        ),
        Div(
            # Shown on archived foods too: they appear because they are favorites
            # and the user must be able to remove them (§11.2.2).
            FavoriteButton(entry_type, food["id"], bool(food.get("favorite"))),
            (
                AddButton(label=add_label, **recipe_add_open_attrs(food["id"]))
                if food["entry_type"] == "recipe"
                else AddButton(label=add_label, hx_post=add_path)
            ),
            cls="flex items-center gap-2 ml-3",
        ),
        FoodActionsTrigger(entry_type, food["id"]),
        id=food_card_id(entry_type, food["id"]),
        hx_get=f"/food/item/{food['entry_type']}/{food['id']}",
        hx_target="#main_content",
        hx_swap="innerHTML",
        hx_push_url="true",
        hx_trigger="click[!event.target.closest('[data-no-open]')]",
        **{"hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });"},
        # Long press or right click: actions pop-up (§9.3.1, static/js/food_actions.js).
        data_food_actions="true",
        cls="web_container food_entry rounded-2xl flex items-center justify-between cursor-pointer",
    )


def _external_food_card(name, subtitle, carbs, fats, proteins, form_query):
    macros = f"{carbs:.1f} g carbs · {fats:.1f} g fat · {proteins:.1f} g protein per 100 g"
    return Div(
        Div(
            H1(Span(name), cls="text-left text-[15px] font-semibold leading-snug"),
            Div(Span(subtitle, cls="truncate"), cls="flex items-center text-xs text-gray-500 min-w-0") if subtitle else "",
            P(macros, cls="text-xs text-gray-700 mt-0.5"),
            cls="flex flex-col min-w-0",
        ),
        hx_get=f"/food/create/catalog/form?{form_query}",
        hx_target="#main_content",
        hx_swap="innerHTML",
        hx_push_url="true",
        **{"hx-on:click": "window.scrollTo({ top: 0, behavior: 'auto' });"},
        cls="web_container food_entry rounded-2xl flex items-center justify-between cursor-pointer",
    )


def off_product_cards(products, extra_query: str = "") -> list:
    """`extra_query` keeps the recipe the food will go into (frontend §9.7)."""
    return [
        _external_food_card(
            p.name, p.brand, p.carbs_100g, p.fats_100g, p.proteins_100g, f"barcode={p.code}{extra_query}"
        )
        for p in products
    ]


def ciqual_food_cards(foods, extra_query: str = "") -> list:
    return [
        _external_food_card(
            f.name_es, None, f.carbs_100g, f.fats_100g, f.proteins_100g, f"ciqual={f.code}{extra_query}"
        )
        for f in foods
    ]


def ExternalFoodSection(title: str, cards: list, load_more, attribution) -> list:
    """A source's results with their own button, so loading more never pushes
    the next section away (frontend §9.3)."""
    if not cards:
        return []
    return [
        H2(title, cls="web_section_label md:w-md lg:w-md w-xs mt-2"),
        *cards,
        *([load_more] if load_more is not None else []),
        attribution,
    ]


def FoodSectionsContent(foods):
    grouped = {"catalog": [], "recipe": [], "manual_intake": []}
    for food in foods:
        entry_type = food.get("entry_type")
        if entry_type in grouped:
            grouped[entry_type].append(food)

    sections = []
    for entry_type, title in (
        ("catalog", "Food"),
        ("recipe", "Recipes"),
        ("manual_intake", "Manual"),
    ):
        items = grouped[entry_type]
        if not items:
            continue
        sections.append(H2(title, cls="web_section_label md:w-md lg:w-md w-xs mt-2"))
        sections.extend(FoodCard(item) for item in items)
    return sections


def FoodList(foods):
    if not foods:
        return Div(H2("No items", cls="text-gray-600"), cls="flex flex-col items-center")

    return Div(
        *FoodSectionsContent(foods),
        id="food-list",
        cls="flex flex-col items-center md:gap-3 lg:gap-3 gap-2 mt-4 transition-all duration-150 ease-out",
    )
