"""Read dataclasses of an entry of the Food list (a food, a dish or a recipe)
that do not belong to a single entity.

This module imports no psycopg, routes or components (code_conventions.md
§3.6).
"""

from dataclasses import dataclass

from DayBetes_food.domain.constants import FoodEntryType

# The `/` suggestions of the assistant (frontend_conventions.md §9.11): how
# many rows a search returns, and how far back "most eaten" looks.
MENTION_SUGGESTIONS_MAX = 20
MENTION_USAGE_DAYS = 60


@dataclass(frozen=True)
class FoodEntrySummary:
    """What the actions pop-up of a Food row shows and allows
    (frontend_conventions.md §9.3.1): its name, the line under it (brand,
    origin or "Recipe"), whether the viewer can edit it and its serving in
    grams, which saving it to the fridge starts from (None: no serving)."""
    name: str
    subtitle: str
    can_edit: bool
    default_portion: float | None = None


@dataclass(frozen=True)
class MentionSuggestion:
    """A row of the `/` suggestions of the assistant (frontend_conventions.md
    §9.11): an entry of the Food list the viewer can see. `subtitle` is the
    brand of a food or the origin of a dish ("" if none, always "" for a
    recipe). `serving_g` and `carbs_100g` are None for a recipe, whose macros
    come from its ingredients, and `serving_g` is None for a food without
    serving."""
    entry_type: FoodEntryType
    entry_id: int
    name: str
    subtitle: str
    serving_g: float | None
    carbs_100g: float | None
    is_favorite: bool


@dataclass(frozen=True)
class ReviewEntry:
    """A provisional food or dish still to review (code_conventions.md §8.12,
    "Alimentos provisionales"): what the To review list shows of it."""

    entry_type: FoodEntryType
    entry_id: int
    name: str
    subtitle: str  # brand of a food, origin of a dish; "" if none
    carbs_100g: float | None
    macros_source: str | None  # MacrosSource value
    is_favorite: bool = False


# Where saving the edit form of a provisional food goes back to (frontend §9.3,
# §9.11): the To review list, or the conversation whose card opened it.
EDIT_RETURN_REVIEW = "review"
EDIT_RETURN_ASSISTANT_PREFIX = "assistant:"


def parse_edit_return(raw: str | None) -> str | None:
    """A known return target, or None: anything else is ignored, never followed."""
    value = (raw or "").strip()
    if value == EDIT_RETURN_REVIEW:
        return value
    if value.startswith(EDIT_RETURN_ASSISTANT_PREFIX):
        conversation = value[len(EDIT_RETURN_ASSISTANT_PREFIX):]
        if conversation.isdigit() and int(conversation) > 0:
            return f"{EDIT_RETURN_ASSISTANT_PREFIX}{int(conversation)}"
    return None


def edit_return_path(target: str | None) -> str | None:
    if target == EDIT_RETURN_REVIEW:
        return "/food?filter=review"
    if target and target.startswith(EDIT_RETURN_ASSISTANT_PREFIX):
        return f"/assistant?conversation_id={target[len(EDIT_RETURN_ASSISTANT_PREFIX):]}"
    return None
