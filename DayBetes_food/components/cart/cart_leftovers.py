"""The leftovers pop-up of the cart (frontend_conventions.md §7.14).

When a meal is confirmed with a plate not eaten whole, the confirm route answers
with this form instead of confirming: what was left of each of those plates, and
what to do with it (fridge, freezer or nothing, in how many containers, with which
name). Confirming from it confirms the meal and stores the leftovers together
(measurement_conventions.md §4.8.5). static/js/fridge.js opens and closes it.
"""

from fasthtml.common import *

from DayBetes_food.components.food.food_shared import STORAGE_LABELS
from DayBetes_food.components.modal import (
    ModalLayer,
    close_modal_js,
    modal_confirm_button,
    modal_secondary_button,
)
from DayBetes_food.domain.constants import StorageLocation
from DayBetes_food.domain.fridge import LEFTOVER_CONTAINERS_RANGE
from DayBetes_food.domain.intake_plate import PlateEaten

CART_LEFTOVERS_MODAL_ID = "cart_leftovers_modal"
CART_LEFTOVERS_BODY_ID = "cart_leftovers_body"
CART_LEFTOVERS_MESSAGE_ID = "cart_leftovers_message"

_FIELD_CLS = "web_input border border-line rounded-lg px-3 py-2 text-sm min-w-0"


def CartLeftoversModal():
    """The pop-up layer, once per cart page. Its body comes from the confirm route."""
    return ModalLayer(
        Div(id=CART_LEFTOVERS_BODY_ID, cls="flex flex-col gap-3"),
        modal_id=CART_LEFTOVERS_MODAL_ID,
        card_cls="gap-3 max-h-[88vh] overflow-y-auto",
    )


def _eaten_fields(eaten: list[PlateEaten]):
    """What was typed in the card, sent again with the final confirm (§9.5)."""
    fields = []
    for entry in eaten:
        fields.extend(
            (
                Input(type="hidden", name="plate_id", value=str(entry.plate_id)),
                Input(type="hidden", name="ingested_value", value="" if entry.value is None else repr(entry.value)),
                Input(type="hidden", name="ingested_unit", value=entry.unit.value),
            )
        )
    return fields


def _plate_leftovers(plate_id: int, label: str, fraction: float, portions: list):
    """One plate: what is left of each ingredient, and what to do with it."""
    left = 1.0 - fraction
    location_id = f"leftover_location_{plate_id}"
    containers_id = f"leftover_containers_{plate_id}"
    name_id = f"leftover_name_{plate_id}"
    return Div(
        Input(type="hidden", name="leftover_plate_id", value=str(plate_id)),
        P(label, cls="font-semibold text-gray-900 break-words"),
        P(
            ", ".join(f"{portion.source.name} {portion.amount * left:.1f} g" for portion in portions),
            cls="text-xs text-gray-600",
        ),
        Div(
            Div(
                Label("Keep in", cls="text-xs text-gray-700", **{"for": location_id}),
                Select(
                    *[
                        Option(STORAGE_LABELS[location], value=location.value, selected=location is StorageLocation.FRIDGE)
                        for location in StorageLocation
                    ],
                    Option("Don't keep", value=""),
                    id=location_id,
                    name="leftover_location",
                    cls=_FIELD_CLS,
                ),
                cls="flex flex-col gap-1 min-w-0",
            ),
            Div(
                Label("Containers", cls="text-xs text-gray-700", **{"for": containers_id}),
                Input(
                    type="number",
                    id=containers_id,
                    name="leftover_containers",
                    value="1",
                    min=str(int(LEFTOVER_CONTAINERS_RANGE.minimum)),
                    max=str(int(LEFTOVER_CONTAINERS_RANGE.maximum)),
                    step="1",
                    inputmode="numeric",
                    cls=f"{_FIELD_CLS} overflow-hidden",
                ),
                cls="flex flex-col gap-1 min-w-0",
            ),
            cls="grid grid-cols-2 gap-2",
        ),
        Div(
            Label("Name", cls="text-xs text-gray-700", **{"for": name_id}),
            Input(type="text", id=name_id, name="leftover_name", placeholder=label, cls=f"{_FIELD_CLS} w-full"),
            cls="flex flex-col gap-1",
        ),
        cls="flex flex-col gap-2 rounded-2xl border border-line p-3",
    )


def LeftoversForm(event_id: int, eaten: list[PlateEaten], plates: list[tuple[int, str, float, list]]):
    """`plates` are `(plate_id, shown name, fraction eaten, portions)` of the plates
    not eaten whole. Split into several containers, each gets an equal part."""
    return Form(
        P("Leftovers", cls="text-lg font-semibold text-gray-900"),
        P("Part of this meal was not eaten. Keep it in containers?", cls="text-sm text-gray-700"),
        *_eaten_fields(eaten),
        Input(type="hidden", name="leftovers_reviewed", value="true"),
        *[_plate_leftovers(*plate) for plate in plates],
        Div(id=CART_LEFTOVERS_MESSAGE_ID),
        Div(
            modal_secondary_button("Cancel", onclick=close_modal_js(CART_LEFTOVERS_MODAL_ID), cls="w-full"),
            modal_confirm_button(
                "Confirm meal",
                cls="w-full",
                hx_post=f"/cart/event/{event_id}/confirm",
                hx_include="closest form",
                hx_target=f"#cart_card_event_{event_id}",
                hx_swap="outerHTML",
                **{"hx-disabled-elt": "this"},
            ),
            cls="grid grid-cols-2 gap-2",
        ),
        onsubmit="return false;",
        cls="flex flex-col gap-3",
    )
