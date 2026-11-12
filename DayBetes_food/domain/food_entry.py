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
