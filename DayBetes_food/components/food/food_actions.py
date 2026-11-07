"""Actions pop-up of a food row (frontend_conventions.md §9.3.1).

Holding a row of the Food list (or a right click on it) opens one
`ModalLayer` whose body is requested from the server each time, so the
options follow what the user can do with that food now. Its views (the
menu, the recipe picker and the copy confirmation) are swapped inside the
same body; static/js/food_actions.js detects the gesture, opens the layer,
animates the change of view and closes it after an add. The star of a row
uses the same pop-up to confirm a removal that loses access (§9.3.2).
"""

import json

from fasthtml.common import *

from DayBetes_food.components.food.food_shared import FORM_FIELD_CLS, STORAGE_LABELS
from DayBetes_food.components.modal import (
    MODAL_NAME_CLS,
    ModalLayer,
    close_modal_js,
    modal_confirm_button,
    modal_icon_button,
    modal_secondary_button,
)
from DayBetes_food.domain.constants import AmountInputUnit, FoodEntryType, StorageLocation
from DayBetes_food.domain.food import INITIAL_AMOUNT_WITHOUT_SERVING_G
from DayBetes_food.domain.food_entry import FoodEntrySummary

FOOD_ACTIONS_MODAL_ID = "food_actions_modal"
FOOD_ACTIONS_BODY_ID = "food_actions_modal_body"
FOOD_ACTIONS_STORE_MESSAGE_ID = "food_actions_store_message"

# Shared with the detail page (§9.4), so both name the same action the same way.
EDIT_LABELS = {
    FoodEntryType.CATALOG: "Edit food",
    FoodEntryType.MANUAL_INTAKE: "Edit manual",
    FoodEntryType.RECIPE: "Edit recipe",
}
COPY_LABEL = "Make a copy"
COPY_QUESTION = "A personal copy will be created and opened for editing. Continue?"

# Options are solid `control` rows: the pop-up card is a solid panel (§8).
_OPTION_CLS = """
    w-full text-left px-3 py-2.5 rounded-xl cursor-pointer
    bg-control border border-line hover:bg-line-soft
    transition-colors flex items-center justify-between gap-3
    text-sm font-medium text-gray-900
"""


def food_card_id(entry_type: FoodEntryType, entry_id: int) -> str:
    return f"food_card_{entry_type.value}_{entry_id}"


def favorite_button_id(entry_type: FoodEntryType, entry_id: int) -> str:
    return f"favorite_{entry_type.value}_{entry_id}"


def food_actions_url(entry_type: FoodEntryType, entry_id: int) -> str:
    return f"/food/actions/{entry_type.value}/{entry_id}"


def ActionsTrigger(url: str):
    """Hidden request source inside a row of the Food list. static/js/food_actions.js
    fires `dbFoodActions` on it after a long press or a right click; being
    its own element, the request skips the page loading layer without
    affecting the row's own click. `url` returns the first view of the pop-up."""
    return Span(
        hidden=True,
        hx_get=url,
        hx_trigger="dbFoodActions",
        hx_target=f"#{FOOD_ACTIONS_BODY_ID}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_skip_page_loading="true",
        data_food_actions_trigger="true",
    )


def FoodActionsTrigger(entry_type: FoodEntryType, entry_id: int):
    return ActionsTrigger(food_actions_url(entry_type, entry_id))


def FoodActionsModal():
    """The pop-up layer. Its body arrives with `GET /food/actions/...`."""
    return ModalLayer(
        Div(id=FOOD_ACTIONS_BODY_ID, cls="flex flex-col gap-3"),
        modal_id=FOOD_ACTIONS_MODAL_ID,
        card_cls="gap-3 max-h-[88vh] overflow-y-auto",
    )


def actions_view_attrs(url: str) -> dict:
    """Swaps another view of the pop-up into its body (also the first view, from a
    button outside it: the pop-up opens when the view is in). `data-food-actions-view`
    is what static/js/food_actions.js animates (§10)."""
    return {
        "hx_get": url,
        "hx_target": f"#{FOOD_ACTIONS_BODY_ID}",
        "hx_swap": "innerHTML",
        "hx_push_url": "false",
        "data_skip_page_loading": "true",
        "data_food_actions_view": "true",
    }


