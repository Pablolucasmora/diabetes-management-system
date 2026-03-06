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


def _clamp_01(value) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def macro_color(uncertainty: float, amount_confidence: float, quality_confidence: float) -> str:
    # Blend 3 reliability signals into a single risk score.
    # Higher score -> less trustworthy -> redder color.
    risk_uncertainty = _clamp_01(uncertainty)
    risk_amount = 1.0 - _clamp_01(amount_confidence)
    risk_quality = 1.0 - _clamp_01(quality_confidence)
    value = (risk_uncertainty + risk_amount + risk_quality) / 3.0

    red = int(34 + (239 - 34) * value)
    green = int(197 + (68 - 197) * value)
    blue = int(94 + (68 - 94) * value)
    return f"rgb({red}, {green}, {blue})"


def macro_text_color(uncertainty: float, amount_confidence: float, quality_confidence: float) -> str:
    risk_uncertainty = _clamp_01(uncertainty)
    risk_amount = 1.0 - _clamp_01(amount_confidence)
    risk_quality = 1.0 - _clamp_01(quality_confidence)
    value = (risk_uncertainty + risk_amount + risk_quality) / 3.0

    red = int(34 + (239 - 34) * value)
    green = int(197 + (68 - 197) * value)
    blue = int(94 + (68 - 94) * value)

    def _to_linear(channel: int) -> float:
        c = channel / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def _luminance(r: int, g: int, b: int) -> float:
        return 0.2126 * _to_linear(r) + 0.7152 * _to_linear(g) + 0.0722 * _to_linear(b)

    bg_luminance = _luminance(red, green, blue)
    white_contrast = (1.0 + 0.05) / (bg_luminance + 0.05)

    dark_r, dark_g, dark_b = 17, 24, 39  # #111827
    dark_luminance = _luminance(dark_r, dark_g, dark_b)
    dark_contrast = (max(bg_luminance, dark_luminance) + 0.05) / (min(bg_luminance, dark_luminance) + 0.05)

    return "#111827" if dark_contrast >= white_contrast else "white"


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


def display_unit(portion) -> str:
    catalog_category = (portion.get("catalog_category") or "").strip().lower()
    manual_subtype = (portion.get("manual_subtype") or "").strip().lower()
    if catalog_category == "beverages":
        return "ml"
    liquid_hints = ("drink", "beverage", "juice", "soda", "smoothie", "milk", "coffee", "tea", "bebida")
    if any(token in manual_subtype for token in liquid_hints):
        return "ml"
    return "g"
