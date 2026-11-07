"""The `Fridge` tab of Food (frontend_conventions.md §9.8).

The open containers of the user, in a `Fridge` section and a `Freezer` one, and
the views of their actions pop-up, which is the same pop-up as the food rows
(components/food/food_actions.py, static/js/food_actions.js). The components
receive the containers already read (code_conventions.md §1.4).
"""

import json
from datetime import datetime

from fasthtml.common import *

from DayBetes_food.components.food.food_actions import (
    FOOD_ACTIONS_MODAL_ID,
    ActionsTrigger,
    actions_header,
    actions_option,
    actions_view_attrs,
)
from DayBetes_food.components.food.food_shared import AmountUnitField, FORM_FIELD_CLS, STORAGE_LABELS
from DayBetes_food.components.modal import close_modal_js, modal_confirm_button, modal_secondary_button
from DayBetes_food.domain.constants import AmountInputUnit, StorageLocation
from DayBetes_food.domain.fridge import FRIDGE_NAME_MAX_LENGTH, FridgeItem, other_location
from DayBetes_food.time_utils import to_local

# The list lives in #food-list, like the other tabs of Food. The actions that
# change it answer with the whole list for that same target (code_conventions §9.5).
FRIDGE_LIST_TARGET = "#food-list"
FRIDGE_EDIT_MESSAGE_ID = "fridge_edit_message"
FRIDGE_TAKE_MESSAGE_ID = "fridge_take_message"
# What is taken goes to the meal and plate chosen in the Food header (§7.7).
MEAL_TARGET_INCLUDE = "#meal_selector, #plate_selector"

_MOVE_LABELS = {StorageLocation.FRIDGE: "To fridge", StorageLocation.FREEZER: "To freezer"}

_SMALL_BUTTON_CLS = "web_button px-2.5 py-1.5 rounded-xl text-xs font-medium whitespace-nowrap"


def fridge_actions_url(fridge_id: int) -> str:
    return f"/food/fridge/{fridge_id}/actions"


def _list_action_attrs(url: str, **values) -> dict:
    """A POST whose answer is the whole fridge list (§9.5 of code_conventions.md)."""
    return {
        "hx_post": url,
        "hx_target": FRIDGE_LIST_TARGET,
        "hx_swap": "innerHTML",
        "hx_push_url": "false",
        "data_skip_page_loading": "true",
        **({"hx_vals": json.dumps(values)} if values else {}),
    }


def _days(count: int, unit: str = "day") -> str:
    return f"{count} {unit}{'' if count == 1 else 's'}"


def _timing_text(item: FridgeItem, now: datetime) -> str:
    """'3 days in · 7 days left', counted in local calendar days (§10.4)."""
    today = to_local(now).date()
    stored = to_local(item.fridge.stored_at).date()
    expires = to_local(item.fridge.expires_at).date()
    days_in = (today - stored).days
    stored_text = "Stored today" if days_in == 0 else f"{_days(days_in)} in"
    if item.is_expired(now):
        days_ago = (today - expires).days
        return f"{stored_text} · expired {'today' if days_ago == 0 else _days(days_ago) + ' ago'}"
    days_left = (expires - today).days
    return f"{stored_text} · {'expires today' if days_left == 0 else _days(days_left) + ' left'}"


