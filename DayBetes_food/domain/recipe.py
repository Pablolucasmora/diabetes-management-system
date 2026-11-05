"""Dataclasses and pure rules of `recipe` (code_conventions.md §3.1, §3.6, §7.11, §11.2.4).

This module imports no psycopg, routes or components. The SQL-row-to-dataclass
conversion lives in DayBetes_food/database/mappers.py.
"""

from dataclasses import dataclass
from datetime import datetime

from DayBetes_food.domain.constants import (
    ConservationMethod,
    CookingMethod,
    FoodPhysicalState,
    MealType,
    parse_enum,
)
from DayBetes_food.domain.food import normalize_food_text
from DayBetes_food.domain.nutrition import NumericRange, parse_number
from DayBetes_food.errors import ValidationError

RECIPE_NAME_MAX_LENGTH = 255  # = VARCHAR(255)
# TEXT column: the limit is a domain rule (§7.3). It is this large because the
# notes can hold the whole preparation of the dish.
RECIPE_NOTES_MAX_LENGTH = 20000
RECIPE_SERVINGS_RANGE = NumericRange(1, 100)
# What is added to a meal can be half a serving (measurement_conventions.md §4.7).
RECIPE_ADD_SERVINGS_RANGE = NumericRange(0, 100, minimum_exclusive=True)

# Rescue has its own flow and never carries insulin, so it is not a recipe type
# (frontend_conventions.md §9.6).
RECIPE_MEAL_TYPES = tuple(meal_type for meal_type in MealType if meal_type is not MealType.RESCUE)


def parse_recipe_name(raw) -> str:
    """Required name, normalized (normalize_food_text), <= 255 characters."""
    name = normalize_food_text(raw)
    if not name:
        raise ValidationError("Recipe name is required.", fields={"name": "required"})
    if len(name) > RECIPE_NAME_MAX_LENGTH:
        raise ValidationError(
            f"Recipe name must be {RECIPE_NAME_MAX_LENGTH} characters or fewer.", fields={"name": "too_long"}
        )
    return name


def parse_recipe_notes(raw) -> str | None:
    """Optional free text: strip only (line breaks are kept); '' -> None; never truncated."""
    notes = str(raw or "").strip()
    if not notes:
        return None
    if len(notes) > RECIPE_NOTES_MAX_LENGTH:
        raise ValidationError(
            f"Notes must be {RECIPE_NOTES_MAX_LENGTH} characters or fewer.", fields={"notes": "too_long"}
        )
    return notes


def parse_recipe_meal_type(raw) -> MealType | None:
    """Closed list without rescue; '' -> None; anything else -> 422 (§7.7)."""
    meal_type = parse_enum(MealType, raw, field="meal_type")
    if meal_type is MealType.RESCUE:
        raise ValidationError("A recipe cannot be a rescue.", fields={"meal_type": "invalid"})
    return meal_type


def parse_recipe_servings(raw) -> int | None:
    """Optional whole number from 1 to 100 (measurement_conventions.md §4.7)."""
    try:
        servings = parse_number(raw, "servings", RECIPE_SERVINGS_RANGE, integer=True)
    except ValidationError as error:
        raise ValidationError("Servings must be a whole number from 1 to 100.", fields=error.fields) from error
    return None if servings is None else int(servings)


def parse_recipe_add_servings(raw) -> float:
    """Required decimal greater than 0, at most 100."""
    try:
        servings = parse_number(raw, "servings", RECIPE_ADD_SERVINGS_RANGE)
    except ValidationError as error:
        raise ValidationError("Servings must be a number greater than 0 and at most 100.", fields=error.fields) from error
    if servings is None:
        raise ValidationError("Choose how many servings to add.", fields={"servings": "required"})
    return servings


def scaled_recipe_amount(amount: float, chosen_servings: float | None, recipe_servings: int | None) -> float:
    """Grams of an ingredient for the chosen servings (§4.7). The server computes it
    from the recipe, never from an amount the client sends (§7.13)."""
    if chosen_servings is None or recipe_servings is None:
        return amount
    return amount * chosen_servings / recipe_servings


def recipe_meal_type_from_event(meal_type: MealType | None) -> MealType | None:
    """Meal type of a recipe saved from a cart event: a rescue leaves it empty."""
    return None if meal_type is MealType.RESCUE else meal_type


@dataclass(frozen=True)
class RecipeRead:
    id: int
    user_id: int  # owner: recipe.users_id, NOT NULL (§3.5)
    origin_root_id: int | None
    name: str
    meal_type: MealType | None
    notes: str | None
    servings: int | None  # None = the recipe is added whole
    is_published: bool
    created_at: datetime
    updated_at: datetime
    is_favorite: bool  # SQL: in the viewer's favorites
    can_edit: bool  # SQL: owned by the viewer


@dataclass(frozen=True)
class RecipeCreate:
    """No is_published: the DB default FALSE makes it personal (§11.4.1)."""

    user_id: int
    origin_root_id: int | None
    name: str
    meal_type: MealType | None
    notes: str | None
    servings: int | None


@dataclass(frozen=True)
class RecipeUpdate:
    """FULL replacement of the editable fields (the edit form sends all of them):
    None means NULL (§3.4, §7.4). It does not contain users_id, origin_root_id or
    is_published. Its field list IS the update whitelist (§4.6, §7.11)."""

    name: str
    meal_type: MealType | None
    notes: str | None
    servings: int | None


@dataclass(frozen=True)
class RecipeRequest:
    """Recipe form already parsed and validated (§3.1, §7.11); never reaches persistence."""

    name: str
    meal_type: MealType | None
    notes: str | None
    servings: int | None
    favorite: bool | None  # None = field absent (edit form)
    tags: list[str] | None  # None = field absent


@dataclass(frozen=True)
class PortionPreparation:
    """Preparation of an ingredient for this meal; it is not written to the recipe."""

    cooking: CookingMethod | None
    conservation: ConservationMethod | None
    final_state: FoodPhysicalState | None


@dataclass(frozen=True)
class RecipeAddRequest:
    """The step before adding a recipe to a meal, already parsed (§3.1, §7.11)."""

    event_id: int | None  # None = a new meal
    plate_id: int | None  # None = new plate; only applies to a recipe with one plate
    servings: float | None  # None = field absent: the recipe has no servings
    preparations: dict[int, PortionPreparation]  # by the recipe portion's id
