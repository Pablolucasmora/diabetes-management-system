"""The guide of the data-quality fields (frontend_conventions.md §9.12): its page
and its pop-ups. The text itself is in domain/guide.py."""

from fasthtml.common import Button, Dd, Div, Dl, Dt, H1, H2, Input, Label, Li, Nav, NotStr, Ol, P, Section, Span, Ul

from DayBetes_food.components.modal import ModalLayer, close_modal_js, modal_icon_button
from DayBetes_food.components.settings.subpage import SUBPAGE_CLS, SearchField, SubpageHeader
from DayBetes_food.domain.guide import (
    GUIDE_GROUPS,
    GUIDE_TOPICS,
    PENDING_DEFINITION,
    GuideTopic,
    GuideValue,
    guide_topics_for,
)

GUIDE_MODAL_ID = "guide_modal"
GUIDE_MODAL_BODY_ID = "guide_modal_body"
GUIDE_HELP_BUTTON_CLS = """
    web_button rounded-full
    h-4 w-4 md:h-5 md:w-5
    text-[10px] md:text-xs
    p-0 leading-none shrink-0
    flex items-center justify-center
    shadow-none cursor-pointer
"""


def GuideHelpButton(topic: str, label: str):
    """The `?` next to a field: opens the guide pop-up on that topic without
    leaving the page. It sends no field of its form and does not navigate."""
    return Button(
        "?",
        type="button",
        title=f"What each {label} option means",
        aria_label=f"What each {label} option means",
        hx_get=f"/settings/guide/{topic}",
        hx_target=f"#{GUIDE_MODAL_BODY_ID}",
        hx_swap="innerHTML",
        hx_params="none",
        hx_push_url="false",
        # Inside a <label> or a clickable row, the click must not reach it.
        onclick="event.stopPropagation();",
        cls=GUIDE_HELP_BUTTON_CLS,
        **{"hx-on::after-request": f"if(event.detail.successful){{dbOpenModal('{GUIDE_MODAL_ID}');}}"},
    )


def GuideModal():
    """The guide pop-up, once per page, outside #main_content (render_page)."""
    return ModalLayer(
        Div(id=GUIDE_MODAL_BODY_ID, cls="flex flex-col gap-4"),
        modal_id=GUIDE_MODAL_ID,
        card_cls="gap-4 max-h-[85vh] overflow-y-auto",
    )


def _pending_badge():
    return Span("Pending", cls="text-[10px] font-semibold uppercase tracking-wide text-warning bg-control border border-line rounded-full px-2 py-0.5")


def _topic_values(topic: GuideTopic):
    return Ul(
        *[
            Li(
                Span(value.label, cls="text-sm font-semibold text-gray-900"),
                Span(
                    value.definition or PENDING_DEFINITION,
                    cls="text-sm text-gray-700" if value.definition else "text-sm text-gray-400 italic",
                ),
                cls="flex flex-col",
            )
            for value in topic.values
        ],
        cls="flex flex-col gap-2",
    )


def _topic_block(topic: GuideTopic, heading):
    return Div(
        Div(heading, _pending_badge() if topic.pending else None, cls="flex items-center gap-2"),
        P(topic.intro, cls="text-sm text-gray-600"),
        P(topic.note, cls="text-xs text-gray-500") if topic.note else None,
        _topic_values(topic),
        cls="flex flex-col gap-2",
    )


def GuideModalBody(topics: list[GuideTopic]):
    """What the pop-up shows: the topics of one field or of a group."""
    blocks = [
        _topic_block(topic, (H2 if len(topics) > 1 else P)(topic.title, cls="text-base font-semibold" if len(topics) > 1 else "text-lg font-semibold"))
        for topic in topics
    ]
    return (
        Div(
            P("Guide", cls="web_section_label"),
            modal_icon_button("×", aria_label="Close", onclick=close_modal_js(GUIDE_MODAL_ID)),
            cls="flex items-center justify-between",
        ),
        *[
            Div(block, cls="pt-3 border-t border-line-soft" if index else "")
            for index, block in enumerate(blocks)
        ],
    )


def _section_id(key: str) -> str:
    return f"guide_{key}"


def _value_id(topic_key: str, index: int) -> str:
    return f"guide_{topic_key}_{index}"


GUIDE_CONTENTS_ID = "guide_contents"
GUIDE_SEARCH_ID = "guide_search"

