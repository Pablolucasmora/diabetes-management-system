"""Page of the assistant for logging meals (frontend_conventions.md §9.11).

Pure components (code_conventions.md §1.4): they receive data already read.
The `/` suggestions and the composer behavior live in static/js/assistant.js.
"""

from fasthtml.common import *

from DayBetes_food.components.food.rescue import carbs_meta
from DayBetes_food.components.modal import MODAL_NAME_CLS
from DayBetes_food.components.navigation import back_js
from DayBetes_food.domain.constants import FoodEntryType
from DayBetes_food.domain.food_entry import MentionSuggestion

MENTIONS_LIST_ID = "assistant_mentions"

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
            "Type / to pin one of your foods, dishes or recipes, so I use exactly that one.",
            cls="text-xs text-gray-500",
        ),
        cls="web_container w-full px-4 py-3 flex flex-col gap-1",
    )


def _composer():
    return Div(
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
            Label("Message", cls="sr-only", **{"for": "assistant_input"}),
            Textarea(
                id="assistant_input",
                name="message",
                rows="1",
                placeholder="What did you eat? / for your foods",
                autocomplete="off",
                cls="""
                    web_input flex-1 min-w-0 resize-none
                    rounded-xl border border-line px-3 py-2 text-sm
                    max-h-40 overflow-y-auto
                """,
                **{"aria-autocomplete": "list", "aria-controls": MENTIONS_LIST_ID},
            ),
            # Sending arrives with the assistant service (code_conventions.md §8.12).
            Button(
                _SEND_ICON,
                type="button",
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
        id="assistant_composer",
        cls="""
            relative w-full web_glass_strong rounded-2xl p-2
            flex flex-col gap-2
        """,
    )


def AssistantPage():
    return Div(
        _header(),
        Div(_intro(), id="assistant_messages", cls="w-full flex flex-col gap-3"),
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
