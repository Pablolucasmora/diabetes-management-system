"""Page of the assistant for logging meals (frontend_conventions.md §9.11).

Pure components (code_conventions.md §1.4): they receive data already read.
The `/` suggestions and the composer behavior live in static/js/assistant.js.
"""

import json
from urllib.parse import urlencode

from fasthtml.common import *

from DayBetes_food.components.cart.cart_shared import portion_name
from DayBetes_food.components.food.food_shared import AMOUNT_METHOD_LABELS, MACROS_SOURCE_LABELS
from DayBetes_food.components.food.food_list import meal_option_label
from DayBetes_food.components.food.rescue import carbs_meta
from DayBetes_food.components.modal import (
    MODAL_NAME_CLS,
    ModalLayer,
    close_modal_js,
    modal_icon_button,
    open_modal_js,
)
from DayBetes_food.components.navigation import back_js
from DayBetes_food.components.preparation import PREPARATION_FIELD_LABELS, PREPARATION_LABELS, pill_cls
from DayBetes_food.components.settings.subpage import SearchField
from DayBetes_food.domain.intake_plate import plate_label
from DayBetes_food.domain.assistant import (
    MANUAL_INTAKE_DRAFT_SOURCE,
    RECIPE_DRAFT_SOURCE,
    ASSISTANT_PHOTOS_MAX,
    ASSISTANT_TEXT_MAX_LENGTH,
    NO_MEAL_CHOICE,
    AddedCard,
    AssistantTurnRead,
    DraftCard,
    ProvisionalCard,
    RemovalCard,
    RepeatCard,
    RepeatSaveAs,
    StoredCard,
    TurnView,
)
from DayBetes_food.domain.constants import (
    AmountMethod,
    AssistantDraftSource,
    FoodEntryType,
    MacrosSource,
    StorageLocation,
)
from DayBetes_food.domain.food_entry import MentionSuggestion
from DayBetes_food.domain.portion_detail import (
    MEASURED_MARGIN_MAX,
    carbs_range,
    portion_carbs,
    portion_carbs_margin,
)
from DayBetes_food.time_utils import to_local

MENTIONS_LIST_ID = "assistant_mentions"
MEAL_SELECT_ID = "assistant_meal"
THREAD_BOX_ID = "assistant_thread_box"
THREAD_ID = "assistant_thread"
CONVERSATION_INPUT_ID = "assistant_conversation_id"
COMPOSER_FORM_ID = "assistant_composer"

_ENTRY_TYPE_LABELS = {
    FoodEntryType.CATALOG: "Food",
    FoodEntryType.MANUAL_INTAKE: "Dish",
    FoodEntryType.RECIPE: "Recipe",
}

_SEND_ICON = NotStr(
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="h-4 w-4">'
    '<path d="M10 16V4"/><path d="m5 9 5-5 5 5"/></svg>'
)


_PHOTO_ICON = NotStr(
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="h-4 w-4">'
    '<path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h1.8l1.2-2h5l1.2 2h1.8A1.5 1.5 0 0 1 17 7.5v7A1.5 1.5 0 0 1 15.5 16h-11A1.5 1.5 0 0 1 3 14.5z"/>'
    '<circle cx="10" cy="10.5" r="3"/></svg>'
)


def _cart_button():
    # The floating cart button is hidden here (data-hide-cart): this small one
    # opens the cart without covering the composer (§9.11).
    return Button(
        Img(src="/images/ui/cart.svg", alt="", cls="h-4 w-4"),
        type="button",
        aria_label="Open the cart",
        cls="""
            h-8 w-8 shrink-0 rounded-full bg-surface border border-line-soft
            shadow-[0_2px_8px_rgba(80,60,40,0.12)] cursor-pointer
            flex items-center justify-center active:scale-95 transition-transform
        """,
        hx_get="/cart",
        hx_target="#main_content",
        hx_push_url="true",
        # Lands on the chosen meal's card (static/js/assistant.js, frontend §5).
        **{"hx-on:click": "dbOpenCartFromAssistant();"},
    )


# The short guide of §9.11 ("How to write"): what the assistant understands best.
_HOW_TO_WRITE = (
    ("Foods", "Type / to pin each food and give its amount: \"/Chicken breast 150 g\", \"1 /Tomato\"."),
    (
        "One sentence, one preparation",
        "It applies to every food in it: \"In a pan with a little oil: /Carrot 80 g, /Tomato 100 g "
        "and /Chicken breast 150 g\". Oil without grams is estimated.",
    ),
    (
        "Cooking",
        "pan or grill = griddle, fried = fried, boiled = boiled-soft, al dente, steamed, oven, "
        "air fryer, toaster, raw.",
    ),
    ("Weight", "For rice, pasta and legumes say \"weighed cooked\" or \"raw\"; otherwise you will be asked."),
    (
        "Also",
        "freshly made, from the fridge, frozen or pre-cooked; mashed or liquid; for fruit, unripe, "
        "ripe or overripe.",
    ),
    ("Time and plates", "\"at 14:30\", \"dinner\", \"dessert 30 min later\"."),
    (
        "New foods and recipes",
        "Send a photo of the label, or ask to estimate a food. Paste a recipe and say which "
        "ingredients you do not have are \"manual\" or \"quick add\".",
    ),
)


def _how_to_write():
    return Details(
        Summary("How to write", cls="text-xs font-semibold text-gray-700 cursor-pointer"),
        Ul(
            *(
                Li(Span(f"{title}: ", cls="font-semibold"), text, cls="text-xs text-gray-600")
                for title, text in _HOW_TO_WRITE
            ),
            cls="flex flex-col gap-1 pt-2",
        ),
    )


def _intro(new_meal: bool = False):
    return Div(
        P("Tell me what you ate, with amounts if you know them.", cls="text-sm text-gray-800"),
        # A new meal is not asked when it is (§9.11): the first message says it.
        P("Say when, or it is for now.", cls="text-xs font-semibold text-gray-700") if new_meal else None,
        P(
            "Type / to pin one of your foods, dishes or recipes, so I use exactly that one. "
            "You can also attach a photo of the dish or of a nutrition label, or describe a "
            "recipe to save it.",
            cls="text-xs text-gray-500",
        ),
        _how_to_write(),
        # Removed by assistant.js as soon as the first message is sent (§9.11).
        data_intro="true",
        cls="web_container w-full px-4 py-3 flex flex-col gap-1",
    )


CHATS_MODAL_ID = "assistant_chats"
MEAL_BAR_ID = "assistant_meal_bar"
# Share of the chat's height the meal's foods may take before they fold into one line (§9.11).
MEAL_FOLD_SHARE = 0.10
# The `No meal` chats the list of chats shows (§9.11).
MEAL_FREE_CHATS_SHOWN = 5


def _carbs_text(value: float) -> str:
    return f"{value:.0f} g"


def _range_text(portions: list) -> str:
    """The meal's carbs as a range (§9.11): one number when both ends round the same."""
    low, high = carbs_range(portions)
    if round(low) == round(high):
        return _carbs_text(low)
    return f"{low:.0f}\u2013{high:.0f} g"


