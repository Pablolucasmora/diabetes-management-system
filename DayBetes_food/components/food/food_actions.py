"""Actions pop-up of a food row (frontend_conventions.md §9.3.1).

Holding a row of the Food list (or a right click on it) opens one
`ModalLayer` whose body is requested from the server each time, so the
options follow what the user can do with that food now. Its views (the
menu, the recipe picker and the copy confirmation) are swapped inside the
same body; static/js/food_actions.js only detects the gesture, opens the
layer and closes it after an add.
"""

from fasthtml.common import *

from DayBetes_food.components.modal import (
    ModalLayer,
    close_modal_js,
    modal_confirm_button,
    modal_secondary_button,
)

FOOD_ACTIONS_MODAL_ID = "food_actions_modal"
FOOD_ACTIONS_BODY_ID = "food_actions_modal_body"

EDIT_LABELS = {"catalog": "Edit food", "manual_intake": "Edit manual", "recipe": "Edit recipe"}

# Long food names: up to two lines, then an ellipsis (as in the rescue pop-up).
_NAME_CLS = "min-w-0 max-w-full line-clamp-2 break-words font-semibold text-gray-900"
_ICON_BUTTON_CLS = """
    h-7 w-7 shrink-0 rounded-full cursor-pointer
    text-gray-500 hover:bg-line-soft transition-colors
    flex items-center justify-center text-lg leading-none
"""
# Options are solid `control` rows: the pop-up card is a solid panel (§8).
_OPTION_CLS = """
    w-full text-left px-3 py-2.5 rounded-xl cursor-pointer
    bg-control border border-line hover:bg-line-soft
    transition-colors flex items-center justify-between gap-3
    text-sm font-medium text-gray-900
"""


def food_actions_url(entry_type: str, entry_id: int) -> str:
    return f"/food/actions/{entry_type}/{entry_id}"


def FoodActionsTrigger(entry_type: str, entry_id: int):
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
    """Swaps another view of the pop-up into its body. The current view
    fades out on the click and the swap waits for it, so the card changes
    height once and the new view rises in (static/js/food_actions.js, §10)."""
    return {
        "hx_get": url,
        "hx_target": f"#{FOOD_ACTIONS_BODY_ID}",
        "hx_swap": "innerHTML swap:150ms",
        "hx_push_url": "false",
        "data_skip_page_loading": "true",
        "data_food_actions_view": "true",
    }


def _header(title: str, subtitle: str = "", back_url: str | None = None):
    back = (
        Button("‹", type="button", aria_label="Back", cls=_ICON_BUTTON_CLS, **_view_link_attrs(back_url))
        if back_url
        else ""
    )
    return Div(
        back,
        Div(
            P(title, cls=f"text-lg leading-snug {_NAME_CLS}"),
            P(subtitle, cls="text-xs text-gray-500 truncate") if subtitle else "",
            cls="flex flex-col min-w-0 flex-1",
        ),
        Button("×", type="button", aria_label="Close", onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID), cls=_ICON_BUTTON_CLS),
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


def FoodActionsMenu(entry_type: str, entry_id: int, name: str, subtitle: str, can_edit: bool):
    """First view: the food and what can be done with it. Edit only for the
    owner; anyone else gets the editable copy, as in the detail (§9.4)."""
    base_url = food_actions_url(entry_type, entry_id)
    options = []
    if can_edit:
        options.append(
            _option(
                EDIT_LABELS.get(entry_type, "Edit"),
                hx_get=f"/food/edit/{entry_type}/{entry_id}/form",
                hx_target="#main_content",
                hx_swap="innerHTML",
                hx_push_url="true",
                onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID) + " window.scrollTo({ top: 0, behavior: 'auto' });",
            )
        )
    else:
        options.append(_option("Create editable copy", chevron=True, **_view_link_attrs(f"{base_url}/copy")))
    # A recipe cannot be an ingredient of another recipe.
    if entry_type in ("catalog", "manual_intake"):
        options.append(_option("Add to recipe", chevron=True, **_view_link_attrs(f"{base_url}/recipes")))

    return Div(
        _header(name or "Unnamed", subtitle),
        Div(*options, cls="flex flex-col gap-1.5"),
        cls="flex flex-col gap-3",
    )


def FoodActionsRecipes(entry_type: str, entry_id: int, name: str, recipes: list[dict]):
    """Second view: the user's recipes. Picking one adds the food with the
    usual initial amount and closes the pop-up (static/js/food_actions.js)."""
    back_url = food_actions_url(entry_type, entry_id)
    if recipes:
        content = Div(
            *[
                _option(
                    str(recipe.get("name") or "Unnamed"),
                    hx_post=f"/food/recipe/{recipe['id']}/ingredients/add/{entry_type}/{entry_id}",
                    hx_swap="none",
                    hx_push_url="false",
                    data_skip_page_loading="true",
                    data_food_actions_recipe=str(recipe.get("name") or "the recipe"),
                )
                for recipe in recipes
            ],
            cls="flex flex-col gap-1.5 max-h-[50vh] overflow-y-auto",
        )
    else:
        content = P(
            "You have no recipes yet. Create one from the + menu.",
            cls="text-sm text-gray-600 px-1",
        )
    return Div(
        _header("Add to recipe", name or "Unnamed", back_url=back_url),
        content,
        cls="flex flex-col gap-3",
    )


def FoodActionsCopyConfirm(entry_type: str, entry_id: int, name: str):
    """Copy confirmation: the same question as the detail page (§9.4)."""
    return Div(
        _header("Create editable copy", name or "Unnamed", back_url=food_actions_url(entry_type, entry_id)),
        P("A personal copy will be created and opened for editing. Continue?", cls="text-sm text-gray-700"),
        Div(
            modal_secondary_button("No", onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID), cls="w-full"),
            modal_confirm_button(
                "Yes",
                hx_post=f"/food/copy/{entry_type}/{entry_id}",
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
