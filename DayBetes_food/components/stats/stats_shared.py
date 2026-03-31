from DayBetes_food.components.cart.cart_shared import MEAL_TYPES


NUTRIENT_SPECS = [
    ("calories", "Cal", "kcal"),
    ("carbs", "HC", "g"),
    ("fats", "Grasas", "g"),
    ("saturated", "Saturadas", "g"),
    ("sugars", "Azucares", "g"),
    ("proteins", "Proteinas", "g"),
    ("fiber", "Fibra", "g"),
]

MEAL_TYPE_LABELS = {
    "breakfast": "Desayuno",
    "brunch": "Almuerzo",
    "lunch": "Comida",
    "afternoon_snack": "Merienda",
    "dinner": "Cena",
    "snack": "Snack",
    "rescue": "Rescate",
    "sin_tipo": "Sin tipo",
}

MEAL_TYPE_ORDER = [*MEAL_TYPES, "sin_tipo"]

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