def _confidence_dot(portion):
    """Green when the food's carbs are measured (a scale or the pack, and a label or a
    table), amber when something is estimated (§9.11)."""
    measured = portion_carbs_margin(portion) <= MEASURED_MARGIN_MAX
    return Span(
        aria_label="Measured" if measured else "Estimated",
        title="Measured" if measured else "Estimated: the total shows its margin",
        role="img",
        cls="shrink-0 h-2 w-2 rounded-full " + ("bg-emerald-600" if measured else "bg-amber-400"),
    )


def _chat_label(event, without_meal: bool) -> str:
    if event is not None:
        return meal_option_label(event)
    return "No meal" if without_meal else "New meal"


def _meal_value(event, without_meal: bool) -> str:
    """The meal of the chat as the composer sends it (`intake_event_id`)."""
    if event is not None:
        return str(event.id)
    return NO_MEAL_CHOICE if without_meal else ""




def _preparation_chips(portion, field_name: str, options: tuple):
    """The values DiaBot offered for one preparation field of a food (§9.11): one
    tap sets it, without the assistant. The one set is dark, as a chosen pill, and
    tapping it again unsets it, to undo a wrong tap."""
    current_value = getattr(portion, field_name)
    current = current_value.value if current_value else None
    labels = PREPARATION_LABELS[field_name]
    chips = []
    for value in options:
        chosen = value == current
        chips.append(
            Button(
                labels.get(value, value),
                type="button",
                aria_pressed="true" if chosen else "false",
                title="Tap again to unset" if chosen else None,
                hx_post=f"/assistant/preparation/{portion.id}",
                hx_vals=json.dumps({"field": field_name, "value": "" if chosen else value}),
                hx_include=f"#{CONVERSATION_INPUT_ID}",
                hx_target=f"#{MEAL_BAR_ID}",
                hx_swap="outerHTML",
                data_skip_page_loading="true",
                cls=pill_cls(chosen),
            )
        )
    return Div(
        Span(PREPARATION_FIELD_LABELS[field_name], cls="w-14 shrink-0 web_section_label"),
        Div(*chips, cls="flex flex-wrap gap-1.5"),
        role="group",
        aria_label=PREPARATION_FIELD_LABELS[field_name],
        cls="flex items-center gap-2",
    )


def _food_row(portion, pending: frozenset, offered: dict | None = None):
    to_review = (portion.origin.value, portion.origin_id) in pending
    return Li(
        Div(
            _confidence_dot(portion),
            Span(portion_name(portion), cls="flex-1 min-w-0 truncate text-sm font-medium text-gray-900"),
            Span("To review", cls="shrink-0 text-[11px] font-semibold text-warning") if to_review else None,
            Span(
                f"{portion.amount:g} g · {_carbs_text(portion_carbs(portion))}",
                cls="shrink-0 text-xs text-muted",
            ),
            cls="flex items-center gap-2",
        ),
        *(_preparation_chips(portion, name, options) for name, options in (offered or {}).items()),
        cls="flex flex-col gap-1.5 rounded-xl bg-white/70 border border-line-soft px-3 py-2",
    )


def _plate_groups(portions: list, plates: list) -> list[tuple[str, list]]:
    """The meal's foods by plate, in the meal's order, each with its visible name
    (§4.6.3 of measurement_conventions); empty plates are left out."""
    by_plate: dict[int, list] = {}
    for portion in portions:
        by_plate.setdefault(portion.plate_id, []).append(portion)
    groups = [(plate_label(plate, by_plate[plate.id]), by_plate.pop(plate.id)) for plate in plates if plate.id in by_plate]
    # A row whose plate was not read with the meal still shows, last.
    groups.extend(("Plate", group) for group in by_plate.values())
    return groups


def _meal_foods(portions: list, pending: frozenset, preparation: dict | None = None, plates: list | None = None):
    """The meal's foods (§9.11). Open by default; assistant.js folds them into the
    summary line as soon as they take more than MEAL_FOLD_SHARE of the chat's
    height, and keeps them open only while the user wants (`Show all`). Opened,
    they scroll inside, so they never cover the whole chat."""
    if not portions:
        return None
    preparation = preparation or {}

    def food_list(group):
        return Ul(*(_food_row(portion, pending, preparation.get(portion.id)) for portion in group), cls="flex flex-col gap-1.5")

    groups = _plate_groups(portions, plates or [])
    if len(groups) <= 1:
        content = food_list(portions)
    else:
        # A meal in several plates (tandas): the last one, where DiaBot adds, open;
        # the earlier ones folded into their name, foods and carbs.
        blocks = []
        for index, (label, group) in enumerate(groups):
            last = index == len(groups) - 1
            blocks.append(
                Details(
                    Summary(
                        Span(label, cls="flex-1 min-w-0 truncate web_section_label"),
                        Span(
                            f"{len(group)} · {_range_text(group)}",
                            cls="shrink-0 text-xs text-muted tabular-nums",
                        ),
                        Span("▾", aria_hidden="true", cls="shrink-0 text-xs text-muted group-open/plate:rotate-180"),
                        cls="flex items-center gap-2 cursor-pointer list-none [&::-webkit-details-marker]:hidden px-1 py-0.5",
                    ),
                    Div(food_list(group), cls="pt-1"),
                    open=last,
                    cls="group/plate",
                )
            )
        content = Div(*blocks, cls="flex flex-col gap-1.5")
    rows = Div(content, data_meal_rows="true", data_meal_count=str(len(portions)))
    estimated = sum(portion_carbs_margin(portion) > MEASURED_MARGIN_MAX for portion in portions)
    summary = f"{len(portions)} food" + ("s" if len(portions) != 1 else "") + (
        f" · {estimated} estimated" if estimated else ""
    )
    return Details(
        Summary(
            Span(*(_confidence_dot(portion) for portion in portions[:8]), cls="flex items-center gap-1"),
            Span(summary, cls="flex-1 min-w-0 truncate text-sm font-semibold"),
            Span("Show all ▾", cls="shrink-0 text-xs text-muted group-open:hidden"),
            Span("Hide ▴", cls="shrink-0 text-xs text-muted hidden group-open:inline"),
            data_meal_fold_toggle="true",
            cls="""
                hidden group-data-[foldable]:flex items-center gap-2 cursor-pointer list-none
                [&::-webkit-details-marker]:hidden
                rounded-xl bg-white/70 border border-line-soft px-3 py-2
            """,
        ),
        Div(
            rows,
            data_meal_scroll="true",
            cls="group-data-[foldable]:pt-1.5 group-data-[foldable]:max-h-[45dvh] overflow-y-auto overscroll-contain",
        ),
        open=True,
        data_meal_fold=str(MEAL_FOLD_SHARE),
        cls="group",
    )


