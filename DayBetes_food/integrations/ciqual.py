"""Builds the create form's prefill from a Ciqual food (measurement_conventions.md
§12.3), through the same checks as an Open Food Facts product."""

from dataclasses import replace

from DayBetes_food.domain.ciqual_food import CiqualFoodRead
from DayBetes_food.domain.food import FoodPrefill
from DayBetes_food.integrations.open_food_facts import prefill_from_record


def prefill_from_ciqual_food(food: CiqualFoodRead) -> FoodPrefill:
    nutriments = {}
    for field, value, unit in (
        ("energy-kcal", food.calories_100g, "kcal"),
        ("carbohydrates", food.carbs_100g, "g"),
        ("sugars", food.sugars_100g, "g"),
        ("fat", food.fats_100g, "g"),
        ("saturated-fat", food.saturated_100g, "g"),
        ("proteins", food.proteins_100g, "g"),
        ("fiber", food.fiber_100g, "g"),
        ("alcohol", food.alcohol, "g"),
    ):
        if value is not None:
            nutriments[f"{field}_100g"] = value
            nutriments[f"{field}_unit"] = unit
    prefill = prefill_from_record(
        None, {"product_name": food.name_es, "categories": food.category_hint, "nutriments": nutriments}
    )
    return replace(prefill, subtype=food.subtype or prefill.subtype)


def reliability_note(food: CiqualFoodRead) -> str:
    """What the form shows so the user can judge the values."""
    note = (
        f"Ciqual reliability (A best, D worst): carbs {food.carbs_confidence or '-'}, "
        f"fat {food.fats_confidence or '-'}, protein {food.proteins_confidence or '-'}. "
        "Values are per 100 g of edible part."
    )
    if food.value_notes:
        note += f" Traces are filled as 0 and \"< x\" as half of x: {food.value_notes}."
    return note
