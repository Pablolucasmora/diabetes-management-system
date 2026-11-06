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

from DayBetes_food.components.modal import (
    MODAL_NAME_CLS,
    ModalLayer,
    close_modal_js,
    modal_confirm_button,
    modal_icon_button,
    modal_secondary_button,
)
from DayBetes_food.domain.constants import FoodEntryType
from DayBetes_food.domain.food_entry import FoodEntrySummary

FOOD_ACTIONS_MODAL_ID = "food_actions_modal"
FOOD_ACTIONS_BODY_ID = "food_actions_modal_body"

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


def FoodActionsTrigger(entry_type: FoodEntryType, entry_id: int):
    """Hidden request source inside a food row. static/js/food_actions.js
    fires `dbFoodActions` on it after a long press or a right click; being
    its own element, the request skips the page loading layer without
    affecting the row's own click."""
    return Span(
        hidden=True,
        hx_get=food_actions_url(entry_type, entry_id),
        hx_trigger="dbFoodActions",
        hx_target=f"#{FOOD_ACTIONS_BODY_ID}",
        hx_swap="innerHTML",
        hx_push_url="false",
        data_skip_page_loading="true",
        data_food_actions_trigger="true",
    )


def FoodActionsModal():
    """The pop-up layer. Its body arrives with `GET /food/actions/...`."""
    return ModalLayer(
        Div(id=FOOD_ACTIONS_BODY_ID, cls="flex flex-col gap-3"),
        modal_id=FOOD_ACTIONS_MODAL_ID,
        card_cls="gap-3 max-h-[88vh] overflow-y-auto",
    )


def _view_link_attrs(url: str) -> dict:
    """Swaps another view of the pop-up into its body. `data-food-actions-view`
    is what static/js/food_actions.js animates (§10)."""
    return {
        "hx_get": url,
        "hx_target": f"#{FOOD_ACTIONS_BODY_ID}",
        "hx_swap": "innerHTML",
        "hx_push_url": "false",
        "data_skip_page_loading": "true",
        "data_food_actions_view": "true",
    }


def _header(title: str, subtitle: str = "", back_url: str | None = None):
    return Div(
        modal_icon_button("‹", aria_label="Back", **_view_link_attrs(back_url)) if back_url else "",
        Div(
            P(title, cls=f"text-lg leading-snug {MODAL_NAME_CLS}"),
            P(subtitle, cls="text-xs text-gray-500 truncate") if subtitle else "",
            cls="flex flex-col min-w-0 flex-1",
        ),
        modal_icon_button("×", aria_label="Close", onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID)),
        cls="flex items-start justify-between gap-2",
    )


def _option(label: str, *, chevron: bool = False, **attrs):
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
            _option(
                EDIT_LABELS[entry_type],
                hx_get=f"/food/edit/{entry_type.value}/{entry_id}/form",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
                onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID) + " window.scrollTo({ top: 0, behavior: 'auto' });",
            )
        )
    options.append(_option(COPY_LABEL, chevron=True, **_view_link_attrs(f"{base_url}/copy")))
    # A recipe cannot be an ingredient of another recipe.
    if entry_type is not FoodEntryType.RECIPE:
        options.append(_option("Add to recipe", chevron=True, **_view_link_attrs(f"{base_url}/recipes")))

    return Div(
        _header(entry.name or "Unnamed", entry.subtitle),
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
                    _option(
                        recipe.name,
                        chevron=True,
                        **_view_link_attrs(
                            f"{food_actions_url(entry_type, entry_id)}/recipes/{recipe.id}/plates"
                        ),
                    )
                    if recipe.id in several_plates
                    else _option(
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
        _header("Add to recipe", entry.name or "Unnamed", back_url=food_actions_url(entry_type, entry_id)),
        content,
        cls="flex flex-col gap-3",
    )


def FoodActionsRecipePlates(
    entry_type: FoodEntryType, entry_id: int, entry: FoodEntrySummary, recipe, plates: list[tuple[int, str]]
):
    """Third view, for a recipe with several plates: which one (§9.3.1)."""
    return Div(
        _header(recipe.name, entry.name or "Unnamed", back_url=f"{food_actions_url(entry_type, entry_id)}/recipes"),
        Div(
            *[
                _option(
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


def FoodActionsCopyConfirm(entry_type: FoodEntryType, entry_id: int, entry: FoodEntrySummary):
    """Copy confirmation: the same question as the detail page (§9.4)."""
    return Div(
        _header(COPY_LABEL, entry.name or "Unnamed", back_url=food_actions_url(entry_type, entry_id)),
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
        _header("Remove from favorites", entry.name or "Unnamed"),
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
