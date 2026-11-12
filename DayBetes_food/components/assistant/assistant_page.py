"""Page of the assistant for logging meals (frontend_conventions.md §9.11).

Pure components (code_conventions.md §1.4): they receive data already read.
The `/` suggestions and the composer behavior live in static/js/assistant.js.
"""

from urllib.parse import urlencode

from fasthtml.common import *

from DayBetes_food.components.food.food_shared import AMOUNT_METHOD_LABELS
from DayBetes_food.components.food.foods import meal_option_label
from DayBetes_food.components.food.rescue import carbs_meta
from DayBetes_food.components.modal import MODAL_NAME_CLS
from DayBetes_food.components.navigation import back_js
from DayBetes_food.domain.assistant import ASSISTANT_TEXT_MAX_LENGTH, AddedCard, DraftCard, TurnView
from DayBetes_food.domain.constants import AmountMethod, AssistantDraftSource, FoodEntryType
from DayBetes_food.domain.food_entry import MentionSuggestion

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


def _header():
    return Div(
        Div(
            Button(
                "‹ Back",
                type="button",
                cls="text-sm font-medium text-gray-700 cursor-pointer px-1 py-1",
                onclick=back_js("/menu"),
            ),
            Div(
                Span("ASSISTANT", cls="web_section_label"),
                # The floating cart button is hidden here (data-hide-cart): this
                # small one opens the cart without covering the composer (§9.11).
                Button(
                    Img(src="/images/ui/cart.svg", alt="", cls="h-4 w-4"),
                    type="button",
                    aria_label="Open the cart",
                    cls="""
                        h-8 w-8 rounded-full bg-surface border border-line-soft
                        shadow-[0_2px_8px_rgba(80,60,40,0.12)] cursor-pointer
                        flex items-center justify-center active:scale-95 transition-transform
                    """,
                    hx_get="/cart",
                    hx_target="#main_content",
                    hx_push_url="true",
                ),
                cls="flex items-center gap-3",
            ),
            cls="flex items-center justify-between",
        ),
        H1("What did you eat?", cls="text-2xl font-bold text-gray-900"),
        cls="w-full px-1 flex flex-col gap-1",
    )


def _intro():
    return Div(
        P("Tell me what you ate, with amounts if you know them.", cls="text-sm text-gray-800"),
        P(
            "Type / to pin one of your foods, dishes or recipes, so I use exactly that one. "
            "You can also attach a photo of the dish or of a nutrition label.",
            cls="text-xs text-gray-500",
        ),
        cls="web_container w-full px-4 py-3 flex flex-col gap-1",
    )


