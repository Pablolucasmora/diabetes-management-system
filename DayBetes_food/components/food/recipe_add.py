"""The step before adding a recipe to a meal, or saving it to the fridge
(frontend_conventions.md §9.7)."""

import json

from fasthtml.common import *

from DayBetes_food.components.food.food_shared import STORAGE_LABELS
from DayBetes_food.components.injection_zone import asset_busted
from DayBetes_food.components.modal import ModalLayer, close_modal_js
from DayBetes_food.domain.constants import ConservationMethod, CookingMethod, FoodPhysicalState, StorageLocation
from DayBetes_food.domain.intake_plate import derive_plate_name

RECIPE_ADD_MODAL_ID = "recipe_add_modal"
_FIELD_CLS = "web_input bg-white border border-line rounded-lg px-2 py-1.5 text-base w-full min-w-0"


def recipe_add_open_attrs(recipe_id: int) -> dict:
    """Attributes of any button that opens the step: it asks the server for the form,
    and static/js/recipe_add.js opens the layer once the form is in."""
    return {
        "hx_get": f"/food/recipe/{recipe_id}/add/form",
        "hx_target": "#recipe_add_body",
        "hx_swap": "innerHTML",
        "hx_include": "#meal_selector, #plate_selector",
        "hx_push_url": "false",
        "data_skip_page_loading": "true",
    }


def RecipeAddModal():
    """The pop-up layer. Its body arrives with `GET /food/recipe/{id}/add/form`."""
    return (
        ModalLayer(
            Div(id="recipe_add_body", cls="flex flex-col gap-3"),
            modal_id=RECIPE_ADD_MODAL_ID,
            card_cls="gap-3 max-h-[88vh] overflow-y-auto",
        ),
        Script(src=asset_busted("/js/recipe_add.js"), defer="defer"),
    )


def _preparation_select(label: str, name: str, enum_cls, selected):
    current = selected.value if selected else ""
    return Label(
        Span(label, cls="text-xs text-gray-600"),
        Select(
            Option("-", value="", selected=current == ""),
            *[Option(item.value, value=item.value, selected=item.value == current) for item in enum_cls],
            name=name,
            cls=_FIELD_CLS,
        ),
        cls="flex flex-col gap-1 min-w-0",
    )


def _ingredient_fields(portion, grams: float):
    """One line per ingredient. The preparation stays folded: it is usually right."""
    return Details(
        Summary(
            Span(portion.source.name or f"Ingredient #{portion.id}", cls="font-medium truncate min-w-0"),
            Span(f"{grams:.0f} g", cls="text-xs text-gray-500 shrink-0"),
            cls="flex items-center justify-between gap-2 cursor-pointer",
        ),
        Input(type="hidden", name="portion_id", value=str(portion.id)),
        Div(
            _preparation_select("Cooking", "cooking", CookingMethod, portion.cooking),
            _preparation_select("Final state", "final_state", FoodPhysicalState, portion.final_state),
            _preparation_select("Conservation", "conservation", ConservationMethod, portion.conservation),
            cls="grid grid-cols-2 gap-2 pt-2",
        ),
        cls="rounded-xl border border-line px-3 py-2 text-sm",
    )


def RecipeAddForm(recipe, groups: list[tuple], intake_event_id: str, plate_id: str):
    """`groups` are the `(plate, portions)` of the recipe, without empty plates."""
    several_plates = len(groups) > 1
    per_serving = 1 / recipe.servings if recipe.servings else 1
    sections = []
    for plate, portions in groups:
        if several_plates:
            sections.append(
                P(
                    plate.name or derive_plate_name([portion.source.name for portion in portions]),
                    cls="web_section_label",
                )
            )
        sections.extend(_ingredient_fields(portion, portion.amount * per_serving) for portion in portions)
    return Form(
        P(f"Add {recipe.name}", cls="text-lg font-semibold break-words"),
        P(f"It goes in as {len(groups)} new plates.", cls="text-xs text-gray-600") if several_plates else "",
        Input(type="hidden", name="intake_event_id", value=intake_event_id),
        Input(type="hidden", name="plate_id", value="" if several_plates else plate_id),
        (
            Label(
                Span(f"Servings (the recipe makes {recipe.servings})", cls="text-xs text-gray-600"),
                Input(type="text", name="servings", inputmode="decimal", value="1", cls=_FIELD_CLS),
                cls="flex flex-col gap-1",
            )
            if recipe.servings
            else ""
        ),
        Div(*sections, cls="flex flex-col gap-2"),
        Div(id="recipe_add_error", cls="text-sm text-red-700"),
        Div(
            Button(
                "Cancel",
                type="button",
                cls="web_button px-4 py-2 text-sm rounded-xl",
                onclick=close_modal_js(RECIPE_ADD_MODAL_ID),
            ),
            Button(
                "Add to meal",
                type="submit",
                cls="web_button px-4 py-2 text-sm rounded-xl bg-black text-white border-black",
            ),
            cls="grid grid-cols-2 gap-2",
        ),
        # Or the same servings into a new container (measurement §4.8.5).
        Div(
            *[
                Button(
                    f"Save to {STORAGE_LABELS[location].lower()}",
                    type="button",
                    cls="web_button px-4 py-2 text-sm rounded-xl",
                    hx_post=f"/food/fridge/store_recipe/{recipe.id}",
                    hx_vals=json.dumps({"location": location.value}),
                    hx_include="closest form",
                    hx_target="#recipe_add_error",
                    hx_swap="innerHTML",
                    hx_push_url="false",
                    data_skip_page_loading="true",
                    **{"hx-disabled-elt": "this"},
                )
                for location in StorageLocation
            ],
            cls="grid grid-cols-2 gap-2",
        ),
        hx_post=f"/add_recipe/{recipe.id}",
        hx_target="#recipe_add_error",
        hx_swap="innerHTML",
        hx_push_url="false",
        hx_disabled_elt="find button[type=submit]",
        data_skip_page_loading="true",
        cls="flex flex-col gap-3",
    )
