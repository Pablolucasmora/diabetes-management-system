"""The Food page: meal and plate selectors, search, tabs and filters, the create buttons and the cards of the list (frontend_conventions.md §7.7, §9.3)."""

import json
from dataclasses import dataclass
from urllib.parse import urlencode
from fasthtml.common import *
from DayBetes_food.components.injection_zone import asset_busted
from DayBetes_food.components.food.food_actions import (
    FoodActionsTrigger,
    favorite_button_id,
    food_card_id,
)
from DayBetes_food.components.food.menus import MenusIconButton
from DayBetes_food.components.food.rescue import RescueModal, rescue_open_attrs
from DayBetes_food.components.modal import (
    ModalLayer,
    close_modal_js,
    modal_confirm_button,
    modal_secondary_button,
)
from DayBetes_food.components.food.recipe_add import recipe_add_open_attrs
from DayBetes_food.components.stats.stats_shared import MEAL_TYPE_LABELS
from DayBetes_food.domain.recipe import RECIPE_MEAL_TYPES
from DayBetes_food.domain.constants import FoodEntryType
from DayBetes_food.time_utils import to_local
from DayBetes_food.components.food.food_widgets import (
    FILTER_ITEM_CLS,
    on_after,
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


def _mode_tabs(group: str, tabs: tuple[tuple[str, str], ...], *, selected_value: str, hidden: bool = True):
    """Underlined tabs of one pill of the Food header (frontend_conventions.md §9.3).
    `selected_value` starts selected; choosing one writes its value in
    #food_<group>_mode and reloads the list."""
    width = {2: "w-1/2", 3: "w-1/3"}[len(tabs)]
    columns = []
    for index, (label, value) in enumerate(tabs):
        selected = value == selected_value
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
FOOD_FILTERS = (
    ("Search", "all"),
    ("Food", "food"),
    ("Recipes", "recipes"),
    ("Favs", "favs"),
    ("Fridge", "fridge"),
    # Not drawn as a pill: ReviewBanner opens it (§9.3, decision 2026-11-21).
    ("To review", "review"),
)
FOOD_FILTER_REVIEW = "review"

# The tabs of each pill, as `(label, value)`; the first is the default.
FOOD_SEARCH_TABS = (("Recommended", "recommended"), ("Global", "global"))
FOOD_FOOD_TABS = (("Catalog", "catalog"), ("Manual", "manual"))
FOOD_RECIPES_TABS = (("Mine", "mine"), ("Discover", "discover"))
FOOD_FAVS_TABS = (("Catalog", "catalog"), ("Manual", "manual"), ("Recipes", "recipes"))


@dataclass(frozen=True)
class FoodView:
    """What the Food page shows: its pill, the tab of each pill and the meal types
    of the filters pop-up. It travels in the URL of /food (frontend_conventions.md §5)."""

    filter: str = "all"
    search_mode: str = FOOD_SEARCH_TABS[0][1]
    food_mode: str = FOOD_FOOD_TABS[0][1]
    favs_mode: str = FOOD_FAVS_TABS[0][1]
    recipes_mode: str = FOOD_RECIPES_TABS[0][1]
    meal_type: str = ""


def ReviewBanner(view: FoodView, review_count: int):
    """Under the search, while there are provisional foods (frontend §9.3): it opens
    the To review list, as Home's reminder does. Not a pill: it would crowd them."""
    if not review_count and view.filter != FOOD_FILTER_REVIEW:
        return None
    text = "1 food to review" if review_count == 1 else f"{review_count} foods to review"
    return Button(
        Span(
            Span("!", cls="w-5 h-5 shrink-0 rounded-full bg-amber-100 text-amber-800 text-xs font-bold flex items-center justify-center"),
            Span(text, cls="max-md:text-xs text-sm font-semibold text-amber-800 truncate"),
            cls="flex items-center gap-2 min-w-0",
        ),
        # Always one line: on a narrow phone the text shrinks and truncates (§9.3).
        Span("Review ›", cls="text-xs font-semibold text-gray-700 shrink-0 whitespace-nowrap"),
        type="button",
        id="food_review_banner",
        data_skip_page_loading="true",
        hx_get="/food/list",
        hx_target="#food-list",
        hx_swap="innerHTML",
        hx_include=_FOOD_LIST_INCLUDE,
        **{
            "hx-on:click": (
                f"document.getElementById('food_filter').value='{FOOD_FILTER_REVIEW}';"
                "this.classList.add('food_review_active');"
                "document.querySelectorAll('[data-food-filter-btn]').forEach(function(btn){"
                "btn.classList.remove('bg-black','text-white','shadow-md');"
                "btn.classList.add('bg-transparent','text-gray-700');"
                "});"
                "['search','food','favs','recipes'].forEach(function(group){"
                "var tabs=document.getElementById('food_'+group+'_tabs');"
                "if(tabs){tabs.classList.add('hidden');}"
                "});"
                "var filtersButton=document.getElementById('food_filters_button');"
                "if(filtersButton){filtersButton.classList.add('hidden');}"
            )
        },
        cls=(
            "web_container md:w-xl lg:w-xl w-xs rounded-2xl px-4 max-md:px-3 py-2 flex items-center justify-between gap-2 whitespace-nowrap cursor-pointer"
            + (" food_review_active" if view.filter == FOOD_FILTER_REVIEW else "")
        ),
    )


def Filters(view: FoodView = FoodView()):
    """`view` is the state the page opens on (frontend_conventions.md §5): the pill,
    its tab and the filters, as the URL of /food gives them."""
    selected = view.filter
    buttons = []
    for text, value in FOOD_FILTERS:
        if value == FOOD_FILTER_REVIEW:
            # Not a pill: the banner under the search opens it (ReviewBanner, §9.3).
            continue
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
                        "var reviewBanner=document.getElementById('food_review_banner');"
                        "if(reviewBanner){reviewBanner.classList.remove('food_review_active');}"
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
        Input(type="hidden", id="food_search_mode", name="search_mode", value=view.search_mode),
        Input(type="hidden", id="food_food_mode", name="food_mode", value=view.food_mode),
        Input(type="hidden", id="food_favs_mode", name="favs_mode", value=view.favs_mode),
        Input(type="hidden", id="food_recipes_mode", name="recipes_mode", value=view.recipes_mode),
        Input(type="hidden", id="food_recipes_meal", name="meal_type", value=view.meal_type),
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
        _mode_tabs("search", FOOD_SEARCH_TABS, selected_value=view.search_mode, hidden=selected != "all"),
        _mode_tabs("food", FOOD_FOOD_TABS, selected_value=view.food_mode, hidden=selected != "food"),
        _mode_tabs("recipes", FOOD_RECIPES_TABS, selected_value=view.recipes_mode, hidden=selected != "recipes"),
        _mode_tabs("favs", FOOD_FAVS_TABS, selected_value=view.favs_mode, hidden=selected != "favs"),
        cls="md:w-xl lg:w-xl w-xs transition-all",
    )


