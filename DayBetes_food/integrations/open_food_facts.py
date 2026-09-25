"""Open Food Facts adapter (H17, measurement_conventions.md §5.1, §12.1).

This module only builds a prefill for the create form. It never logs (the route
logs the failure once, §8.3), it never persists anything and it has no retries:
the user can type the data by hand. The conversion depends on the unit each
field declares (`<field>_unit`) and never on the field name (decision
2026-09-25).
"""

import http.client
import json
from dataclasses import dataclass
from urllib import request as urlrequest
from urllib.error import HTTPError

from DayBetes_food.config import OPEN_FOOD_FACTS_BASE_URL, OPEN_FOOD_FACTS_TIMEOUT_SECONDS
from DayBetes_food.domain.catalog import (
    CATALOG_DEFAULT_PORTION_RANGE,
    CATALOG_NAME_MAX_LENGTH,
    CATALOG_SUBTYPE_MAX_LENGTH,
    normalize_catalog_name,
    parse_barcode,
)
from DayBetes_food.domain.constants import (
    NOVA_MAX,
    NOVA_MIN,
    FoodCategory,
    FoodPhysicalState,
    Nutriscore,
)
from DayBetes_food.domain.nutrition import (
    ETHANOL_DENSITY_G_PER_ML,
    NUTRIENT_LIMITS,
    NutrientValues,
    check_number,
)
from DayBetes_food.errors import ExternalServiceError, ValidationError

# OFF field name -> (canonical field, accepted unit, factor).
_MACRO_FIELDS = {
    "calories_100g": ("energy-kcal", "kcal", 1.0),
    "carbs_100g": ("carbohydrates", "g", 1.0),
    "sugars_100g": ("sugars", "g", 1.0),
    "fats_100g": ("fat", "g", 1.0),
    "saturated_100g": ("saturated-fat", "g", 1.0),
    "proteins_100g": ("proteins", "g", 1.0),
    "fiber_100g": ("fiber", "g", 1.0),
}


@dataclass(frozen=True)
class OffProductPrefill:
    barcode: str
    name: str | None
    brand: str | None
    category: FoodCategory | None
    subtype: str | None
    initial_state: FoodPhysicalState | None
    default_portion_g: float | None
    nutriscore: Nutriscore | None
    nova: int | None
    nutrients: NutrientValues
    alcohol_source_note: str | None


