from datetime import datetime
from fasthtml.common import Option


MEAL_TYPES = [
    "breakfast",
    "brunch",
    "lunch",
    "afternoon_snack",
    "dinner",
    "snack",
    "rescue",
]

MACRO_KEYS = [
    ("carbs", "Carbs", "carbs_uncertainty"),
    ("sugars", "Sugars", "sugars_uncertainty"),
    ("fats", "Fats", "fats_uncertainty"),
    ("saturated", "Saturated", "saturated_uncertainty"),
    ("proteins", "Proteins", "proteins_uncertainty"),
    ("fiber", "Fiber", "fiber_uncertainty"),
]

CHECKBOX_CLS = """
    peer h-5 w-5 cursor-pointer transition-all appearance-none rounded
    shadow hover:shadow-md border border-slate-300
    checked:bg-slate-800 checked:border-slate-800
"""


def macro_color(uncertainty: float) -> str:
    value = max(0.0, min(1.0, float(uncertainty or 0.0)))
    red = int(34 + (239 - 34) * value)
    green = int(197 + (68 - 197) * value)
    blue = int(94 + (68 - 94) * value)
    return f"rgb({red}, {green}, {blue})"


def parse_source_macro(portion, macro_key: str):
    catalog_value = portion.get(f"catalog_{macro_key}_100g")
    manual_value = portion.get(f"manual_{macro_key}_100g")
    return catalog_value if catalog_value is not None else manual_value


def portion_name(portion):
    return portion.get("catalog_name") or portion.get("manual_intake_name") or f"Ingredient #{portion['id']}"


def unit_amount(portion) -> float:
    if portion.get("catalog_id"):
        return float(portion.get("catalog_default_portion") or 100.0)
    return float(portion.get("manual_amount_g") or portion.get("amount_g") or 100.0)


def group_portions(portions):
    grouped = {}
    order = []
    for portion in portions:
        if portion.get("catalog_id"):
            origin = "catalog"
            origin_id = int(portion["catalog_id"])
        else:
            origin = "manual_intake"
            origin_id = int(portion["manual_intake_id"])
        key = (origin, origin_id)
        if key not in grouped:
            grouped[key] = {
                "origin": origin,
                "origin_id": origin_id,
                "portion_ids": [],
                "total_amount_g": 0.0,
                "sample": portion,
            }
            order.append(key)
        grouped[key]["portion_ids"].append(int(portion["id"]))
        grouped[key]["total_amount_g"] += float(portion.get("amount_g") or 0.0)
    return [grouped[k] for k in order]


def time_options(selected_time: datetime):
    options = []
    for hour in range(24):
        for minute in (0, 15, 30, 45):
            hhmm = f"{hour:02d}:{minute:02d}"
            selected = selected_time.strftime("%H:%M") == hhmm
            options.append(Option(hhmm, value=hhmm, selected=selected))
    return options


def datetime_local_value(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M")


def display_unit(portion) -> str:
    catalog_category = (portion.get("catalog_category") or "").strip().lower()
    manual_subtype = (portion.get("manual_subtype") or "").strip().lower()
    if catalog_category == "beverages":
        return "ml"
    liquid_hints = ("drink", "beverage", "juice", "soda", "smoothie", "milk", "coffee", "tea", "bebida")
    if any(token in manual_subtype for token in liquid_hints):
        return "ml"
    return "g"
