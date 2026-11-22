"""The text of the guide of the data-quality fields (frontend_conventions.md §9.12):
what each value to choose means, so every meal is logged with the same criterion.

This module is the only place with the guide's text: the guide page and its
pop-ups draw it (components/guide.py) and DiaBot reads it to answer questions
about it (code_conventions.md §8.12, "Dudas sobre la guía"). The rule behind
each line is in study_conventions.md §6.3 and measurement_conventions.md; the
guide is its short version for the interface. Each topic walks its enum, so a
new value shows up on its own, as "Definition pending." until its line is
written here.
"""

from dataclasses import dataclass
from enum import Enum

from DayBetes_food.domain.constants import (
    AmountMethod,
    ConservationMethod,
    CookingMethod,
    FoodPhysicalState,
    MacrosSource,
    Ripeness,
)

# How U1 and U2 read in the interface (study_conventions.md §6.3); the guide
# names its values with them.
MACROS_SOURCE_LABELS = {
    MacrosSource.LABEL: "Package label",
    MacrosSource.OFFICIAL: "Menu or official website",
    MacrosSource.OPEN_FOOD_FACTS: "Open Food Facts",
    MacrosSource.REFERENCE_DB: "Food composition table",
    MacrosSource.INGREDIENTS: "Calculated from its ingredients",
    MacrosSource.AI_ESTIMATE: "AI estimate",
    MacrosSource.OWN_ESTIMATE: "My estimate",
}
AMOUNT_METHOD_LABELS = {
    AmountMethod.KITCHEN_SCALE: "Kitchen scale",
    AmountMethod.POCKET_SCALE: "Pocket scale",
    AmountMethod.PACKAGE: "Package weight",
    AmountMethod.USUAL_AMOUNT: "Usual amount",
    AmountMethod.HOUSEHOLD: "Household measure",
    AmountMethod.EYEBALL: "By eye",
    AmountMethod.AI_ESTIMATE: "AI estimate",
}

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
    AmountMethod.PACKAGE: "The weight printed on the pack or the unit, eaten whole: a 125 g yogurt, a 60 g can.",
    AmountMethod.USUAL_AMOUNT: (
        "An amount you always take about the same and whose weight you know from weighing it before, "
        "not weighed this time: your usual glass of milk, one medium tomato, half your usual jar."
    ),
    AmountMethod.HOUSEHOLD: "A rough household measure: a spoon, a handful, a splash, any glass.",
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
                GuideValue("%", "The part of the plate you ate."),
                GuideValue("g", "The grams you ate, out of the plate's total."),
                GuideValue(
                    "Weighed",
                    "Mark it only if you weighed the plate and what you ate. Unmarked, the part "
                    "is by eye, whether you wrote % or g.",
                ),
            ),
            note=(
                "Splits with the fridge are recorded on their own: % is by eye, grams or "
                "Weighed are weighed."
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




def guide_text(key: str) -> str | None:
    """A topic or group of the guide as plain text, for DiaBot (§8.12). None if unknown."""
    topics = guide_topics_for(key)
    if topics is None:
        return None
    blocks = []
    for topic in topics:
        lines = [f"{topic.title}: {topic.intro}"]
        lines += [f"- {value.label}: {value.definition or PENDING_DEFINITION}" for value in topic.values]
        if topic.note:
            lines.append(topic.note)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