def MealBar(
    event,
    portions: list,
    *,
    without_meal: bool = False,
    pending: frozenset = frozenset(),
    preparation: dict | None = None,
    plates: list | None = None,
    oob: bool = False,
):
    """The fixed bar (§9.11): Back, the pill of the chat, which opens the list of
    chats, the meal's carbs and the cart; under it the meal's foods. `event` None:
    a new meal, or a chat without a meal. It carries the meal the composer sends."""
    carbs = _range_text(portions) if event is not None else None
    return Div(
        Div(
            Button(
                "‹ Back",
                type="button",
                cls="shrink-0 text-sm font-medium text-gray-700 cursor-pointer px-1 py-1",
                onclick=back_js("/menu"),
            ),
            Button(
                Span(_chat_label(event, without_meal), cls="truncate"),
                Span("▾", aria_hidden="true", cls="text-xs text-muted"),
                type="button",
                aria_label=f"Chats. Now: {_chat_label(event, without_meal)}",
                onclick=open_modal_js(CHATS_MODAL_ID),
                cls="""
                    min-w-0 max-w-[60%] flex items-center gap-1.5 cursor-pointer
                    rounded-full bg-control border border-line px-3 py-1.5 text-sm font-semibold text-gray-900
                """,
            ),
            Div(
                Span(carbs, title="Carbs, with the margin of what is estimated", cls="text-base font-bold text-gray-900 tabular-nums")
                if carbs is not None
                else None,
                _cart_button(),
                cls="shrink-0 flex items-center gap-2",
            ),
            cls="flex items-center justify-between gap-2",
        ),
        _meal_foods(portions, pending, preparation, plates) if event is not None else None,
        Input(
            type="hidden",
            id=MEAL_SELECT_ID,
            name="intake_event_id",
            value=_meal_value(event, without_meal),
        ),
        id=MEAL_BAR_ID,
        cls="w-full flex flex-col gap-2.5",
        **({"hx_swap_oob": "true"} if oob else {}),
    )


def _chat_link(label, url: str, *, meta: str = "", current: bool = False):
    return A(
        Span(label, cls="flex-1 min-w-0 truncate text-sm font-semibold text-gray-900"),
        Span(meta, cls="shrink-0 text-xs text-muted") if meta else None,
        href=url,
        hx_get=url,
        hx_target="#main_content",
        hx_push_url="true",
        onclick=close_modal_js(CHATS_MODAL_ID),
        aria_current="true" if current else None,
        cls="flex items-center gap-2 rounded-xl px-3 py-2.5 bg-white border "
        + ("border-ink border-2" if current else "border-line-soft"),
    )


_HIDE_ICON = NotStr(
    '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="h-4 w-4">'
    '<path d="M4 6h12"/><path d="M8 6V4.5h4V6"/><path d="M5.5 6l.8 9.5h7.4l.8-9.5"/></svg>'
)


def _meal_free_row(chat, current: bool):
    """A `No meal` chat in the list, with the button that hides it from the list
    (§9.11): it is kept, and still shows in the past chats."""
    return Div(
        Div(
            _chat_link(
                chat.preview,
                f"/assistant?{urlencode({'conversation_id': chat.conversation_id})}",
                meta=f"{to_local(chat.updated_at):%d %b}",
                current=current,
            ),
            cls="flex-1 min-w-0",
        ),
        Button(
            _HIDE_ICON,
            type="button",
            aria_label=f"Delete chat {chat.preview}",
            title="Delete from this list (it stays in Past chats)",
            hx_post=f"/assistant/conversations/{chat.conversation_id}/hide",
            hx_target="closest [data-chat-row]",
            hx_swap="outerHTML",
            data_skip_page_loading="true",
            cls="""
                shrink-0 h-9 w-9 rounded-full cursor-pointer text-muted
                hover:text-danger hover:bg-danger/5 active:scale-95 transition
                flex items-center justify-center
            """,
        ),
        data_chat_row="true",
        cls="flex items-center gap-1.5",
    )


def _chats_section(title: str, *rows):
    return Div(
        Span(title, cls="web_section_label px-1"),
        *rows,
        cls="flex flex-col gap-1.5",
    )


def ChatsModal(
    events: list,
    carbs_by_event: dict,
    meal_free_chats: list,
    *,
    current_event_id: int | None,
    current_conversation_id: int | None,
    oob: bool = False,
):
    """The list of chats (§9.11): the planned meals, a new meal, the latest chats
    without a meal and the past chats. Each row loads the page with its URL."""
    planned = [
        _chat_link(
            meal_option_label(event),
            f"/assistant?{urlencode({'intake_event_id': event.id})}",
            meta=_carbs_text(carbs_by_event.get(event.id, 0.0)),
            current=event.id == current_event_id,
        )
        for event in events
    ]
    meal_free = [_meal_free_row(chat, chat.conversation_id == current_conversation_id) for chat in meal_free_chats[:MEAL_FREE_CHATS_SHOWN]]
    new_meal_url = "/assistant?new_meal=1"
    new_chat_url = f"/assistant?{urlencode({'intake_event_id': NO_MEAL_CHOICE, 'new_chat': 1})}"
    content = Div(
        Div(
            H2("Your chats", cls="text-lg font-bold text-gray-900"),
            modal_icon_button("×", aria_label="Close", onclick=close_modal_js(CHATS_MODAL_ID)),
            cls="flex items-center justify-between",
        ),
        _chats_section(
            "Planned meals",
            *(planned or [P("No planned meals.", cls="text-sm text-muted px-1")]),
            _chat_link("+ New meal", new_meal_url),
        ),
        _chats_section("No meal · new foods and recipes", *meal_free, _chat_link("+ New chat", new_chat_url)),
        A(
            "Past chats ›",
            href="/assistant/history",
            hx_get="/assistant/history",
            hx_target="#main_content",
            hx_push_url="true",
            onclick=close_modal_js(CHATS_MODAL_ID),
            cls="text-sm font-medium text-muted px-1",
        ),
        cls="flex flex-col gap-4",
    )
    return Div(
        ModalLayer(content, modal_id=CHATS_MODAL_ID, card_cls="gap-4 max-h-[85vh] overflow-y-auto"),
        id="assistant_chats_box",
        **({"hx_swap_oob": "true"} if oob else {}),
    )


def ConversationIdInput(conversation_id: int | None, *, oob: bool = False):
    """The conversation the next message continues; empty starts one (§9.11)."""
    return Input(
        type="hidden",
        id=CONVERSATION_INPUT_ID,
        name="conversation_id",
        value=str(conversation_id or ""),
        form=COMPOSER_FORM_ID,
        **({"hx_swap_oob": "true"} if oob else {}),
    )


def _user_bubble(turn: TurnView):
    parts = []
    if turn.photo_count:
        label = "Photo" if turn.photo_count == 1 else f"{turn.photo_count} photos"
        parts.append(Span(label, cls="inline-block text-[11px] rounded-full bg-white/70 border border-line px-2 py-0.5 w-fit"))
    if turn.user_text:
        parts.append(P(turn.user_text, cls="text-sm whitespace-pre-wrap break-words"))
    return Div(
        *parts,
        cls="self-end max-w-[85%] rounded-2xl rounded-br-md bg-control border border-line px-3 py-2 flex flex-col gap-1",
    )


def _reply_bubble(text: str):
    return Div(
        P(text, cls="text-sm text-gray-900 whitespace-pre-wrap break-words"),
        cls="self-start max-w-[85%] web_container rounded-2xl rounded-bl-md px-3 py-2",
    )


