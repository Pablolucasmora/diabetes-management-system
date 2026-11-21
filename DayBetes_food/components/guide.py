"""The guide of the data-quality fields (frontend_conventions.md §9.12): what
each value to choose means, so every meal is logged with the same criterion.

This module is the only place with the guide's text. The rule behind each line
is in study_conventions.md §6.3 and measurement_conventions.md; the guide is
its short version for the interface. Each topic walks its enum, so a new value
shows up on its own, as "Definition pending." until its line is written here.
"""

from dataclasses import dataclass
from enum import Enum

from fasthtml.common import Button, Dd, Div, Dl, Dt, H1, H2, Input, Label, Li, Nav, NotStr, Ol, P, Section, Span, Ul

from DayBetes_food.components.food.food_shared import AMOUNT_METHOD_LABELS, MACROS_SOURCE_LABELS
from DayBetes_food.components.modal import ModalLayer, close_modal_js, modal_icon_button
from DayBetes_food.components.settings.subpage import SUBPAGE_CLS, SearchField, SubpageHeader
from DayBetes_food.domain.constants import (
    AmountMethod,
    ConservationMethod,
    CookingMethod,
    FoodPhysicalState,
    MacrosSource,
    Ripeness,
)

GUIDE_MODAL_ID = "guide_modal"
GUIDE_MODAL_BODY_ID = "guide_modal_body"
PENDING_DEFINITION = "Definition pending."


@dataclass(frozen=True)
class GuideValue:
    label: str
    definition: str | None


@dataclass(frozen=True)
class GuideTopic:
    key: str
    title: str
    intro: str
    values: tuple[GuideValue, ...]
    # The definitions are not agreed yet (study_conventions.md §6.3).
    pending: bool = False
    note: str | None = None


def _enum_values(enum_cls: type[Enum], definitions: dict, labels: dict | None = None, empty: str | None = None):
    """One line per member of the enum, in its order, and the empty option last."""
    values = [
        GuideValue((labels or {}).get(member, member.value), definitions.get(member)) for member in enum_cls
    ]
    if empty:
        values.append(GuideValue("Not given" if labels else "Not set", empty))
    return tuple(values)


# U2 (study_conventions.md §6.3).
_AMOUNT_METHOD = {
    AmountMethod.KITCHEN_SCALE: "Weighed on the kitchen scale.",
    AmountMethod.POCKET_SCALE: "Weighed on a small portable scale.",
    AmountMethod.PACKAGE: "The weight printed on the pack or the unit: a 125 g yogurt, a 60 g can.",
    AmountMethod.HOUSEHOLD: "A spoon, a glass, a handful, or a unit with no printed weight.",
    AmountMethod.EYEBALL: "Your own guess, without a scale.",
    AmountMethod.AI_ESTIMATE: "The assistant estimated it, from a photo or a description.",
}

# U1 (study_conventions.md §6.3).
_MACROS_SOURCE = {
    MacrosSource.LABEL: "The nutrition table on the pack. Still this one if the assistant read it from a photo.",
    MacrosSource.OFFICIAL: "Published by whoever makes or serves it: its menu or website.",
    MacrosSource.OPEN_FOOD_FACTS: "Labels uploaded by other people, not checked.",
    MacrosSource.REFERENCE_DB: "A food composition table: Ciqual, BEDCA, USDA.",
    MacrosSource.INGREDIENTS: "Added up from its weighed ingredients.",
    MacrosSource.AI_ESTIMATE: "The assistant estimated them.",
    MacrosSource.OWN_ESTIMATE: "Your own estimate.",
}

# study_conventions.md §6.3, fruit ripeness.
_RIPENESS = {
    Ripeness.UNRIPE: "Green or not quite ripe.",
    Ripeness.RIPE: "Just right.",
    Ripeness.OVERRIPE: "Very ripe: spotty or soft.",
}

_PREPARATION_PENDING_NOTE = "The definitions of these values are still being written. Until then, choose the closest one."

GUIDE_TOPICS: dict[str, GuideTopic] = {
    topic.key: topic
    for topic in (
        GuideTopic(
            key="amount_method",
            title="Amount from",
            intro="How you got the amount of this food this time. A food's default is only where it starts.",
            values=_enum_values(
                AmountMethod,
                _AMOUNT_METHOD,
                AMOUNT_METHOD_LABELS,
                empty="You don't know or didn't record it. Not the same as by eye.",
            ),
        ),
        GuideTopic(
            key="macros_source",
            title="Macros from",
            intro="Where the food's macros come from. Who typed them in doesn't change it.",
            values=_enum_values(
                MacrosSource,
                _MACROS_SOURCE,
                MACROS_SOURCE_LABELS,
                empty="Unknown. Not the same as estimated.",
            ),
        ),
        GuideTopic(
            key="cooking",
            title="Cooking",
            intro="How the food was cooked.",
            values=_enum_values(CookingMethod, {}, empty="Not recorded."),
            pending=True,
            note=_PREPARATION_PENDING_NOTE,
        ),
        GuideTopic(
            key="final_state",
            title="Final state",
            intro="The texture of the food as you ate it. A food's initial state uses the same values, before preparing it.",
            values=_enum_values(FoodPhysicalState, {}, empty="Not recorded."),
            pending=True,
            note=_PREPARATION_PENDING_NOTE,
        ),
        GuideTopic(
            key="conservation",
            title="Conservation",
            intro="Whether it was freshly made or kept before eating it.",
            values=_enum_values(ConservationMethod, {}, empty="Not recorded."),
            pending=True,
            note=_PREPARATION_PENDING_NOTE,
        ),
        GuideTopic(
            key="ripeness",
            title="Ripeness",
            intro="Fruits only: how ripe it looked when you ate it.",
            values=_enum_values(Ripeness, _RIPENESS, empty="Not recorded. Not the same as ripe."),
        ),
        GuideTopic(
            key="cooked_weight",
            title="Weighed cooked",
            intro="Only for foods with a cooking factor.",
            values=(
                GuideValue("On", "The grams are the cooked weight. The macros are worked out from the raw weight."),
                GuideValue("Off", "The grams are the weight before cooking, as the food comes."),
            ),
        ),
        GuideTopic(
            key="eaten",
            title="Eaten",
            intro="How much of each plate you ate, when you confirm the meal.",
            values=(
                GuideValue("Empty", "You ate all of it."),
                GuideValue("%", "The part of the plate you ate. Usually a guess by eye."),
                GuideValue("g", "The grams you ate, out of the plate's total."),
            ),
        ),
    )
}

# A pop-up can show several topics, as the fields sit together (the preparation).
GUIDE_GROUPS: dict[str, tuple[str, ...]] = {
    "preparation": ("cooking", "final_state", "conservation", "ripeness"),
    # A recipe has no ripeness (study_conventions.md §6.3), and weighs cooked on its rows.
    "recipe_preparation": ("cooking", "final_state", "conservation", "cooked_weight"),
}


def guide_topics_for(key: str) -> list[GuideTopic] | None:
    """The topics a help button opens: one, or a group. None if `key` is unknown."""
    if key in GUIDE_TOPICS:
        return [GUIDE_TOPICS[key]]
    if key in GUIDE_GROUPS:
        return [GUIDE_TOPICS[topic] for topic in GUIDE_GROUPS[key]]
    return None


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