def _off_number(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _off_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _off_pick_name(product: dict) -> str | None:
    name = (
        _off_text(product.get("product_name_es"))
        or _off_text(product.get("product_name"))
        or _off_text(product.get("product_name_en"))
        or _off_text(product.get("generic_name_es"))
        or _off_text(product.get("generic_name"))
        or _off_text(product.get("generic_name_en"))
    )
    if name is None:
        return None
    name = normalize_catalog_name(name)
    if not name or len(name) > CATALOG_NAME_MAX_LENGTH:
        return None
    return name


def _off_pick_brand(product: dict) -> str | None:
    brands = _off_text(product.get("brands"))
    if not brands:
        return None
    first = brands.split(",")[0].strip()
    return first or None


def _off_categories(product: dict) -> list[str]:
    categories = _off_text(product.get("categories")) or ""
    return [part.strip() for part in categories.split(",") if part.strip()]


def _off_pick_subtype(product: dict) -> str | None:
    parts = _off_categories(product)
    if not parts:
        return None
    subtype = parts[-1].lower()
    if len(subtype) > CATALOG_SUBTYPE_MAX_LENGTH:
        return None
    return subtype


def _off_pick_category(product: dict) -> FoodCategory | None:
    parts = _off_categories(product)
    base = ""
    if len(parts) >= 3:
        base = parts[-3]
    elif len(parts) >= 2:
        base = parts[-2]
    elif len(parts) == 1:
        base = parts[0]

    blob = base.strip().lower()
    checks = (
        (("beverage", "drink", "juice", "soda", "water", "tea", "coffee"), FoodCategory.BEVERAGES),
        (("dairy", "milk", "yogurt", "cheese"), FoodCategory.DAIRY),
        (("cereal", "bread", "flour", "grain", "rice", "wheat", "oat"), FoodCategory.CEREALS),
        (("fruit", "apple", "banana", "berries"), FoodCategory.FRUITS),
        (("vegetable", "greens", "salad", "tomato"), FoodCategory.VEGETABLES),
        (("fish", "seafood", "salmon", "tuna"), FoodCategory.FISH),
        (("meat", "beef", "chicken", "pork", "ham"), FoodCategory.MEAT),
        (("legume", "lentil", "chickpea", "bean"), FoodCategory.LEGUMES),
        (("nut", "almond", "hazelnut", "walnut"), FoodCategory.NUTS),
        (("oil", "fat", "butter", "margarine"), FoodCategory.OILS_AND_FATS),
        (("sweet", "chocolate", "candy", "dessert", "biscuit", "cookie"), FoodCategory.SWEETS),
        (("sauce", "ketchup", "mustard", "mayo"), FoodCategory.SAUCES),
        (("condiment", "spice", "seasoning"), FoodCategory.CONDIMENTS),
        (("egg", "omelette"), FoodCategory.EGGS),
        (("potato", "tuber"), FoodCategory.TUBERS),
    )
    for keywords, category in checks:
        if any(keyword in blob for keyword in keywords):
            return category
    return None


def _off_nutriscore(product: dict) -> Nutriscore | None:
    grade = _off_text(product.get("nutriscore_grade"))
    if not grade:
        return None
    try:
        return Nutriscore(grade.upper())
    except ValueError:
        return None


def _off_nova(product: dict) -> int | None:
    raw = product.get("nova_group")
    try:
        nova = int(raw)
    except (TypeError, ValueError):
        return None
    if nova < NOVA_MIN or nova > NOVA_MAX:
        return None
    return nova


def _converted_nutrient(nutriments: dict, off_field: str, accepted_unit: str, factor: float):
    raw = _off_number(nutriments.get(f"{off_field}_100g"))
    if raw is None:
        return None
    unit = _off_text(nutriments.get(f"{off_field}_unit"))
    if unit != accepted_unit:
        return None
    return raw * factor


def _safe_check(value, field: str, limits=None):
    """An OFF value outside its range is not prefilled (None), never clamped."""
    if value is None:
        return None
    try:
        return check_number(round(value, 4), field, limits or NUTRIENT_LIMITS[field])
    except ValidationError:
        return None


def _prefill_from_product(barcode: str, product: dict) -> OffProductPrefill:
    nutriments = product.get("nutriments") or {}
    if not isinstance(nutriments, dict):
        nutriments = {}

    nutrients: dict[str, float | None] = {}
    for field, (off_field, unit, factor) in _MACRO_FIELDS.items():
        nutrients[field] = _safe_check(
            _converted_nutrient(nutriments, off_field, unit, factor), field
        )

    # Caffeine: g -> mg (×1000); mg -> mg.
    caffeine_raw = _off_number(nutriments.get("caffeine_100g"))
    caffeine_unit = _off_text(nutriments.get("caffeine_unit"))
    if caffeine_raw is None or caffeine_unit not in ("g", "mg"):
        nutrients["caffeine"] = None
    else:
        factor = 1000.0 if caffeine_unit == "g" else 1.0
        nutrients["caffeine"] = _safe_check(caffeine_raw * factor, "caffeine")

    # Alcohol: % vol -> g/100 g; g -> g/100 g.
    alcohol_source_note = None
    alcohol_raw = _off_number(nutriments.get("alcohol_100g"))
    alcohol_unit = _off_text(nutriments.get("alcohol_unit"))
    if alcohol_raw is None or alcohol_unit not in ("% vol", "g"):
        nutrients["alcohol"] = None
    elif alcohol_unit == "% vol":
        alcohol_source_note = f"OFF: {alcohol_raw:g} % vol"
        nutrients["alcohol"] = _safe_check(
            alcohol_raw * ETHANOL_DENSITY_G_PER_ML, "alcohol"
        )
    else:
        nutrients["alcohol"] = _safe_check(alcohol_raw, "alcohol")

    nutrients_obj = NutrientValues(**nutrients)

    category = _off_pick_category(product)

    default_portion_g = None
    if _off_text(product.get("serving_quantity_unit")) == "g":
        default_portion_g = _safe_check(
            _off_number(product.get("serving_quantity")),
            "default_portion",
            CATALOG_DEFAULT_PORTION_RANGE,
        )

    return OffProductPrefill(
        barcode=barcode,
        name=_off_pick_name(product),
        brand=_off_pick_brand(product),
        category=category,
        subtype=_off_pick_subtype(product),
        initial_state=(
            FoodPhysicalState.LIQUID
            if category is FoodCategory.BEVERAGES
            else FoodPhysicalState.SOLID
        ),
        default_portion_g=default_portion_g,
        nutriscore=_off_nutriscore(product),
        nova=_off_nova(product),
        nutrients=nutrients_obj,
        alcohol_source_note=alcohol_source_note,
    )


def fetch_product_prefill(barcode: str) -> OffProductPrefill | None:
    """None = product not found (HTTP 404 or JSON status 0).

    Raises ExternalServiceError on network error, timeout, unexpected status,
    non-JSON Content-Type or malformed JSON. Never logs: the route logs once
    (§8.3). No retries (§8.7: prefill, the user can type).
    """
    try:
        valid_barcode = parse_barcode(barcode)
    except ValidationError as exc:
        raise ExternalServiceError("off_invalid_barcode") from exc
    if valid_barcode is None:
        return None

    url = f"{OPEN_FOOD_FACTS_BASE_URL}/api/v2/product/{valid_barcode}.json"
    request = urlrequest.Request(
        url,
        headers={
            "User-Agent": "DayBetes/1.0 (personal TFG project)",
            "Accept": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(request, timeout=OPEN_FOOD_FACTS_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "") or ""
            if status != 200:
                raise ExternalServiceError("off_status")
            if "application/json" not in content_type.lower():
                raise ExternalServiceError("off_content_type")
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise ExternalServiceError("off_http_error") from exc
    except (OSError, http.client.HTTPException) as exc:
        # OSError covers URLError, timeouts and a connection reset while
        # reading; HTTPException an IncompleteRead (§8.6, §8.9).
        raise ExternalServiceError("off_network_error") from exc
    except UnicodeDecodeError as exc:
        raise ExternalServiceError("off_malformed_json") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExternalServiceError("off_malformed_json") from exc

    if not isinstance(payload, dict):
        raise ExternalServiceError("off_malformed_payload")
    if payload.get("status") == 0:
        return None
    product = payload.get("product")
    if not isinstance(product, dict):
        raise ExternalServiceError("off_malformed_payload")
    return _prefill_from_product(valid_barcode, product)