def FridgeCard(item: FridgeItem, now: datetime):
    """A container: name, content, days and real weight. Its buttons move it to the
    other place and take a part of it into the meal of the header or, once expired,
    discard it or eat all of it; holding the card opens its actions."""
    fridge = item.fridge
    expired = item.is_expired(now)
    # The amounts as stored, so what is left after taking a part shows (frontend §6).
    content = ", ".join(
        f"{portion.source.name} {portion.amount:.1f} g{' cooked' if portion.is_cooked_weight else ''}"
        for portion in item.portions
        if portion.source.name
    )
    meta = _timing_text(item, now)
    if fridge.content_weight is not None:
        meta = f"{meta} · {fridge.content_weight:.1f} g"
    if expired:
        buttons = (
            Button(
                "Discard",
                type="button",
                cls=f"{_SMALL_BUTTON_CLS} text-danger",
                data_no_open="true",
                **actions_view_attrs(f"{fridge_actions_url(fridge.id)}/discard"),
            ),
            # The + with 100 %, straight away (frontend §9.8). Only the list comes
            # back, out of band; a failure is a notice (error_conventions §7.1).
            Button(
                "Eat",
                type="button",
                cls=_SMALL_BUTTON_CLS,
                data_no_open="true",
                hx_post=f"/food/fridge/{fridge.id}/take",
                hx_vals=json.dumps({"amount_value": "100", "amount_unit": AmountInputUnit.PERCENT.value}),
                hx_include=MEAL_TARGET_INCLUDE,
                hx_swap="none",
                hx_push_url="false",
                data_skip_page_loading="true",
                **{"hx-disabled-elt": "this"},
            ),
        )
    else:
        target = other_location(fridge.location)
        buttons = (
            Button(
                _MOVE_LABELS[target],
                type="button",
                cls=_SMALL_BUTTON_CLS,
                data_no_open="true",
                **{"hx-disabled-elt": "this"},
                **_list_action_attrs(f"/food/fridge/{fridge.id}/location", location=target.value),
            ),
            Button(
                "+",
                type="button",
                aria_label="Add to meal",
                cls="web_button web_button_primary rounded-xl w-9 h-9 flex items-center justify-center text-lg leading-none",
                data_no_open="true",
                **actions_view_attrs(f"{fridge_actions_url(fridge.id)}/take"),
            ),
        )
    return Div(
        Div(
            H1(
                Span(item.display_name),
                Span("Expired", cls="text-[10px] font-semibold text-danger") if expired else "",
                cls="text-left text-[15px] font-semibold leading-snug flex flex-wrap items-center gap-1.5",
            ),
            P(content, cls="text-xs text-gray-500 truncate") if content else "",
            P(meta, cls=f"text-xs mt-0.5 {'text-danger' if expired else 'text-gray-700'}"),
            cls="flex flex-col min-w-0",
        ),
        Div(*buttons, cls="flex items-center gap-2 ml-3 shrink-0"),
        ActionsTrigger(fridge_actions_url(fridge.id)),
        id=f"fridge_card_{fridge.id}",
        # Long press or right click: actions pop-up (§9.3.1, static/js/food_actions.js).
        data_food_actions="true",
        cls="web_container food_entry rounded-2xl flex items-center justify-between",
    )


def FridgeListContent(items: list[FridgeItem], now: datetime) -> tuple:
    """The two sections, Fridge first, as children of #food-list."""
    if not items:
        return (
            P(
                "Nothing stored yet. Save a food or a dish with Save to fridge, on its page or holding it in the list.",
                cls="text-sm text-gray-600 text-center md:w-md lg:w-md w-xs mt-2",
            ),
        )
    nodes = []
    for location in StorageLocation:
        cards = [FridgeCard(item, now) for item in items if item.fridge.location is location]
        nodes.append(H2(STORAGE_LABELS[location], cls="web_section_label md:w-md lg:w-md w-xs mt-2"))
        nodes.extend(cards or [P("Empty.", cls="text-xs text-gray-500 md:w-md lg:w-md w-xs")])
    return tuple(nodes)


def FridgeListOob(items: list[FridgeItem], now: datetime):
    """The same list, swapped out of band into #food-list (after the edit form)."""
    return Div(*FridgeListContent(items, now), id="food-list", hx_swap_oob="innerHTML")


# ---- Actions pop-up (frontend_conventions.md §9.8) ----


def FridgeActionsMenu(item: FridgeItem):
    url = fridge_actions_url(item.fridge.id)
    return Div(
        actions_header(item.display_name, STORAGE_LABELS[item.fridge.location]),
        Div(
            actions_option("Edit", chevron=True, **actions_view_attrs(f"{url}/edit")),
            actions_option("Discard", chevron=True, **actions_view_attrs(f"{url}/discard")),
            cls="flex flex-col gap-1.5",
        ),
        cls="flex flex-col gap-3",
    )


def _field(label: str, field_id: str, *control):
    return Div(
        Label(label, cls="text-xs text-gray-700", **{"for": field_id}),
        *control,
        cls="flex flex-col gap-1",
    )