def _added_line(card: AddedCard):
    if card.kind == "recipe":
        amount = f"{card.servings:g} servings" if card.servings else "whole recipe"
        meta = ["Recipe", amount]
    elif card.kind == "fridge":
        meta = ["From the fridge", f"{card.grams:g} g" if card.grams is not None else ""]
        if card.carbs_g is not None:
            meta.append(f"{card.carbs_g:g} g carbs")
    else:
        meta = [f"{card.grams:g} g" if card.grams is not None else ""]
        if card.carbs_g is not None:
            meta.append(f"{card.carbs_g:g} g carbs")
        if card.amount_method:
            try:
                meta.append(AMOUNT_METHOD_LABELS[AmountMethod(card.amount_method)])
            except ValueError:
                pass
        if card.preparation:
            meta.append(card.preparation)
    return Li(
        Span(card.name, cls="text-sm text-gray-900 min-w-0 break-words"),
        Span(" · ".join(part for part in meta if part), cls="text-[11px] text-gray-500"),
        cls="flex flex-col",
    )


def _review_button():
    return Button(
        "Review",
        type="button",
        cls="web_button px-3 py-1 text-xs",
        hx_get="/cart",
        hx_target="#main_content",
        hx_push_url="true",
        **{"hx-on:click": "dbOpenCartFromAssistant();"},
    )


def _cart_card(title: str, lines: list):
    """What the assistant did in the cart (§9.11), with `Review`, which opens it."""
    return Div(
        Div(
            Span(title, cls="web_section_label"),
            _review_button(),
            cls="flex items-center justify-between gap-2",
        ),
        Ul(*lines, cls="flex flex-col gap-1.5"),
        cls="self-start w-full max-w-[85%] web_container rounded-2xl px-3 py-2 flex flex-col gap-2",
    )


def _added_card(cards: list[AddedCard]):
    return _cart_card("Added to the cart", [_added_line(card) for card in cards])


def _changed_card(lines: list[str]):
    return _cart_card(
        "Changed in the cart",
        [Li(line, cls="text-sm text-gray-900 min-w-0 break-words") for line in lines],
    )


_STORED_TITLES = {
    StorageLocation.FRIDGE.value: "Stored in the fridge",
    StorageLocation.FREEZER.value: "Stored in the freezer",
}


def _stored_card(cards: list[StoredCard]):
    """Containers the assistant stored (§9.11), with `Fridge`, which opens it in Food."""
    titles = {_STORED_TITLES.get(card.location, "Stored") for card in cards}
    title = titles.pop() if len(titles) == 1 else "Stored in the fridge and freezer"
    return Div(
        Div(
            Span(title, cls="web_section_label"),
            Button(
                "Fridge",
                type="button",
                cls="web_button px-3 py-1 text-xs",
                hx_get="/food?filter=fridge",
                hx_target="#main_content",
                hx_push_url="true",
            ),
            cls="flex items-center justify-between gap-2",
        ),
        Ul(
            *(
                Li(
                    Span(card.name, cls="text-sm text-gray-900 min-w-0 break-words"),
                    Span(
                        " · ".join(
                            part
                            for part in (
                                "Freezer" if card.location == StorageLocation.FREEZER.value else "Fridge",
                                f"{card.grams:g} g" if card.grams is not None else "",
                            )
                            if part
                        ),
                        cls="text-[11px] text-gray-500",
                    ),
                    cls="flex flex-col",
                )
                for card in cards
            ),
            cls="flex flex-col gap-1.5",
        ),
        cls="self-start w-full max-w-[85%] web_container rounded-2xl px-3 py-2 flex flex-col gap-2",
    )


def RemovalRow(card: RemovalCard, conversation_id: int, *, removed: bool = False, read_only: bool = False):
    """A food DiaBot proposes to remove (§9.11): only the user's tap on `Remove`
    removes it. Once gone, the row says so instead."""
    grams = f"{card.grams:g} g" if card.grams is not None else None
    if removed:
        action = Span("Removed", cls="shrink-0 text-xs font-semibold text-muted")
    elif read_only:
        action = None
    else:
        action = Button(
            "Remove",
            type="button",
            cls="shrink-0 rounded-full px-3 py-1 text-xs font-semibold border border-danger text-danger bg-white/70 hover:bg-white cursor-pointer active:scale-95",
            hx_post=f"/assistant/remove/{card.portion_id}",
            hx_vals=json.dumps({"conversation_id": str(conversation_id)}),
            hx_target="closest [data-removal-row]",
            hx_swap="outerHTML",
            hx_disabled_elt="this",
            data_skip_page_loading="true",
        )
    return Li(
        Div(
            Span(card.name, cls="text-sm min-w-0 break-words " + ("text-gray-400 line-through" if removed else "text-gray-900")),
            Span(grams, cls="text-[11px] text-gray-500") if grams else None,
            cls="flex flex-col min-w-0",
        ),
        action,
        data_removal_row="true",
        cls="flex items-center justify-between gap-3",
    )


def _removal_card(cards: list[RemovalCard], conversation_id: int, meal_rows: frozenset | None, read_only: bool):
    """What DiaBot proposes to take out of the meal (§9.11, "Quitar del carrito").
    `meal_rows`: the rows the meal still has; a row not in it shows as removed
    (None: unknown, every row keeps its button)."""
    return Div(
        Span("Remove from the cart?", cls="web_section_label"),
        Ul(
            *(
                RemovalRow(
                    card,
                    conversation_id,
                    removed=meal_rows is not None and card.portion_id not in meal_rows,
                    read_only=read_only,
                )
                for card in cards
            ),
            cls="flex flex-col gap-2",
        ),
        cls="self-start w-full max-w-[85%] web_container rounded-2xl px-3 py-2 flex flex-col gap-2",
    )


# The create form of each kind of draft (frontend §9.11): a recipe and a dish say
# so in their tool result's `source`; any other source is a catalog food.
_DRAFT_FORM_PATHS = {
    RECIPE_DRAFT_SOURCE: "/food/create/recipe/form",
    MANUAL_INTAKE_DRAFT_SOURCE: "/food/create/manual_intake/form",
}
_DRAFT_TITLES = {
    RECIPE_DRAFT_SOURCE: "New recipe to review",
    MANUAL_INTAKE_DRAFT_SOURCE: "New dish to review",
}


def draft_form_url(card: DraftCard, conversation_id: int) -> str:
    """The create form prefilled with a draft (§9.11). The form reads the draft from
    its stored tool call; saving a food comes back here."""
    path = _DRAFT_FORM_PATHS.get(card.source, "/food/create/catalog/form")
    query = urlencode(
        {
            "assistant_message": card.message_id,
            "assistant_tool": card.tool_use_id,
            "return_to_assistant": conversation_id,
        }
    )
    return f"{path}?{query}"


_DRAFT_SOURCE_LABELS = {
    AssistantDraftSource.CIQUAL.value: "From the food composition table",
    AssistantDraftSource.OPEN_FOOD_FACTS.value: "From Open Food Facts",
    AssistantDraftSource.LABEL.value: "Read from the label",
    AssistantDraftSource.ESTIMATE.value: "Estimated by the assistant",
}