def actions_header(title: str, subtitle: str = "", back_url: str | None = None):
    return Div(
        modal_icon_button("‹", aria_label="Back", **actions_view_attrs(back_url)) if back_url else "",
        Div(
            P(title, cls=f"text-lg leading-snug {MODAL_NAME_CLS}"),
            P(subtitle, cls="text-xs text-gray-500 truncate") if subtitle else "",
            cls="flex flex-col min-w-0 flex-1",
        ),
        modal_icon_button("×", aria_label="Close", onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID)),
        cls="flex items-start justify-between gap-2",
    )


def actions_option(label: str, *, chevron: bool = False, **attrs):
    return Button(
        Span(label),
        Span("›", aria_hidden="true", cls="text-lg leading-none text-gray-500") if chevron else "",
        type="button",
        cls=_OPTION_CLS,
        **attrs,
    )


def FoodActionsMenu(entry_type: FoodEntryType, entry_id: int, entry: FoodEntrySummary):
    """First view: the food and what can be done with it. Edit only for the
    owner; anyone who sees it can copy it, the owner too (§9.3.1)."""
    base_url = food_actions_url(entry_type, entry_id)
    options = []
    if entry.can_edit:
        options.append(
            actions_option(
                EDIT_LABELS[entry_type],
                hx_get=f"/food/edit/{entry_type.value}/{entry_id}/form",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
                onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID) + " window.scrollTo({ top: 0, behavior: 'auto' });",
            )
        )
    options.append(actions_option(COPY_LABEL, chevron=True, **actions_view_attrs(f"{base_url}/copy")))
    # A recipe cannot be an ingredient of another recipe, nor go alone into a
    # container (frontend §9.4).
    if entry_type is not FoodEntryType.RECIPE:
        options.append(actions_option("Add to recipe", chevron=True, **actions_view_attrs(f"{base_url}/recipes")))
        options.append(actions_option("Save to fridge", chevron=True, **actions_view_attrs(f"{base_url}/fridge")))

    return Div(
        actions_header(entry.name or "Unnamed", entry.subtitle),
        Div(*options, cls="flex flex-col gap-1.5"),
        cls="flex flex-col gap-3",
    )


def FoodActionsRecipes(
    entry_type: FoodEntryType, entry_id: int, entry: FoodEntrySummary, recipes: list, several_plates: set[int] = frozenset()
):
    """Second view: the user's recipes. Picking one adds the food with the
    usual initial amount and closes the pop-up (static/js/food_actions.js).
    `recipes` are RecipeRead; one in `several_plates` first asks which plate (§9.3.1)."""
    if recipes:
        content = Div(
            *[
                (
                    actions_option(
                        recipe.name,
                        chevron=True,
                        **actions_view_attrs(
                            f"{food_actions_url(entry_type, entry_id)}/recipes/{recipe.id}/plates"
                        ),
                    )
                    if recipe.id in several_plates
                    else actions_option(
                        recipe.name,
                        hx_post=f"/food/recipe/{recipe.id}/ingredients/add/{entry_type.value}/{entry_id}",
                        hx_swap="none",
                        hx_push_url="false",
                        data_skip_page_loading="true",
                        data_food_actions_recipe=recipe.name,
                    )
                )
                for recipe in recipes
            ],
            cls="flex flex-col gap-1.5 max-h-[50vh] overflow-y-auto",
        )
    else:
        content = P("You have no recipes yet. Create one from the + menu.", cls="text-sm text-gray-600 px-1")
    return Div(
        actions_header("Add to recipe", entry.name or "Unnamed", back_url=food_actions_url(entry_type, entry_id)),
        content,
        cls="flex flex-col gap-3",
    )


def FoodActionsRecipePlates(
    entry_type: FoodEntryType, entry_id: int, entry: FoodEntrySummary, recipe, plates: list[tuple[int, str]]
):
    """Third view, for a recipe with several plates: which one (§9.3.1)."""
    return Div(
        actions_header(recipe.name, entry.name or "Unnamed", back_url=f"{food_actions_url(entry_type, entry_id)}/recipes"),
        Div(
            *[
                actions_option(
                    label,
                    hx_post=(
                        f"/food/recipe/{recipe.id}/ingredients/add/{entry_type.value}/{entry_id}"
                        f"?recipe_plate_id={plate_id}"
                    ),
                    hx_swap="none",
                    hx_push_url="false",
                    data_skip_page_loading="true",
                    data_food_actions_recipe=recipe.name,
                )
                for plate_id, label in plates
            ],
            cls="flex flex-col gap-1.5 max-h-[50vh] overflow-y-auto",
        ),
        cls="flex flex-col gap-3",
    )