def _scroll_js(element_id: str) -> str:
    """Scroll inside the page without a hash: the URL and the history stay (§9.12)."""
    return f"document.getElementById('{element_id}').scrollIntoView({{behavior:'smooth',block:'start'}});"


def _contents(topics: list[GuideTopic]):
    """The index: one row per topic, with its number and how many values it has.
    While searching, static/js/guide.js lists under each topic the values that
    match, and hides the topics without any."""
    return Nav(
        P("Contents", cls="web_section_label"),
        Ol(
            *[
                Li(
                    Button(
                        Span(f"{number:02d}", cls="font-mono text-xs text-muted w-6 shrink-0"),
                        Span(topic.title, cls="flex-1 text-left"),
                        Span(str(len(topic.values)), data_guide_count="", cls="text-xs text-muted tabular-nums"),
                        type="button",
                        onclick=_scroll_js(_section_id(topic.key)),
                        cls="w-full flex items-baseline gap-3 py-2 text-sm text-stone-900 cursor-pointer hover:text-ink",
                    ),
                    # Filled by guide.js with the values that match the search.
                    Ol(data_guide_matches="", cls="hidden pl-9 pb-2 flex-col gap-1"),
                    data_guide_entry=topic.key,
                    cls="border-t border-line-soft first:border-t-0",
                )
                for number, topic in enumerate(topics, start=1)
            ],
            cls="flex flex-col",
        ),
        id=GUIDE_CONTENTS_ID,
        aria_label="Contents",
        cls="w-full flex flex-col gap-1 scroll-mt-28",
    )


def _section(topic: GuideTopic, number: int):
    """One topic: number, title, what is chosen, and each value with its meaning."""
    return Section(
        Div(
            Span(f"{number:02d}", cls="font-mono text-xs text-muted"),
            H2(topic.title, cls="text-lg font-semibold text-stone-900"),
            _pending_badge() if topic.pending else None,
            cls="flex items-baseline gap-3",
        ),
        P(topic.intro, cls="text-sm text-gray-600"),
        P(topic.note, cls="text-xs text-gray-500") if topic.note else None,
        Dl(
            *[
                Div(
                    Dt(value.label, data_guide_label="", cls="text-sm font-medium text-stone-900"),
                    Dd(
                        value.definition or PENDING_DEFINITION,
                        data_guide_text="",
                        cls="text-sm text-gray-700" if value.definition else "text-sm text-gray-400 italic",
                    ),
                    id=_value_id(topic.key, index),
                    data_guide_value="",
                    cls="grid gap-0.5 md:grid-cols-[9rem_1fr] md:gap-4 py-2.5 border-t border-line-soft scroll-mt-28",
                )
                for index, value in enumerate(topic.values)
            ],
            cls="flex flex-col",
        ),
        Button(
            "↑ Contents",
            type="button",
            data_guide_to_contents="",
            onclick=_scroll_js(GUIDE_CONTENTS_ID),
            cls="self-start text-xs text-muted hover:text-ink cursor-pointer py-1",
        ),
        id=_section_id(topic.key),
        data_guide_topic=topic.key,
        data_guide_title=topic.title,
        cls="w-full flex flex-col gap-2 pt-6 scroll-mt-28",
    )


def GuidePage():
    """Settings > Guide (frontend_conventions.md §9.12): a search box, the contents
    and every topic below. Searching filters the topics and their values in the
    page (static/js/guide.js); with a single result the contents hide and the
    result keeps the title of its topic."""
    topics = list(GUIDE_TOPICS.values())
    return Div(
        SubpageHeader(
            "Guide",
            SearchField(GUIDE_SEARCH_ID, "Search a field or an option"),
            status_id="guide_status",
        ),
        P(
            "What each option means, so every meal is logged the same way. "
            "The ? next to a field opens the same text.",
            cls="w-full text-sm text-gray-600 px-1",
        ),
        Div(_contents(topics), cls="web_container w-full p-4"),
        *[Div(_section(topic, number), cls="web_container w-full px-4 pb-2") for number, topic in enumerate(topics, start=1)],
        P("Nothing matches. Try another word.", id="guide_empty", hidden=True, cls="web_container w-full text-sm text-gray-500 p-4"),
        id="guide_page",
        cls=SUBPAGE_CLS,
    )
