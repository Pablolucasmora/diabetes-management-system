"""Page of the assistant for logging meals (frontend_conventions.md §9.11).

Pure components (code_conventions.md §1.4): they receive data already read.
The `/` suggestions and the composer behavior live in static/js/assistant.js.
"""

from urllib.parse import urlencode

from fasthtml.common import *

from DayBetes_food.components.food.food_shared import AMOUNT_METHOD_LABELS, MACROS_SOURCE_LABELS
from DayBetes_food.components.food.food_list import meal_option_label
from DayBetes_food.components.food.rescue import carbs_meta
from DayBetes_food.components.modal import MODAL_NAME_CLS
from DayBetes_food.components.navigation import back_js
from DayBetes_food.domain.assistant import (
    MANUAL_INTAKE_DRAFT_SOURCE,
    RECIPE_DRAFT_SOURCE,
    ASSISTANT_PHOTOS_MAX,
    ASSISTANT_TEXT_MAX_LENGTH,
    NO_MEAL_CHOICE,
    AddedCard,
    DraftCard,
    ProvisionalCard,
    RepeatCard,
    RepeatSaveAs,
    TurnView,
)
from DayBetes_food.domain.constants import AmountMethod, AssistantDraftSource, FoodEntryType, MacrosSource
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
                    # Lands on the chosen meal's card (static/js/assistant.js, frontend §5).
                    **{"hx-on:click": "dbOpenCartFromAssistant();"},
                ),
                cls="flex items-center gap-3",
            ),
            cls="flex items-center justify-between",
        ),
        H1("What did you eat?", cls="text-2xl font-bold text-gray-900"),
        cls="w-full px-1 flex flex-col gap-1",
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


def _intro():
    return Div(
        P("Tell me what you ate, with amounts if you know them.", cls="text-sm text-gray-800"),
        P(
            "Type / to pin one of your foods, dishes or recipes, so I use exactly that one. "
            "You can also attach a photo of the dish or of a nutrition label, or describe a "
            "recipe to save it.",
            cls="text-xs text-gray-500",
        ),
        _how_to_write(),
        cls="web_container w-full px-4 py-3 flex flex-col gap-1",
    )


def AssistantMealSelect(events: list, selected_id: int | None, *, without_meal: bool = False, oob: bool = False):
    """Which meal the conversation writes to (§9.11): the planned meals, and
    `New meal`, whose first add creates it, and `No meal`, a chat for new foods and
    recipes only. Changing it opens that meal's conversation."""
    options = [
        Option(meal_option_label(event), value=str(event.id), selected=(event.id == selected_id))
        for event in events
    ]
    options.append(Option("New meal", value="", selected=(selected_id is None and not without_meal)))
    options.append(Option("No meal", value=NO_MEAL_CHOICE, selected=without_meal))
    return Div(
        Label("Add to", cls="web_section_label shrink-0", **{"for": MEAL_SELECT_ID}),
        # `No meal` only (§9.11): its last chat reopens, this starts an empty one.
        # static/js/assistant.js shows it while `No meal` is chosen.
        Button(
            "New chat",
            type="button",
            id="assistant_new_chat",
            data_skip_page_loading="true",
            hx_get=f"/assistant/thread?intake_event_id={NO_MEAL_CHOICE}&new_chat=1",
            hx_target=f"#{THREAD_BOX_ID}",
            hx_swap="innerHTML",
            cls="web_button px-2.5 py-1 text-xs ml-auto" + ("" if without_meal else " hidden"),
        ),
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


def TurnBlock(
    turn: TurnView, conversation_id: int, notices: list[str] | None = None, pending: frozenset = frozenset()
):
    """One message of the user and what the assistant did for it (§9.11).
    `pending`: the (entry_type, id) of the provisional entries still to review."""
    bot = [
        *(_reply_bubble(text) for text in turn.replies),
        _added_card(turn.added) if turn.added else None,
        *(_provisional_card(card, conversation_id, pending) for card in turn.provisional),
        *(_repeat_card(card, conversation_id) for card in turn.repeats),
        _changed_card(turn.changed) if turn.changed else None,
        *(_draft_card(card, conversation_id) for card in turn.drafts),
        *(_notice(text) for text in (notices or [])),
    ]
    return Div(
        _user_bubble(turn),
        _bot_row(*bot) if any(bot) else None,
        # Scrolled to below the fixed top bar, not under it.
        cls="w-full flex flex-col gap-2 scroll-mt-48",
    )


def AssistantThread(turns: list[TurnView], conversation_id: int | None, pending: frozenset = frozenset()):
    """The conversation of the chosen meal; the intro while it is empty."""
    return Div(
        _intro() if not turns else None,
        *(TurnBlock(turn, conversation_id, pending=pending) for turn in turns),
        ConversationIdInput(conversation_id),
        id=THREAD_ID,
        cls="w-full flex flex-col gap-3",
    )


def _thinking():
    # On a failed send assistant.js keeps it shown with `db_failed` (§9.11).
    bubble = Div(
        Span("Thinking", data_thinking_only="true", cls="text-sm text-gray-500"),
        Span("Couldn't answer", data_failed_only="true", cls="text-sm text-gray-500"),
        # Three dots that rise in turn while the answer comes (§9.11, static/css/input.css).
        Span(
            Span(cls="db_typing_dot"),
            Span(cls="db_typing_dot"),
            Span(cls="db_typing_dot"),
            aria_hidden="true",
            data_thinking_only="true",
            cls="flex items-end gap-1 pb-1 text-gray-500",
        ),
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


def AssistantPage(
    events: list,
    selected_event_id: int | None,
    conversation_id: int | None,
    turns: list[TurnView],
    *,
    without_meal: bool = False,
    pending: frozenset = frozenset(),
    plus_buttons: list | None = None,
):
    return Div(
        # Fixed at the top, like Food's bar (§9.11): Back, the cart and Add to stay
        # at hand however long the conversation is.
        Div(
            _header(),
            AssistantMealSelect(events, selected_event_id, without_meal=without_meal),
            cls="sticky top-0 z-[600] w-full flex flex-col gap-3 px-5 pt-6 pb-4 web_glass_strong rounded-b-3xl",
        ),
        Div(AssistantThread(turns, conversation_id, pending), id=THREAD_BOX_ID, cls="w-full"),
        _thinking(),
        # At the bottom of the screen, flush on the island's highest point
        # (--island-reach, measured by island_indicator.js); on desktop 12px
        # above it. In the flow (sticky, not fixed) so a phone
        # keyboard scrolls it into view.
        Div(
            PlusRow(plus_buttons or [], conversation_id),
            _composer(),
            cls="sticky bottom-[var(--island-reach,119px)] md:bottom-[calc(var(--island-reach,147px)+12px)] w-full mt-auto flex flex-col gap-2",
        ),
        data_hide_cart="true",
        # Asked for again on coming back, with the conversation of its URL
        # (frontend_conventions.md §5): a saved copy loses the `Add to` choice.
        hx_history="false",
        cls="w-full max-w-2xl mx-auto px-4 pb-28 min-h-dvh flex flex-col gap-4",
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