def FridgeEditForm(item: FridgeItem):
    """Name, expiry date and real weight, saved together (§3.4 full replacement).
    A validation error stays inside the form (§9.5); on success the list is
    repainted and the pop-up closes (`fridgeChanged`)."""
    fridge = item.fridge
    url = fridge_actions_url(fridge.id)
    form_id = f"fridge_edit_form_{fridge.id}"
    weight = "" if fridge.content_weight is None else f"{fridge.content_weight:g}"
    return Div(
        actions_header("Edit", item.display_name, back_url=url),
        Form(
            _field(
                "Name",
                "fridge_edit_name",
                Input(
                    type="text",
                    id="fridge_edit_name",
                    name="name",
                    value=fridge.name or "",
                    placeholder=item.display_name,
                    maxlength=str(FRIDGE_NAME_MAX_LENGTH),
                    cls=FORM_FIELD_CLS,
                ),
            ),
            _field(
                "Expiry date",
                "fridge_edit_expires_at",
                Input(
                    type="date",
                    id="fridge_edit_expires_at",
                    name="expires_at",
                    value=to_local(fridge.expires_at).date().isoformat(),
                    min=to_local(fridge.stored_at).date().isoformat(),
                    required=True,
                    cls=f"{FORM_FIELD_CLS} min-w-0",
                ),
            ),
            _field(
                "Real weight (g)",
                "fridge_edit_content_weight",
                Input(
                    type="text",
                    id="fridge_edit_content_weight",
                    name="content_weight",
                    value=weight,
                    inputmode="decimal",
                    placeholder="Not weighed",
                    cls=FORM_FIELD_CLS,
                ),
            ),
            Div(id=FRIDGE_EDIT_MESSAGE_ID),
            Div(
                modal_secondary_button("Cancel", cls="w-full", **actions_view_attrs(url)),
                modal_confirm_button(
                    "Save",
                    cls="w-full",
                    hx_post=f"/food/fridge/{fridge.id}/edit",
                    hx_include=f"#{form_id}",
                    hx_target=f"#{FRIDGE_EDIT_MESSAGE_ID}",
                    hx_swap="innerHTML",
                    hx_push_url="false",
                    data_skip_page_loading="true",
                    **{"hx-disabled-elt": "this"},
                ),
                cls="grid grid-cols-2 gap-2",
            ),
            id=form_id,
            onsubmit="return false;",
            cls="flex flex-col gap-3",
        ),
        cls="flex flex-col gap-3",
    )


def FridgeTakeForm(item: FridgeItem):
    """How much to take into the meal of the header: % by default, grams only with
    the real weight (measurement §4.8.3). A validation error stays in the form."""
    fridge = item.fridge
    form_id = f"fridge_take_form_{fridge.id}"
    units = [Option("%", value=AmountInputUnit.PERCENT.value, selected=True)]
    if fridge.content_weight is not None:
        units.append(Option(f"g (of {fridge.content_weight:.1f} g)", value=AmountInputUnit.GRAMS.value))
    return Div(
        actions_header("Add to meal", item.display_name, back_url=fridge_actions_url(fridge.id)),
        Form(
            AmountUnitField("fridge_take_amount", "100", units),
            P("It goes to the meal and plate chosen in Add to.", cls="text-xs text-gray-500"),
            Div(id=FRIDGE_TAKE_MESSAGE_ID),
            Div(
                modal_secondary_button("Cancel", onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID), cls="w-full"),
                modal_confirm_button(
                    "Add to meal",
                    cls="w-full",
                    hx_post=f"/food/fridge/{fridge.id}/take",
                    hx_include=f"#{form_id}, {MEAL_TARGET_INCLUDE}",
                    hx_target=f"#{FRIDGE_TAKE_MESSAGE_ID}",
                    hx_swap="innerHTML",
                    hx_push_url="false",
                    data_skip_page_loading="true",
                    **{"hx-disabled-elt": "this"},
                ),
                cls="grid grid-cols-2 gap-2",
            ),
            id=form_id,
            onsubmit="return false;",
            cls="flex flex-col gap-3",
        ),
        cls="flex flex-col gap-3",
    )


def FridgeDiscardConfirm(item: FridgeItem):
    """Asked before throwing a container away (frontend_conventions.md §9.8)."""
    return Div(
        actions_header("Discard", item.display_name, back_url=fridge_actions_url(item.fridge.id)),
        P("This container will be removed from your fridge. This cannot be undone. Continue?", cls="text-sm text-gray-700"),
        Div(
            modal_secondary_button("No", onclick=close_modal_js(FOOD_ACTIONS_MODAL_ID), cls="w-full"),
            modal_confirm_button(
                "Discard",
                danger=True,
                cls="w-full",
                **{"hx-disabled-elt": "this"},
                **_list_action_attrs(f"/food/fridge/{item.fridge.id}/discard"),
            ),
            cls="grid grid-cols-2 gap-2",
        ),
        cls="flex flex-col gap-3",
    )
