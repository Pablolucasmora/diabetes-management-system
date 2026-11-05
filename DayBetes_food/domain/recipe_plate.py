"""Dataclass and limits of a recipe's plate (measurement_conventions.md §4.7).

This module imports no psycopg, routes or components.
"""

from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.food import normalize_food_text
from DayBetes_food.errors import ValidationError

RECIPE_PLATE_NAME_MAX_LENGTH = 255  # = VARCHAR(255)


def parse_recipe_plate_name(raw) -> str | None:
    """Optional name, normalized; '' -> None, which is the derived name (§4.6.3)."""
    name = normalize_food_text(raw)
    if not name:
        return None
    if len(name) > RECIPE_PLATE_NAME_MAX_LENGTH:
        raise ValidationError(
            f"The plate name must be {RECIPE_PLATE_NAME_MAX_LENGTH} characters or fewer.",
            fields={"name": "too_long"},
        )
    return name


@dataclass(frozen=True)
class RecipePlateRead:
    id: int
    recipe_id: int
    position: int
    name: str | None  # None = derived from its ingredients (§4.6.3)
    created_at: datetime
    updated_at: datetime