def _food_filters_button(view: FoodView):
    """Inside the search box, on the right. It opens the filters pop-up (§9.3)."""
    return Button(
        Img(src="/images/ui/filter.svg", alt="", cls="w-5 h-5"),
        # Marks that a filter is on: from outside the pop-up it would not show.
        Span(
            id="food_filters_active",
            cls=f"{'' if view.meal_type else 'hidden '}absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-danger border border-white",
        ),
        type="button",
        id="food_filters_button",
        aria_label="Filters",
        title="Filters",
        cls=f"""
            {'' if view.filter == 'recipes' else 'hidden'} absolute right-1.5 top-1/2 -translate-y-1/2
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


def SearchInput(view: FoodView = FoodView()):
    """The search box and, on its right, the saved menus (§9.13)."""
    return Div(_search_box(view), MenusIconButton(), cls="flex items-center gap-2 md:w-xl lg:w-xl w-xs")


def _search_box(view: FoodView):
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
            hx_trigger="input changed delay:300ms",
            # A newer search drops the one still running.
            hx_sync="this:replace",
            hx_include="#food_filter, #food_search_mode, #food_food_mode, #food_favs_mode, #food_recipes_mode, #food_recipes_meal",
            hx_swap="innerHTML",
        ),
        _food_filters_button(view),
        cls="relative flex-1 min-w-0",
    )


def QuickCreateButtons():
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
            # Free space: DiaBot lives in the island now (frontend_conventions.md §9.3).
            Div(cls="flex-1"),
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
            p-2 w-9 h-9 rounded-lg
            bg-transparent hover:bg-control
            flex items-center justify-center
            cursor-pointer active:scale-95 transition-transform duration-150
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


def FoodCard(food, open_url: str | None = None):
    """`open_url`: where a tap goes, if not the food's page (the To review list
    opens the edit form, §9.3)."""
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
    if food.get("needs_review"):
        # A provisional food of the assistant (code_conventions.md §8.12).
        archived_badge = Span(
            "To review", cls="text-[10px] font-semibold text-amber-800 bg-amber-50 rounded-full px-1.5 py-0.5"
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
        hx_get=open_url or f"/food/item/{food['entry_type']}/{food['id']}",
        hx_target="#main_content",
        hx_swap="innerHTML",
        hx_push_url="true",
        hx_trigger="click[!event.target.closest('[data-no-open]')]",
        # Fetched while the finger rests on it (frontend_conventions.md §12).
        data_preload="true",
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


def ReviewListContent(entries: list):
    """The To review list (frontend_conventions.md §9.3): the provisional foods and
    dishes, drawn as the cards of every other list, so a tap, the + and the long
    press behave the same; their "To review" badge says what is pending."""
    if not entries:
        return P("Nothing to review.", cls="text-sm text-gray-600 text-center py-8 md:w-md lg:w-md w-xs")
    cards = [
        FoodCard(
            {
                "entry_type": entry.entry_type.value,
                "id": entry.entry_id,
                "name": entry.name,
                "brand" if entry.entry_type == FoodEntryType.CATALOG else "origin": entry.subtitle,
                "carbs_100g": entry.carbs_100g,
                "favorite": entry.is_favorite,
                "needs_review": True,
                "is_owned": True,
            },
            # Straight to the form: reviewing is editing; saving clears the mark
            # and comes back here (§9.3).
            open_url=f"/food/edit/{entry.entry_type.value}/{entry.entry_id}/form?{urlencode({'return_to': 'review'})}",
        )
        for entry in entries
    ]
    return Div(
        Span("Added by DiaBot while you ate", cls="web_section_label px-1"),
        *cards,
        cls="flex flex-col items-center md:gap-3 lg:gap-3 gap-2 w-full",
    )