def AssistantMealSelect(events: list, selected_id: int | None, *, oob: bool = False):
    """Which meal the conversation writes to (§9.11): the planned meals, and
    `New meal`, whose first add creates it. Changing it opens that meal's conversation."""
    options = [
        Option(meal_option_label(event), value=str(event.id), selected=(event.id == selected_id))
        for event in events
    ]
    options.append(Option("New meal", value="", selected=(selected_id is None)))
    return Div(
        Label("Add to", cls="web_section_label shrink-0", **{"for": MEAL_SELECT_ID}),
        Select(
            *options,
            id=MEAL_SELECT_ID,
            name="intake_event_id",
            data_skip_page_loading="true",
            hx_get="/assistant/thread",
            hx_trigger="change",
            hx_target=f"#{THREAD_BOX_ID}",
            hx_swap="innerHTML",
            hx_include="this",
            cls="bg-white border border-line px-2 py-1.5 text-sm rounded-lg focus:outline-none cursor-pointer max-w-[60%]",
        ),
        id="assistant_meal_box",
        cls="flex items-center justify-between gap-3 px-1",
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
    if turn.had_photo:
        parts.append(Span("Photo", cls="inline-block text-[11px] rounded-full bg-white/70 border border-line px-2 py-0.5 w-fit"))
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
    else:
        meta = [f"{card.grams:g} g" if card.grams is not None else ""]
        if card.carbs_g is not None:
            meta.append(f"{card.carbs_g:g} g carbs")
        if card.amount_method:
            try:
                meta.append(AMOUNT_METHOD_LABELS[AmountMethod(card.amount_method)])
            except ValueError:
                pass
    return Li(
        Span(card.name, cls="text-sm text-gray-900 min-w-0 break-words"),
        Span(" · ".join(part for part in meta if part), cls="text-[11px] text-gray-500"),
        cls="flex flex-col",
    )


def _added_card(cards: list[AddedCard]):
    return Div(
        Div(
            Span("Added to the cart", cls="web_section_label"),
            Button(
                "Review",
                type="button",
                cls="web_button px-3 py-1 text-xs",
                hx_get="/cart",
                hx_target="#main_content",
                hx_push_url="true",
            ),
            cls="flex items-center justify-between gap-2",
        ),
        Ul(*(_added_line(card) for card in cards), cls="flex flex-col gap-1.5"),
        cls="self-start w-full max-w-[85%] web_container rounded-2xl px-3 py-2 flex flex-col gap-2",
    )


def draft_form_url(card: DraftCard, conversation_id: int) -> str:
    """The create form prefilled with a draft (§9.11); saving comes back here."""
    back = f"return_to_assistant={conversation_id}"
    if card.source == AssistantDraftSource.CIQUAL.value and card.code:
        return f"/food/create/catalog/form?{urlencode({'ciqual': card.code})}&{back}"
    if card.source == AssistantDraftSource.OPEN_FOOD_FACTS.value and card.code:
        return f"/food/create/catalog/form?{urlencode({'barcode': card.code})}&{back}"
    query = urlencode({"assistant_message": card.message_id, "assistant_tool": card.tool_use_id})
    return f"/food/create/catalog/form?{query}&{back}"


_DRAFT_SOURCE_LABELS = {
    AssistantDraftSource.CIQUAL.value: "From the food composition table",
    AssistantDraftSource.OPEN_FOOD_FACTS.value: "From Open Food Facts",
    AssistantDraftSource.LABEL.value: "Read from the label",
}


def _draft_card(card: DraftCard, conversation_id: int):
    return Div(
        Div(
            Span("New food to review", cls="web_section_label"),
            P(card.name, cls="text-sm text-gray-900 break-words"),
            P(_DRAFT_SOURCE_LABELS.get(card.source, ""), cls="text-[11px] text-gray-500"),
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


def _notice(text: str):
    return P(text, cls="self-start text-xs text-amber-800 px-1")


def TurnBlock(turn: TurnView, conversation_id: int, notices: list[str] | None = None):
    """One message of the user and what the assistant did for it (§9.11)."""
    return Div(
        _user_bubble(turn),
        *(_reply_bubble(text) for text in turn.replies),
        _added_card(turn.added) if turn.added else None,
        *(_draft_card(card, conversation_id) for card in turn.drafts),
        *(_notice(text) for text in (notices or [])),
        cls="w-full flex flex-col gap-2",
    )


def AssistantThread(turns: list[TurnView], conversation_id: int | None):
    """The conversation of the chosen meal; the intro while it is empty."""
    return Div(
        _intro() if not turns else None,
        *(TurnBlock(turn, conversation_id) for turn in turns),
        ConversationIdInput(conversation_id),
        id=THREAD_ID,
        cls="w-full flex flex-col gap-3",
    )


def _thinking():
    return Div(
        Span("Thinking…", cls="text-sm text-gray-500"),
        id="assistant_thinking",
        cls="hidden [&.htmx-request]:block self-start web_container rounded-2xl rounded-bl-md px-3 py-2",
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
        Div(
            Span(id="assistant_photo_name", cls="truncate"),
            Button(
                "×",
                type="button",
                id="assistant_photo_remove",
                aria_label="Remove the photo",
                cls="shrink-0 h-5 w-5 rounded-full text-gray-500 hover:bg-line-soft cursor-pointer",
            ),
            id="assistant_photo_chip",
            hidden=True,
            cls="inline-flex items-center gap-1 rounded-full bg-control border border-line pl-2.5 pr-1 py-0.5 text-xs text-gray-800 max-w-full w-fit",
        ),
        Div(
            Label(
                _PHOTO_ICON,
                Input(type="file", id="assistant_photo", name="photo", accept="image/*", cls="sr-only"),
                aria_label="Attach a photo",
                title="Attach a photo",
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


def AssistantPage(events: list, selected_event_id: int | None, conversation_id: int | None, turns: list[TurnView]):
    return Div(
        _header(),
        AssistantMealSelect(events, selected_event_id),
        Div(AssistantThread(turns, conversation_id), id=THREAD_BOX_ID, cls="w-full"),
        _thinking(),
        # At the bottom of the screen, above the island; in the flow (sticky,
        # not fixed) so a phone keyboard scrolls it into view.
        Div(_composer(), cls="sticky bottom-28 w-full mt-auto"),
        data_hide_cart="true",
        cls="w-full max-w-2xl mx-auto px-4 pt-6 pb-28 min-h-dvh flex flex-col gap-4",
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
