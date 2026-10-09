from DayBetes_food.domain.constants import MealType


NUTRIENT_SPECS = [
    ("calories", "Cal", "kcal"),
    ("carbs", "Carbs", "g"),
    ("fats", "Fats", "g"),
    ("saturated", "Saturated", "g"),
    ("sugars", "Sugars", "g"),
    ("proteins", "Proteins", "g"),
    ("fiber", "Fiber", "g"),
]

MEAL_TYPE_LABELS = {
    "breakfast": "Breakfast",
    "brunch": "Brunch",
    "lunch": "Lunch",
    "afternoon_snack": "Afternoon snack",
    "dinner": "Dinner",
    "snack": "Snack",
    "rescue": "Rescue",
    "untyped": "No type",
}

MEAL_TYPE_ORDER = [meal_type.value for meal_type in MealType] + ["untyped"]

STATS_PAGE_CLS = """
    w-full mx-auto
    flex flex-col items-center justify-center gap-6
    md:mt-7 lg:mt-7 mt-2
    md:w-md lg:w-md w-xs
    md:mb-28 lg:mb-28 mb-24
    transition-[width,margin,padding] duration-150
"""


def to_float(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def empty_totals() -> dict:
    return {key: 0.0 for key, _, _ in NUTRIENT_SPECS}


def format_amount(value: float, unit: str) -> str:
    return f"{value:.0f}" if unit == "kcal" else f"{value:.1f}"