def _draft_subtitle(card: DraftCard) -> str:
    if card.source == RECIPE_DRAFT_SOURCE:
        count = card.ingredients or 0
        return f"{count} ingredient{'s' if count != 1 else ''}"
    if card.source == MANUAL_INTAKE_DRAFT_SOURCE:
        return "Dish proposed by the assistant"
    return _DRAFT_SOURCE_LABELS.get(card.source, "")


def _draft_card(card: DraftCard, conversation_id: int):
    title = _DRAFT_TITLES.get(card.source, "New food to review")
    return Div(
        Div(
            Span(title, cls="web_section_label"),
            P(card.name, cls="text-sm text-gray-900 break-words"),
            P(_draft_subtitle(card), cls="text-[11px] text-gray-500"),
            cls="flex flex-col min-w-0",
        ),
        Button(
            "Review and save",
            type="button",
            cls="web_button web_button_primary px-3 py-1.5 text-xs shrink-0",
            hx_get=draft_form_url(card, conversation_id),
            hx_target="#main_content",
            hx_push_url="true",
        ),
        cls="self-start w-full max-w-[85%] web_container rounded-2xl px-3 py-2 flex items-center justify-between gap-3",
    )


_PROVISIONAL_TITLES = {
    FoodEntryType.CATALOG.value: "New food added",
    FoodEntryType.MANUAL_INTAKE.value: "New dish added",
}


def review_form_url(entry_type: str, entry_id: int, return_to: str) -> str:
    """The edit form of a provisional food or dish, which comes back to `return_to`."""
    return f"/food/edit/{entry_type}/{entry_id}/form?{urlencode({'return_to': return_to})}"


def _provisional_card(card: ProvisionalCard, conversation_id: int, pending: frozenset):
    """A provisional food or dish created and added (§9.11): what the assistant
    filled in, and Review while it is still to review."""
    to_review = (card.entry_type, card.entry_id) in pending
    source = MACROS_SOURCE_LABELS.get(_macros_source(card.macros_source))
    about = " · ".join(
        part
        for part in (
            card.brand_or_origin,
            f"{_fmt(card.carbs_100g)} g carbs/100 g" if card.carbs_100g is not None else None,
            source,
        )
        if part
    )
    added = " · ".join(
        part
        for part in (
            f"{_fmt(card.grams)} g" if card.grams is not None else None,
            f"{_fmt(card.carbs_g)} g carbs" if card.carbs_g is not None else None,
        )
        if part
    )
    status = (
        Span("To review", cls="text-[11px] rounded-full bg-amber-50 border border-amber-200 text-amber-800 px-2 py-0.5")
        if to_review
        else Span("Reviewed", cls="text-[11px] text-gray-500")
    )
    return Div(
        Div(
            Div(
                Span(_PROVISIONAL_TITLES.get(card.entry_type, "New food added"), cls="web_section_label"),
                status,
                cls="flex items-center gap-2",
            ),
            P(card.name, cls="text-sm text-gray-900 break-words"),
            P(about, cls="text-[11px] text-gray-500") if about else None,
            P(f"Added: {added}", cls="text-[11px] text-gray-500") if added else None,
            cls="flex flex-col min-w-0",
        ),
        Button(
            "Review",
            type="button",
            cls="web_button web_button_primary px-3 py-1.5 text-xs shrink-0",
            hx_get=review_form_url(card.entry_type, card.entry_id, f"assistant:{conversation_id}"),
            hx_target="#main_content",
            hx_push_url="true",
        )
        if to_review
        else None,
        cls="self-start w-full max-w-[85%] web_container rounded-2xl px-3 py-2 flex items-center justify-between gap-3",
    )


def _repeat_card(card: RepeatCard, conversation_id: int):
    """A quick add eaten often enough to offer saving it (§9.11, "Repeticiones")."""
    if card.save_as == RepeatSaveAs.RECIPE.value:
        # A recipe needs its ingredients: the button asks the assistant for the draft.
        action = Button(
            "Save as recipe",
            type="button",
            cls="web_button px-3 py-1.5 text-xs shrink-0",
            data_assistant_prompt=f"Save {card.name} as a recipe.",
        )
    else:
        action = Button(
            "Save as dish",
            type="button",
            cls="web_button px-3 py-1.5 text-xs shrink-0",
            hx_post=f"/assistant/repeat/{card.quick_add_id}/dish",
            hx_vals=f'{{"conversation_id": "{conversation_id}"}}',
            hx_target="closest [data-repeat-card]",
            hx_swap="outerHTML",
            hx_disabled_elt="this",
        )
    return Div(
        Div(
            Span("You eat this often", cls="web_section_label"),
            P(card.name, cls="text-sm text-gray-900 break-words"),
            P(f"Logged {card.count} times in 90 days", cls="text-[11px] text-gray-500"),
            cls="flex flex-col min-w-0",
        ),
        action,
        data_repeat_card="true",
        cls="self-start w-full max-w-[85%] web_container rounded-2xl px-3 py-2 flex items-center justify-between gap-3",
    )


def RepeatSavedCard(name: str, entry_id: int, conversation_id: int):
    """The repeat card once its dish is saved: it links to the new provisional dish."""
    return Div(
        Div(
            Span("Saved as dish", cls="web_section_label"),
            P(name, cls="text-sm text-gray-900 break-words"),
            P("Review it when you can.", cls="text-[11px] text-gray-500"),
            cls="flex flex-col min-w-0",
        ),
        Button(
            "Review",
            type="button",
            cls="web_button web_button_primary px-3 py-1.5 text-xs shrink-0",
            hx_get=review_form_url(FoodEntryType.MANUAL_INTAKE.value, entry_id, f"assistant:{conversation_id}"),
            hx_target="#main_content",
            hx_push_url="true",
        ),
        data_repeat_card="true",
        cls="self-start w-full max-w-[85%] web_container rounded-2xl px-3 py-2 flex items-center justify-between gap-3",
    )


def _macros_source(value):
    try:
        return MacrosSource(value) if value else None
    except ValueError:
        return None


def _fmt(value: float) -> str:
    return f"{value:.0f}" if float(value).is_integer() else f"{value:.1f}"


def _notice(text: str):
    return P(text, cls="self-start text-xs text-amber-800 px-1")


# Faces of the DiaBot avatar; all are stacked and the state shows one (§9.11).
_AVATAR_FACES = ("thinking", "normal", "confused")


def _avatar(state: str):
    """DiaBot's face beside its messages; static/js/assistant.js changes `data-avatar`."""
    return Span(
        *(
            Img(src=f"/images/diabot/diabot_{face}.svg", alt="", data_avatar_face=face, cls="db_avatar_face")
            for face in _AVATAR_FACES
        ),
        data_avatar=state,
        aria_hidden="true",
        cls="db_avatar relative shrink-0 h-10 w-10 -mb-1",
    )


def _bot_row(*children):
    """The assistant's messages of a turn with its avatar at their bottom left, as in a chat app."""
    return Div(
        _avatar("normal"),
        Div(*children, cls="flex-1 min-w-0 flex flex-col gap-2"),
        cls="w-full flex items-end gap-2",
    )


