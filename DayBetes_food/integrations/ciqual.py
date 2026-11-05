"""Builds the create form's prefill from a Ciqual food (measurement_conventions.md
§12.3), through the same checks as an Open Food Facts product."""

from dataclasses import replace

from DayBetes_food.domain.ciqual_food import CiqualFoodRead
from DayBetes_food.domain.constants import FoodCategory
from DayBetes_food.domain.food import FoodPrefill
from DayBetes_food.integrations.open_food_facts import initial_state_for, prefill_from_record

# Ciqual subgroup -> category. A closed list, reviewed by hand; a subgroup left
# out, such as "dishes", mixes categories and leaves the field empty (§12.3).
_CATEGORY_BY_SUBGROUP = {
    "alcoholic beverages": FoodCategory.BEVERAGES,
    "non-alcoholic beverages": FoodCategory.BEVERAGES,
    "water": FoodCategory.BEVERAGES,
    "breads and similar": FoodCategory.CEREALS,
    "breakfast cereals": FoodCategory.CEREALS,
    "flours": FoodCategory.CEREALS,
    "pasta, rice and grains": FoodCategory.CEREALS,
    "pastry dough": FoodCategory.CEREALS,
    "butters": FoodCategory.OILS_AND_FATS,
    "margarines": FoodCategory.OILS_AND_FATS,
    "fish oils": FoodCategory.OILS_AND_FATS,
    "vegetable oils": FoodCategory.OILS_AND_FATS,
    "other fats": FoodCategory.OILS_AND_FATS,
    "cheese and similar": FoodCategory.DAIRY,
    "cream and similar": FoodCategory.DAIRY,
    "dairy products": FoodCategory.DAIRY,
    "milk": FoodCategory.DAIRY,
    "cakes and pastry": FoodCategory.SWEETS,
    "cereal bars": FoodCategory.SWEETS,
    "chocolate and chocolate products": FoodCategory.SWEETS,
    "frozen desserts": FoodCategory.SWEETS,
    "ice cream": FoodCategory.SWEETS,
    "jam": FoodCategory.SWEETS,
    "non-chocolate confectionery": FoodCategory.SWEETS,
    "sorbet": FoodCategory.SWEETS,
    "sugars and honey": FoodCategory.SWEETS,
    "sweet biscuits": FoodCategory.SWEETS,
    "viennese pastries": FoodCategory.SWEETS,
    "condiments": FoodCategory.CONDIMENTS,
    "herbs": FoodCategory.CONDIMENTS,
    "salts": FoodCategory.CONDIMENTS,
    "spices": FoodCategory.CONDIMENTS,
    "sauces": FoodCategory.SAUCES,
    "cooked meat": FoodCategory.MEAT,
    "raw meat": FoodCategory.MEAT,
    "other meat products": FoodCategory.MEAT,
    "delicatessen meat and similar": FoodCategory.PROCESSED_MEAT,
    "eggs": FoodCategory.EGGS,
    "fish, cooked": FoodCategory.FISH,
    "fish, raw": FoodCategory.FISH,
    "fish products": FoodCategory.FISH,
    "seafood, cooked": FoodCategory.FISH,
    "seafood, raw": FoodCategory.FISH,
    "fruits": FoodCategory.FRUITS,
    "legumes": FoodCategory.LEGUMES,
    "nuts and seeds": FoodCategory.NUTS,
    "potatoes and other tubers": FoodCategory.TUBERS,
    "seaweed": FoodCategory.VEGETABLES,
    "vegetables": FoodCategory.VEGETABLES,
}


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
    category = _CATEGORY_BY_SUBGROUP.get((food.category_hint or "").lower())
    return replace(
        prefill_from_record(None, {"product_name": food.name_es, "nutriments": nutriments}),
        category=category,
        initial_state=initial_state_for(category),
        subtype=food.subtype,
    )


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