def FoodActionsStore(entry_type: FoodEntryType, entry_id: int, entry: FoodEntrySummary):
    """An amount of the food into a new container, in the fridge or the freezer
    (measurement §4.8.5). It starts from its serving or, without one, 100 g, as the
    + of the row does. On success static/js/fridge.js closes it and gives the notice."""
    has_serving = entry.default_portion is not None
    form_id = f"food_actions_store_form_{entry_type.value}_{entry_id}"
    units = [Option("g", value=AmountInputUnit.GRAMS.value, selected=not has_serving)]
    if has_serving:
        units.insert(
            0, Option(f"serving ({entry.default_portion:g} g)", value=AmountInputUnit.PORTION.value, selected=True)
        )
    return Div(
        actions_header("Save to fridge", entry.name or "Unnamed", back_url=food_actions_url(entry_type, entry_id)),
        Form(
            Div(
                Label("Amount", cls="text-xs text-gray-700", **{"for": "food_actions_store_amount"}),
                Div(
                    Input(
                        type="text",
                        id="food_actions_store_amount",
                        name="amount_value",
                        value="1" if has_serving else f"{INITIAL_AMOUNT_WITHOUT_SERVING_G:g}",
                        inputmode="decimal",
                        onclick="this.select()",
                        cls=f"{FORM_FIELD_CLS} flex-1 min-w-0",
                    ),
                    Select(*units, name="amount_unit", aria_label="Unit", cls=f"{FORM_FIELD_CLS} w-auto"),
                    cls="flex items-center gap-2",
                ),
                cls="flex flex-col gap-1",
            ),
            Div(id=FOOD_ACTIONS_STORE_MESSAGE_ID),
            Div(
                *[
                    modal_confirm_button(
                        f"To {STORAGE_LABELS[location].lower()}",
                        cls="w-full",
                        hx_post=f"/food/fridge/store/{entry_type.value}/{entry_id}",
                        hx_vals=json.dumps({"location": location.value}),
                        hx_include=f"#{form_id}",
                        hx_target=f"#{FOOD_ACTIONS_STORE_MESSAGE_ID}",
                        hx_swap="innerHTML",
                        hx_push_url="false",
                        data_skip_page_loading="true",
                        **{"hx-disabled-elt": "this"},
                    )
                    for location in StorageLocation
                ],
                cls="grid grid-cols-2 gap-2",
            ),
            id=form_id,
            onsubmit="return false;",
            cls="flex flex-col gap-3",
        ),
        cls="flex flex-col gap-3",
    )


def FoodActionsCopyConfirm(entry_type: FoodEntryType, entry_id: int, entry: FoodEntrySummary):
    """Copy confirmation: the same question as the detail page (§9.4)."""
    return Div(
        actions_header(COPY_LABEL, entry.name or "Unnamed", back_url=food_actions_url(entry_type, entry_id)),
        P(COPY_QUESTION, cls="text-sm text-gray-700"),
        Div(
            modal_secondary_button("No", onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID), cls="w-full"),
            modal_confirm_button(
                "Yes",
                hx_post=f"/food/copy/{entry_type.value}/{entry_id}",
                hx_swap="none",
                hx_push_url="false",
                data_skip_page_loading="true",
                onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID),
                cls="w-full",
            ),
            cls="grid grid-cols-2 gap-2",
        ),
        cls="flex flex-col gap-3",
    )


def FoodActionsFavoriteConfirm(entry_type: FoodEntryType, entry_id: int, entry: FoodEntrySummary):
    """Asked only when the favorite is all that keeps the food visible (§9.3.2)."""
    noun = "dish" if entry_type is FoodEntryType.MANUAL_INTAKE else "food"
    return Div(
        actions_header("Remove from favorites", entry.name or "Unnamed"),
        P(
            f"This {noun} is no longer available. If you remove it from your favorites, "
            "you will lose access to it. Make a copy first if you want to keep using it.",
            cls="text-sm text-gray-700",
        ),
        Div(
            modal_secondary_button("Keep it", onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID), cls="w-full"),
            modal_confirm_button(
                "Remove",
                danger=True,
                hx_post=f"/food/favorite/{entry_type.value}/{entry_id}",
                hx_vals=json.dumps({"favorite": "false", "confirmed": "true"}),
                hx_target=f"#{favorite_button_id(entry_type, entry_id)}",
                hx_swap="outerHTML",
                hx_push_url="false",
                data_skip_page_loading="true",
                onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID),
                cls="w-full",
            ),
            cls="grid grid-cols-2 gap-2",
        ),
        cls="flex flex-col gap-3",
    )