def _guide_question(turn: TurnView, *, open_: bool):
    """A question about the guide (§9.11): folded into one line, open only while it
    is the latest turn. Kept for the study; the model does not see it again."""
    return Details(
        Summary(
            Span("?", aria_hidden="true", cls="shrink-0 h-5 w-5 rounded-full bg-control border border-line text-[11px] font-bold flex items-center justify-center"),
            Span(turn.user_text or "Question", cls="flex-1 min-w-0 truncate text-sm text-gray-800"),
            Span("Guide", cls="shrink-0 web_section_label"),
            cls="""
                flex items-center gap-2 cursor-pointer list-none [&::-webkit-details-marker]:hidden
                web_container rounded-2xl px-3 py-2
            """,
        ),
        Div(
            _bot_row(
                *(_reply_bubble(text) for text in turn.replies),
                A(
                    "See it in the guide ›",
                    href="/settings/guide",
                    hx_get="/settings/guide",
                    hx_target="#main_content",
                    hx_push_url="true",
                    cls="text-xs font-medium text-muted px-1",
                ),
            ),
            cls="pt-2",
        ),
        open=open_,
        cls="w-full scroll-mt-48",
    )


def _quick_replies(options: list[str]):
    """The answer buttons under DiaBot's question (§9.11), on the latest turn
    only: a tap sends the option as the user's message (static/js/assistant.js)."""
    return Div(
        *(
            Button(
                option,
                type="button",
                data_quick_reply=option,
                cls="""
                    web_button rounded-full px-3.5 py-1.5 text-sm font-medium
                    active:scale-95 transition-transform
                """,
            )
            for option in options
        ),
        data_quick_replies="true",
        role="group",
        aria_label="Quick answers",
        cls="flex flex-wrap gap-2 pl-10",
    )


def TurnBlock(
    turn: TurnView,
    conversation_id: int,
    notices: list[str] | None = None,
    pending: frozenset = frozenset(),
    *,
    read_only: bool = False,
    latest: bool = False,
    meal_rows: frozenset | None = None,
):
    """One message of the user and what the assistant did for it (§9.11).
    `pending`: the (entry_type, id) of the provisional entries still to review.
    `read_only` (a past chat): without the cards that only offer an action
    (save a repetition, review a draft), which belong to the live chat.
    `meal_rows`: the ids of the meal's rows now, for the removal cards."""
    if turn.is_guide_question:
        return _guide_question(turn, open_=latest)
    bot = [
        *(_reply_bubble(text) for text in turn.replies),
        _added_card(turn.added) if turn.added else None,
        *(_provisional_card(card, conversation_id, pending) for card in turn.provisional),
        *(() if read_only else (_repeat_card(card, conversation_id) for card in turn.repeats)),
        _changed_card(turn.changed) if turn.changed else None,
        _stored_card(turn.stored) if turn.stored else None,
        _removal_card(turn.removals, conversation_id, meal_rows, read_only) if turn.removals else None,
        *(() if read_only else (_draft_card(card, conversation_id) for card in turn.drafts)),
        *(_notice(text) for text in (notices or [])),
    ]
    return Div(
        _user_bubble(turn),
        _bot_row(*bot) if any(bot) else None,
        _quick_replies(turn.quick_replies) if latest and not read_only and turn.quick_replies else None,
        # Scrolled to below the fixed top bar, not under it.
        cls="w-full flex flex-col gap-2 scroll-mt-48",
    )


def _typing_dots():
    # Three dots that rise in turn while the answer comes (§9.11, static/css/input.css).
    return Span(
        Span(cls="db_typing_dot"),
        Span(cls="db_typing_dot"),
        Span(cls="db_typing_dot"),
        aria_hidden="true",
        cls="flex items-end gap-1 pb-1 text-gray-500",
    )


def assistant_turn_dom_id(turn_id: int) -> str:
    return f"assistant_turn_{turn_id}"


def PendingTurnBlock(turn: AssistantTurnRead):
    """A message the assistant is answering in the background (code_conventions.md
    §8.12): what the user sent and `Thinking`, asked for again every 2 s until the
    answer replaces it. Also drawn on coming back to the page while it waits."""
    return Div(
        _user_bubble(turn),
        Div(
            _avatar("thinking"),
            Div(
                Span("Thinking", cls="text-sm text-gray-500"),
                _typing_dots(),
                cls="flex items-end gap-1.5 web_container rounded-2xl rounded-bl-md px-3 py-2",
            ),
            role="status",
            cls="flex items-end gap-2 self-start",
        ),
        id=assistant_turn_dom_id(turn.id),
        hx_get=f"/assistant/turn/{turn.id}",
        hx_trigger="every 2s",
        hx_swap="outerHTML",
        data_skip_page_loading="true",
        cls="w-full flex flex-col gap-2 scroll-mt-48",
    )


def FailedTurnBlock(turn: AssistantTurnRead):
    """A message the assistant could not answer: nothing was stored, so the text
    goes back to an empty composer to send it again (static/js/assistant.js)."""
    return Div(
        _user_bubble(turn),
        _notice(turn.error_message or "The assistant could not answer. Send it again."),
        id=assistant_turn_dom_id(turn.id),
        data_assistant_failed_text=turn.user_text,
        cls="w-full flex flex-col gap-2 scroll-mt-48",
    )


def AssistantThread(
    turns: list[TurnView],
    conversation_id: int | None,
    pending: frozenset = frozenset(),
    *,
    new_meal: bool = False,
    tail=(),
    meal_rows: frozenset | None = None,
):
    """The conversation of the chosen meal; the intro while it is empty. `tail` is
    a message still being answered, or one that failed, drawn after it (§8.12).
    `meal_rows`: the ids of the meal's rows, for the removal cards."""
    tail = tuple(block for block in tail if block is not None)
    return Div(
        _intro(new_meal) if not turns and not tail else None,
        *(
            TurnBlock(
                turn,
                conversation_id,
                pending=pending,
                latest=index == len(turns) - 1 and not tail,
                meal_rows=meal_rows,
            )
            for index, turn in enumerate(turns)
        ),
        *tail,
        ConversationIdInput(conversation_id),
        id=THREAD_ID,
        cls="w-full flex flex-col gap-3",
    )


def _thinking():
    # On a failed send assistant.js keeps it shown with `db_failed` (§9.11).
    bubble = Div(
        # Only while the message is sent: the answer then waits in its own block.
        Span("Sending", data_thinking_only="true", cls="text-sm text-gray-500"),
        Span("Couldn't answer", data_failed_only="true", cls="text-sm text-gray-500"),
        Span(_typing_dots(), data_thinking_only="true"),
        cls="flex items-end gap-1.5 web_container rounded-2xl rounded-bl-md px-3 py-2",
    )
    return Div(
        _avatar("thinking"),
        bubble,
        id="assistant_thinking",
        role="status",
        cls="hidden [&.htmx-request]:flex items-end gap-2 self-start",
    )


PLUS_ROW_ID = "assistant_plus_row"


def _count_text(count: float) -> str:
    rounded = round(count * 2) / 2  # the menu steps are halves
    return f"×{rounded:g}"


def PlusRow(buttons: list, conversation_id: int | None, *, oob: bool = False):
    """The +1 buttons over the composer (§9.11): one more of a row of the meal, at
    once and without the assistant. Held, a small menu with +½, +2 and −1
    (static/js/assistant.js)."""
    chips = [
        Button(
            Span(f"+1 {button.name}", cls="truncate max-w-[9rem]"),
            Span(_count_text(button.count), cls="text-[11px] text-gray-500 shrink-0"),
            type="button",
            data_plus_url=f"/assistant/plus/{button.portion_id}",
            data_plus_count=f"{button.count:.2f}",
            aria_label=f"One more {button.name}, now {_count_text(button.count)}",
            cls="""
                web_button shrink-0 rounded-full px-3 py-1.5 text-xs
                flex items-center gap-1.5 select-none touch-manipulation
                [-webkit-touch-callout:none]
            """,
        )
        for button in buttons
    ]
    attrs = {"hx-swap-oob": "true"} if oob else {}
    return Div(
        *chips,
        id=PLUS_ROW_ID,
        data_conversation_id=str(conversation_id or ""),
        aria_label="Add one more",
        cls="flex gap-1.5 overflow-x-auto overscroll-contain empty:hidden px-1 pb-0.5 [scrollbar-width:none]",
        **attrs,
    )


def UsualRow(foods: list):
    """"Usual now" over the composer of an empty chat (§9.11): the foods eaten most
    around this time. A tap writes `/Name 150 g` in the box as a mention, so
    several go in one message (static/js/assistant.js); nothing is sent yet."""
    if not foods:
        return None
    return Div(
        Span("Usual now", cls="shrink-0 web_section_label pl-1"),
        *(
            Button(
                Span(food.name, cls="truncate max-w-[9rem]"),
                Span(f"{food.grams:g} g", cls="text-[11px] text-muted shrink-0"),
                type="button",
                data_usual_type=food.entry_type,
                data_usual_id=str(food.entry_id),
                data_usual_name=food.name,
                data_usual_grams=f"{food.grams:g}",
                aria_label=f"Add {food.name}, {food.grams:g} g, to the message",
                cls="""
                    web_button shrink-0 rounded-full px-3 py-1.5 text-xs
                    flex items-center gap-1.5 active:scale-95 transition-transform
                """,
            )
            for food in foods
        ),
        data_usual_row="true",
        role="group",
        aria_label="Usual now",
        cls="flex items-center gap-1.5 overflow-x-auto overscroll-contain px-1 pb-0.5 [scrollbar-width:none]",
    )


def _composer():
    return Form(
        # Suggestions after `/`: they open above the composer, like a command list.
        Div(
            Div(
                id=MENTIONS_LIST_ID,
                role="listbox",
                aria_label="Your foods",
                cls="flex flex-col gap-1",
                data_skip_page_loading="true",
                **{"hx-sync": "this:replace"},
            ),
            id="assistant_mentions_popup",
            hidden=True,
            cls="""
                absolute bottom-full left-0 right-0 mb-2 z-40
                max-h-72 overflow-y-auto overscroll-contain
                rounded-2xl bg-white border border-line shadow-lg p-1.5
            """,
        ),
        Div(id="assistant_mention_chips", cls="flex flex-wrap gap-1.5 empty:hidden"),
        # One thumbnail per attached photo, drawn by assistant.js (§9.11).
        Div(id="assistant_photos", aria_label="Attached photos", cls="flex flex-wrap gap-2 empty:hidden"),
        Div(
            Label(
                _PHOTO_ICON,
                # The picker only: assistant.js keeps the chosen photos and sends them.
                Input(type="file", id="assistant_photo", accept="image/*", multiple=True, cls="sr-only"),
                aria_label="Attach photos",
                title="Attach photos",
                cls="""
                    shrink-0 h-9 w-9 rounded-full border border-line bg-white text-gray-600
                    flex items-center justify-center cursor-pointer
                """,
            ),
            Label("Message", cls="sr-only", **{"for": "assistant_input"}),
            Textarea(
                id="assistant_input",
                name="message",
                rows="1",
                placeholder="What did you eat? / for your foods",
                autocomplete="off",
                maxlength=str(ASSISTANT_TEXT_MAX_LENGTH),
                cls="""
                    web_input flex-1 min-w-0 resize-none
                    rounded-xl border border-line px-3 py-2 text-sm
                    max-h-40 overflow-y-auto
                """,
                **{"aria-autocomplete": "list", "aria-controls": MENTIONS_LIST_ID},
            ),
            Button(
                _SEND_ICON,
                type="submit",
                id="assistant_send",
                disabled=True,
                aria_label="Send",
                cls="""
                    web_button web_button_primary shrink-0 h-9 w-9 rounded-full
                    flex items-center justify-center disabled:opacity-40
                """,
            ),
            cls="flex items-end gap-2",
        ),
        Input(type="hidden", id="assistant_mentions_value", name="mentions", value="[]"),
        id=COMPOSER_FORM_ID,
        hx_post="/assistant/message",
        hx_encoding="multipart/form-data",
        data_photos_max=str(ASSISTANT_PHOTOS_MAX),
        hx_target=f"#{THREAD_ID}",
        hx_swap="beforeend",
        hx_include=f"#{MEAL_SELECT_ID}, #{CONVERSATION_INPUT_ID}",
        hx_indicator="#assistant_thinking",
        hx_disabled_elt="#assistant_send",
        data_skip_page_loading="true",
        cls="""
            relative w-full web_glass_strong rounded-2xl p-2
            flex flex-col gap-2
        """,
    )


def _top_bar(*children):
    # Fixed at the top, like Food's bar (§9.11): the meal stays at hand however
    # long the conversation is.
    return Div(
        *children,
        cls="sticky top-0 z-[600] w-full flex flex-col gap-3 px-5 pt-6 pb-4 web_glass_strong rounded-b-3xl",
    )


def AssistantPage(
    event,
    portions: list,
    conversation_id: int | None,
    turns: list[TurnView],
    chats,
    *,
    without_meal: bool = False,
    pending: frozenset = frozenset(),
    plus_buttons: list | None = None,
    preparation: dict | None = None,
    usual: list | None = None,
    plates: list | None = None,
    tail=(),
):
    """`chats`: the list of chats (ChatsModal), drawn with the page. `preparation`:
    the values offered per row of the meal and field. `usual`: "Usual now"."""
    return Div(
        _top_bar(
            MealBar(event, portions, without_meal=without_meal, pending=pending, preparation=preparation, plates=plates)
        ),
        Div(
            AssistantThread(
                turns,
                conversation_id,
                pending,
                new_meal=event is None and not without_meal,
                tail=tail,
                meal_rows=frozenset(portion.id for portion in portions),
            ),
            id=THREAD_BOX_ID,
            cls="w-full",
        ),
        _thinking(),
        # At the bottom of the screen, flush on the island's highest point
        # (--island-reach, measured by island_indicator.js); on desktop 12px
        # above it. In the flow (sticky, not fixed) so a phone
        # keyboard scrolls it into view.
        Div(
            UsualRow(usual or []) if not turns and not without_meal else None,
            PlusRow(plus_buttons or [], conversation_id),
            _composer(),
            cls="sticky bottom-[var(--island-reach,119px)] md:bottom-[calc(var(--island-reach,147px)+12px)] w-full mt-auto flex flex-col gap-2",
        ),
        chats,
        data_hide_cart="true",
        # Asked for again on coming back, with the conversation of its URL
        # (frontend_conventions.md §5).
        hx_history="false",
        cls="w-full max-w-2xl mx-auto px-4 pb-28 min-h-dvh flex flex-col gap-4",
    )


def PastChatPage(
    event, portions: list, turns: list[TurnView], pending: frozenset = frozenset(), conversation_id: int = 0
):
    """A past chat, read-only (§9.11): the meal and the conversation, without the
    composer or the +1 buttons. A confirmed meal is changed where it always is."""
    return Div(
        _top_bar(
            Div(
                Button(
                    "‹ Past chats",
                    type="button",
                    cls="shrink-0 text-sm font-medium text-gray-700 cursor-pointer px-1 py-1",
                    onclick=back_js("/assistant/history"),
                ),
                Span(_range_text(portions), cls="text-base font-bold text-gray-900 tabular-nums"),
                cls="flex items-center justify-between gap-2",
            ),
            Div(
                H1(meal_option_label(event), cls="flex-1 min-w-0 truncate text-xl font-bold text-gray-900 px-1"),
                # A new planned meal for now with what this one served (§9.11).
                Button(
                    "Repeat today",
                    type="button",
                    hx_post=f"/assistant/history/{conversation_id}/repeat",
                    hx_swap="none",
                    cls="web_button web_button_primary shrink-0 rounded-full px-4 py-2 text-sm",
                )
                if portions
                else None,
                cls="flex items-center gap-3",
            ),
            _meal_foods(portions, pending),
        ),
        Div(
            *(TurnBlock(turn, 0, pending=pending, read_only=True) for turn in turns),
            cls="w-full flex flex-col gap-3",
        ),
        P("Read-only: this meal is confirmed.", cls="text-xs text-muted text-center"),
        cls="w-full max-w-2xl mx-auto px-4 pb-40 min-h-dvh flex flex-col gap-4",
    )


def _past_chat_card(chat, event, portions: list):
    """A past chat (§9.11): a confirmed meal opens read-only; a `No meal` chat
    opens in the live page, where it can go on. A hidden one says so."""
    if event is not None:
        title = meal_option_label(event)
        names = ", ".join(portion_name(portion) for portion in portions[:4])
        if len(portions) > 4:
            names += f" and {len(portions) - 4} more"
        meta = _carbs_text(sum(portion_carbs(portion) for portion in portions))
        detail = names or "Nothing added"
        url = f"/assistant/history/{chat.conversation_id}"
    else:
        title = chat.preview
        meta = "No meal"
        detail = "New foods and recipes"
        url = f"/assistant?{urlencode({'conversation_id': chat.conversation_id})}"
    return A(
        Div(
            Span(title, cls="flex-1 min-w-0 truncate text-sm font-semibold text-gray-900"),
            Span("Deleted", cls="shrink-0 text-[11px] font-semibold text-muted rounded-full border border-line px-2 py-0.5")
            if chat.hidden
            else None,
            Span(meta, cls="shrink-0 text-xs text-muted"),
            cls="flex items-center gap-2",
        ),
        Span(detail, cls="text-xs text-muted truncate"),
        href=url,
        hx_get=url,
        hx_target="#main_content",
        hx_push_url="true",
        cls="web_container rounded-2xl px-4 py-3 flex flex-col gap-1" + (" opacity-70" if chat.hidden else ""),
    )


PAST_CHATS_LIST_ID = "past_chats_list"


def PastChatsPage(days: list, query: str = ""):
    """The past chats (§9.11): `days` is [(date, [(chat, event, portions)])], the
    latest first. Not the default: reached from the list of chats. The search
    filters them by what they say and by their foods."""
    sections = [
        Div(
            Span(f"{day:%A %d %b}".upper(), cls="web_section_label px-1"),
            *(_past_chat_card(chat, event, portions) for chat, event, portions in chats),
            cls="flex flex-col gap-2",
        )
        for day, chats in days
    ]
    if sections:
        listing = sections
    elif query:
        listing = [P(f"No chats match \u201c{query}\u201d.", cls="text-sm text-muted px-1")]
    else:
        listing = [P("No past chats yet: they appear once a meal is confirmed.", cls="text-sm text-muted px-1")]
    return Div(
        _top_bar(
            Button(
                "\u2039 Back",
                type="button",
                cls="self-start text-sm font-medium text-gray-700 cursor-pointer px-1 py-1",
                onclick=back_js("/assistant"),
            ),
            H1("Past chats", cls="text-2xl font-bold text-gray-900 px-1"),
            SearchField(
                "past_chats_search",
                "Search: sushi, La Tasca\u2026",
                name="q",
                value=query,
                hx_get="/assistant/history",
                hx_trigger="input changed delay:300ms, search",
                hx_target=f"#{PAST_CHATS_LIST_ID}",
                hx_select=f"#{PAST_CHATS_LIST_ID}",
                hx_swap="outerHTML",
                hx_replace_url="true",
                data_skip_page_loading="true",
            ),
        ),
        Div(*listing, id=PAST_CHATS_LIST_ID, cls="flex flex-col gap-4"),
        cls="w-full max-w-2xl mx-auto px-4 pb-40 min-h-dvh flex flex-col gap-4",
    )


def MentionOptions(rows: list[MentionSuggestion], searching: bool):
    """The `/` suggestions: one compact row per entry (§9.11)."""
    if not rows:
        message = "No foods match" if searching else "Type to search your foods"
        return P(message, cls="text-xs text-gray-600 px-2 py-1.5", data_mentions_empty="true")
    options = []
    for index, row in enumerate(rows):
        meta = [_ENTRY_TYPE_LABELS[row.entry_type]]
        if row.subtitle:
            meta.append(row.subtitle)
        if row.entry_type is not FoodEntryType.RECIPE:
            meta.append(carbs_meta(row.carbs_100g, row.serving_g))
        options.append(
            Button(
                Div(
                    Span(row.name or "Unnamed", cls=f"text-sm {MODAL_NAME_CLS}"),
                    Span(" · ".join(meta), cls="block max-w-full text-[11px] text-gray-500 truncate"),
                    cls="flex flex-col items-start min-w-0 flex-1",
                ),
                Span("★", aria_hidden="true", cls="shrink-0 text-sm text-amber-500") if row.is_favorite else "",
                type="button",
                role="option",
                id=f"assistant_mention_option_{index}",
                aria_selected="true" if index == 0 else "false",
                cls="""
                    w-full text-left px-3 py-1.5 rounded-lg cursor-pointer
                    border border-transparent hover:bg-control
                    aria-selected:bg-control aria-selected:border-line
                    transition-colors flex items-center justify-between gap-3
                """,
                data_mention_type=row.entry_type.value,
                data_mention_id=str(row.entry_id),
                data_mention_name=row.name,
            )
        )
    return Div(*options, cls="flex flex-col gap-0.5")
