from fasthtml.common import *
from datetime import datetime
import json
import difflib
import re
import unicodedata
from urllib import request as urlrequest
from urllib.parse import urlencode
from DayBetes_food.components.food.food_main import food_main
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.database.queries.crud import (
    add_catalog_item,
    get_all_catalog,
    get_all_manual_intakes,
    get_all_recipes,
    add_intake_event,
    add_portion_detail,
    get_catalog_item,
    get_catalog_item_by_barcode,
    get_manual_intake,
    get_recipe,
    get_portion_detail_by_recipe,
    get_portion_detail,
    get_recipe_portions_by_origin,
    get_default_user_id,
    get_intake_event,
    update_catalog_item,
    update_catalog_favorite,
    update_manual_intake,
    update_recipe,
    delete_catalog_item,
    delete_manual_intake,
    delete_recipe,
    add_manual_intake,
    add_recipe,
    add_food_brand,
    get_food_brand_suggestions,
    get_category_suggestions,
    get_subtype_suggestions,
    get_manual_origin_suggestions,
    get_consumed_food_usage_rankings,
    update_portion_detail_amount,
    update_portion_detail_fields,
    delete_portion_detail,
    normalize_brand_name,
)
from DayBetes_food.components.food.foods import (
    GLYCEMIC_INDEX_OPTIONS,
    INITIAL_STATE_OPTIONS,
    COOKING_OPTIONS,
    CONSERVATION_OPTIONS,
    MEAL_TYPES,
)
from DayBetes_food.components.food.foods import FoodSectionsContent, FoodCard, FavoriteButton, on_after
from DayBetes_food.components.food.foods import (
    CreateCatalogPage,
    CreateManualPage,
    CreateRecipePage,
    EditCatalogPage,
    EditManualPage,
    EditRecipePage,
    FoodDetailPage,
    RecipeIngredientPickerList,
    RecipeIngredientPickerPage,
    RecipeMacrosGrid,
)
from DayBetes_food.database.connection import get_connection


def _to_float(value: str):
    normalized = (value or "").strip().replace(",", ".")
    if not normalized:
        return None
    try:
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _to_int(value: str):
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        return int(normalized)
    except (TypeError, ValueError):
        return None


def _to_bool(value: str):
    return (value or "").strip().lower() in ("1", "true", "on", "yes")


def _smart_macro_float(
    smart_enabled: str,
    smart_raw: str,
    raw_value: str,
):
    if _to_bool(smart_enabled) and not (smart_raw or "").strip():
        return None
    return _to_float(raw_value)


def _to_str_or_none(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _off_number(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _off_pick_name(product: dict):
    return (
        _to_str_or_none(product.get("product_name_es"))
        or _to_str_or_none(product.get("product_name"))
        or _to_str_or_none(product.get("product_name_en"))
        or _to_str_or_none(product.get("generic_name_es"))
        or _to_str_or_none(product.get("generic_name"))
        or _to_str_or_none(product.get("generic_name_en"))
    )


def _off_pick_subtype(product: dict):
    categories = _to_str_or_none(product.get("categories")) or ""
    parts = [p.strip() for p in categories.split(",") if p.strip()]
    if parts:
        return parts[-1].lower()
    return None


def _off_pick_category(product: dict):
    categories = _to_str_or_none(product.get("categories")) or ""
    parts = [p.strip() for p in categories.split(",") if p.strip()]
    base = ""
    if len(parts) >= 3:
        base = parts[-3]
    elif len(parts) >= 2:
        base = parts[-2]
    elif len(parts) == 1:
        base = parts[0]

    blob = (base or "").strip().lower()
    if any(k in blob for k in ("beverage", "drink", "juice", "soda", "water", "tea", "coffee")):
        return "beverages"
    if any(k in blob for k in ("dairy", "milk", "yogurt", "cheese")):
        return "dairy"
    if any(k in blob for k in ("cereal", "bread", "flour", "grain", "rice", "wheat", "oat")):
        return "cereals"
    if any(k in blob for k in ("fruit", "apple", "banana", "berries")):
        return "fruits"
    if any(k in blob for k in ("vegetable", "greens", "salad", "tomato")):
        return "vegetables"
    if any(k in blob for k in ("fish", "seafood", "salmon", "tuna")):
        return "fish"
    if any(k in blob for k in ("meat", "beef", "chicken", "pork", "ham")):
        return "meat"
    if any(k in blob for k in ("legume", "lentil", "chickpea", "bean")):
        return "legumes"
    if any(k in blob for k in ("nut", "almond", "hazelnut", "walnut")):
        return "nuts"
    if any(k in blob for k in ("oil", "fat", "butter", "margarine")):
        return "oils_and_fats"
    if any(k in blob for k in ("sweet", "chocolate", "candy", "dessert", "biscuit", "cookie")):
        return "sweets"
    if any(k in blob for k in ("sauce", "ketchup", "mustard", "mayo")):
        return "sauces"
    if any(k in blob for k in ("condiment", "spice", "seasoning")):
        return "condiments"
    if any(k in blob for k in ("egg", "omelette")):
        return "eggs"
    if any(k in blob for k in ("potato", "tuber")):
        return "tubers"
    return None


def _off_prefill_by_barcode(barcode: str):
    clean = (barcode or "").strip()
    if not clean:
        return {}
    url = f"https://world.openfoodfacts.net/api/v2/product/{clean}.json"
    try:
        with urlrequest.urlopen(url, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return {"barcode": clean}
    product = payload.get("product") if isinstance(payload, dict) else None
    if not isinstance(product, dict):
        return {"barcode": clean}
    nutriments = product.get("nutriments") or {}
    category = _off_pick_category(product)
    prefill = {
        "barcode": clean,
        "name": _off_pick_name(product) or "",
        "brand": (_to_str_or_none(product.get("brands")) or "").split(",")[0].strip() if _to_str_or_none(product.get("brands")) else "",
        "category": category or "",
        "subtype": _off_pick_subtype(product) or "",
        "default_portion": _off_number(product.get("serving_quantity")),
        "initial_state": "liquid" if category == "beverages" else "solid",
        "nutriscore": (_to_str_or_none(product.get("nutriscore_grade")) or "").upper(),
        "nova": product.get("nova_group"),
        "calories_100g": _off_number(nutriments.get("energy-kcal_100g")),
        "carbs_100g": _off_number(nutriments.get("carbohydrates_100g")),
        "sugars_100g": _off_number(nutriments.get("sugars_100g")),
        "fats_100g": _off_number(nutriments.get("fat_100g")),
        "saturated_100g": _off_number(nutriments.get("saturated-fat_100g")),
        "proteins_100g": _off_number(nutriments.get("proteins_100g")),
        "fiber_100g": _off_number(nutriments.get("fiber_100g")),
        "alcohol": _off_number(nutriments.get("alcohol_100g")),
        "caffeine": _off_number(nutriments.get("caffeine_100g")),
    }
    for key, value in list(prefill.items()):
        if value is None:
            prefill[key] = ""
    return prefill


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return text


def _closest_option(value: str, options: list[str]) -> str:
    clean = (value or "").strip()
    if not clean:
        return ""
    by_norm = {}
    normalized_pool = []
    for opt in options or []:
        opt_clean = (opt or "").strip()
        if not opt_clean:
            continue
        norm = _normalize_text(opt_clean)
        if not norm:
            continue
        if norm not in by_norm:
            by_norm[norm] = opt_clean
            normalized_pool.append(norm)

    target = _normalize_text(clean)
    if not target or not normalized_pool:
        return clean
    if target in by_norm:
        return by_norm[target]
    matches = difflib.get_close_matches(target, normalized_pool, n=1, cutoff=0.72)
    if matches:
        return by_norm[matches[0]]
    return clean


def _normalized_choice_set(options: list[str] | None) -> set[str]:
    return {_normalize_text(opt) for opt in (options or []) if (opt or "").strip()}


def _is_allowed_choice(value: str, options: list[str] | None) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    allowed = _normalized_choice_set(options)
    return _normalize_text(text) in allowed


def _coerce_choice(
    value: str,
    *,
    options: list[str] | None,
    allow_add: bool,
    added: bool,
    required: bool,
    label: str,
) -> tuple[str | None, str | None]:
    text = (value or "").strip()
    if not text:
        if required:
            return None, f"{label} is required."
        return None, None

    if _is_allowed_choice(text, options):
        resolved = _closest_option(text, options or [])
        return (resolved or text), None

    if allow_add and added:
        return text, None

    action_hint = "Use Add to create a new value." if allow_add else "Choose one of the available options."
    return None, f"Invalid {label.lower()}. {action_hint}"


def _macro_value(row: dict, macro_key: str):
    catalog_value = row.get(f"catalog_{macro_key}_100g")
    manual_value = row.get(f"manual_{macro_key}_100g")
    return catalog_value if catalog_value is not None else manual_value


def _build_detail_summary(entry_type: str, entry: dict, recipe_portions: list | None = None) -> dict:
    if entry_type == "catalog":
        return {
            "subtitle": entry.get("brand") or "No brand",
            "default_amount_g": float(entry.get("default_portion") or 100.0),
            "per100": {
                "calories_100g": float(entry.get("calories_100g") or 0.0),
                "carbs_100g": float(entry.get("carbs_100g") or 0.0),
                "sugars_100g": float(entry.get("sugars_100g") or 0.0),
                "fats_100g": float(entry.get("fats_100g") or 0.0),
                "saturated_100g": float(entry.get("saturated_100g") or 0.0),
                "proteins_100g": float(entry.get("proteins_100g") or 0.0),
                "fiber_100g": float(entry.get("fiber_100g") or 0.0),
            },
            "info_rows": [
                ("Category", str(entry.get("category") or "")),
                ("Subtype", str(entry.get("subtype") or "")),
                ("Initial state", str(entry.get("initial_state") or "")),
                ("Nutriscore", str(entry.get("nutriscore") or "")),
                ("NOVA", str(entry.get("nova") or "")),
                ("Yuka", str(entry.get("yuka") or "")),
                ("Caffeine", str(entry.get("caffeine") or "")),
                ("Alcohol", str(entry.get("alcohol") or "")),
                ("Barcode", str(entry.get("barcode") or "")),
                ("Cooking factor", str(entry.get("cooking_factor") or "")),
            ],
        }

    if entry_type == "manual_intake":
        return {
            "subtitle": entry.get("origin") or "Manual intake",
            "default_amount_g": float(entry.get("amount_g") or 100.0),
            "per100": {
                "calories_100g": float(entry.get("calories_100g") or 0.0),
                "carbs_100g": float(entry.get("carbs_100g") or 0.0),
                "sugars_100g": float(entry.get("sugars_100g") or 0.0),
                "fats_100g": float(entry.get("fats_100g") or 0.0),
                "saturated_100g": float(entry.get("saturated_100g") or 0.0),
                "proteins_100g": float(entry.get("proteins_100g") or 0.0),
                "fiber_100g": float(entry.get("fiber_100g") or 0.0),
            },
            "info_rows": [
                ("Description", str(entry.get("description") or "")),
                ("Subtype", str(entry.get("subtype") or "")),
                ("Origin", str(entry.get("origin") or "")),
                ("Stored amount", str(entry.get("amount_g") or "")),
                ("Glycemic index", str(entry.get("glycemic_index") or "")),
                ("IG confidence", str(entry.get("ig_confidence") or "")),
                ("Caffeine", str(entry.get("caffeine") or "")),
                ("Alcohol", str(entry.get("alcohol") or "")),
            ],
        }

    portions = recipe_portions or []
    total_amount = sum(float(row.get("amount_g") or 0.0) for row in portions)
    totals = {
        "calories_100g": 0.0,
        "carbs_100g": 0.0,
        "sugars_100g": 0.0,
        "fats_100g": 0.0,
        "saturated_100g": 0.0,
        "proteins_100g": 0.0,
        "fiber_100g": 0.0,
    }
    for row in portions:
        amount = float(row.get("amount_g") or 0.0)
        for key in list(totals.keys()):
            macro = _macro_value(row, key.replace("_100g", ""))
            if macro is None:
                continue
            totals[key] += amount * float(macro) / 100.0

    per100 = {}
    for key, total in totals.items():
        per100[key] = (total * 100.0 / total_amount) if total_amount > 0 else 0.0

    return {
        "subtitle": "Recipe",
        "default_amount_g": total_amount or 100.0,
        "per100": per100,
        "info_rows": [
            ("Meal type", str(entry.get("meal_type") or "")),
            ("Notes", str(entry.get("notes") or "")),
            ("Ingredients", str(len(portions))),
            ("Recipe amount", f"{total_amount:.1f}" if total_amount > 0 else ""),
        ],
    }


def _sorted_food_entries(catalog_items, manual_items, recipes, viewer_user_id: int | None = None):
    def _is_owned(entry_type: str, item: dict) -> bool:
        if not viewer_user_id:
            return False
        raw_owner = item.get("created_by") if entry_type in ("catalog", "manual_intake") else item.get("users_id")
        try:
            return int(raw_owner) == int(viewer_user_id)
        except (TypeError, ValueError):
            return False

    entries = []
    for item in catalog_items:
        entries.append({"entry_type": "catalog", "is_owned": _is_owned("catalog", item), **item})
    for item in manual_items:
        entries.append({"entry_type": "manual_intake", "is_owned": _is_owned("manual_intake", item), **item})
    for item in recipes:
        entries.append({"entry_type": "recipe", "is_owned": _is_owned("recipe", item), **item})
    entries.sort(
        key=lambda item: (
            0 if (item.get("favorite") or item.get("is_owned")) else 1,
            0 if item.get("favorite") else 1,
            (item.get("name") or "").lower(),
        )
    )
    return entries


def _is_owned_by_viewer(entry_type: str, item: dict, viewer_user_id: int | None) -> bool:
    if not viewer_user_id:
        return False
    raw_owner = item.get("created_by") if entry_type in ("catalog", "manual_intake") else item.get("users_id")
    try:
        return int(raw_owner) == int(viewer_user_id)
    except (TypeError, ValueError):
        return False


def _community_entries(connection, search: str = "") -> list[dict]:
    viewer_user_id = get_default_user_id(connection)
    viewer_id = viewer_user_id if viewer_user_id else -1
    search_value = (search or "").strip() or None

    catalog_items = get_all_catalog(connection, search=search_value, viewer_user_id=viewer_id)
    manual_items = get_all_manual_intakes(connection, search=search_value, viewer_user_id=viewer_id)

    if viewer_user_id:
        catalog_items = [item for item in catalog_items if not _is_owned_by_viewer("catalog", item, viewer_user_id)]
        manual_items = [item for item in manual_items if not _is_owned_by_viewer("manual_intake", item, viewer_user_id)]

    entries = []
    for item in manual_items:
        entries.append({"entry_type": "manual_intake", "is_owned": False, **item})
    for item in catalog_items:
        entries.append({"entry_type": "catalog", "is_owned": False, **item})
    return entries


def _recommended_entries(connection, search: str = "", days: int = 14) -> list[dict]:
    viewer_user_id = get_default_user_id(connection)
    viewer_id = viewer_user_id if viewer_user_id else -1
    search_value = (search or "").strip() or None

    catalog_items = get_all_catalog(connection, search=search_value, viewer_user_id=viewer_id)
    manual_items = get_all_manual_intakes(connection, search=search_value, viewer_user_id=viewer_id)
    catalog_by_id = {int(item["id"]): item for item in catalog_items if item.get("id") is not None}
    manual_by_id = {int(item["id"]): item for item in manual_items if item.get("id") is not None}

    rankings = get_consumed_food_usage_rankings(connection, days=days)
    entries = []
    for row in rankings:
        entry_type = row.get("entry_type")
        try:
            entry_id = int(row.get("entry_id"))
        except (TypeError, ValueError):
            continue

        if entry_type == "catalog":
            item = catalog_by_id.get(entry_id)
            if not item:
                continue
            entries.append(
                {
                    "entry_type": "catalog",
                    "is_owned": _is_owned_by_viewer("catalog", item, viewer_user_id),
                    "usage_count": int(row.get("usage_count") or 0),
                    **item,
                }
            )
        elif entry_type == "manual_intake":
            item = manual_by_id.get(entry_id)
            if not item:
                continue
            entries.append(
                {
                    "entry_type": "manual_intake",
                    "is_owned": _is_owned_by_viewer("manual_intake", item, viewer_user_id),
                    "usage_count": int(row.get("usage_count") or 0),
                    **item,
                }
            )
    return entries


def _recipes_entries(connection, search: str = "", recipes_mode: str = "mine") -> list[dict]:
    user_id = get_default_user_id(connection)
    viewer_id = user_id if user_id else -1
    clean_search = (search or "").strip() or None
    mode = (recipes_mode or "mine").strip().lower()

    if mode == "discover":
        recipes = get_all_recipes(connection, search=clean_search, viewer_user_id=viewer_id)
        if user_id:
            recipes = [item for item in recipes if not _is_owned_by_viewer("recipe", item, user_id)]
    else:
        mode = "mine"
        if not user_id:
            recipes = []
        else:
            recipes = get_all_recipes(connection, users_id=user_id, search=clean_search, viewer_user_id=viewer_id)

    return _sorted_food_entries([], [], recipes, viewer_user_id=user_id)


def _community_sections_content(entries: list[dict]):
    grouped = {"catalog": [], "manual_intake": []}
    for item in entries:
        entry_type = item.get("entry_type")
        if entry_type in grouped:
            grouped[entry_type].append(item)

    nodes = []
    for entry_type, title in (
        ("catalog", "Catalog"),
        ("manual_intake", "Manual"),
    ):
        section_items = grouped[entry_type]
        if not section_items:
            continue
        nodes.append(H2(title, cls="text-gray-700"))
        nodes.extend(FoodCard(item) for item in section_items)
    return nodes


def _entry_owner_id(entry_type: str, entry: dict) -> int | None:
    if not entry:
        return None
    raw = entry.get("created_by") if entry_type in ("catalog", "manual_intake") else entry.get("users_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _can_view_entry(entry_type: str, entry: dict, viewer_user_id: int | None) -> bool:
    if not entry:
        return False
    if not bool(entry.get("is_private")):
        return True
    owner_id = _entry_owner_id(entry_type, entry)
    return bool(viewer_user_id and owner_id == viewer_user_id)


def _can_toggle_private(entry_type: str, entry: dict, viewer_user_id: int | None) -> bool:
    owner_id = _entry_owner_id(entry_type, entry)
    return bool(viewer_user_id and owner_id and owner_id == viewer_user_id)


def _can_edit_entry(entry_type: str, entry: dict, viewer_user_id: int | None) -> bool:
    owner_id = _entry_owner_id(entry_type, entry)
    return bool(viewer_user_id and owner_id and owner_id == viewer_user_id)


def _copy_root_id(entry: dict) -> int | None:
    raw = entry.get("origin_root_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _next_copy_name(connection, entry_type: str, base_name: str, owner_user_id: int) -> str:
    base = (base_name or "").strip() or "Untitled"
    for index in range(1, 5000):
        suffix = " (copy)" if index == 1 else f" (copy {index})"
        candidate = f"{base}{suffix}"
        with connection.cursor() as cursor:
            if entry_type == "catalog":
                cursor.execute("SELECT 1 FROM catalog WHERE lower(name) = lower(%(name)s) LIMIT 1;", {"name": candidate})
            elif entry_type == "manual_intake":
                cursor.execute(
                    "SELECT 1 FROM manual_intake WHERE created_by = %(user_id)s AND lower(name) = lower(%(name)s) LIMIT 1;",
                    {"user_id": owner_user_id, "name": candidate},
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM recipe WHERE users_id = %(user_id)s AND lower(name) = lower(%(name)s) LIMIT 1;",
                    {"user_id": owner_user_id, "name": candidate},
                )
            if cursor.fetchone() is None:
                return candidate
    return f"{base} (copy {datetime.now().strftime('%Y%m%d%H%M%S')})"


def _filtered_entries(connection, search: str = "", filter_value: str = "all", include_recipes: bool = True):
    user_id = get_default_user_id(connection)
    has_search = bool((search or "").strip())
    viewer_id = user_id if user_id else -1

    def _unique_by_id(items: list[dict]) -> list[dict]:
        seen = set()
        merged = []
        for item in items:
            item_id = item.get("id")
            if item_id in seen:
                continue
            seen.add(item_id)
            merged.append(item)
        return merged

    if filter_value == "food":
        if has_search:
            catalog_items = get_all_catalog(connection, search=search or None, viewer_user_id=viewer_id)
            manual_items = get_all_manual_intakes(connection, search=search or None, viewer_user_id=viewer_id)
        else:
            catalog_items = _unique_by_id(
                get_all_catalog(connection, favorite=True, viewer_user_id=viewer_id)
                + (get_all_catalog(connection, users_id=user_id, viewer_user_id=viewer_id) if user_id else [])
            )
            manual_items = _unique_by_id(
                get_all_manual_intakes(connection, favorite=True, viewer_user_id=viewer_id)
                + (get_all_manual_intakes(connection, users_id=user_id, viewer_user_id=viewer_id) if user_id else [])
            )
        entries = _sorted_food_entries(catalog_items, manual_items, [], viewer_user_id=user_id)
    elif filter_value == "recipes":
        if has_search:
            recipes = get_all_recipes(connection, search=search or None, viewer_user_id=viewer_id) if include_recipes else []
        else:
            recipes = _unique_by_id(
                (get_all_recipes(connection, favorite=True, viewer_user_id=viewer_id) if include_recipes else [])
                + (get_all_recipes(connection, users_id=user_id, viewer_user_id=viewer_id) if include_recipes and user_id else [])
            )
        entries = _sorted_food_entries([], [], recipes, viewer_user_id=user_id)
    elif filter_value == "favs":
        catalog_items = get_all_catalog(connection, search=search or None, favorite=True, viewer_user_id=viewer_id)
        manual_items = get_all_manual_intakes(connection, search=search or None, favorite=True, viewer_user_id=viewer_id)
        recipes = (
            get_all_recipes(connection, search=search or None, favorite=True, viewer_user_id=viewer_id)
            if include_recipes
            else []
        )
        entries = _sorted_food_entries(catalog_items, manual_items, recipes, viewer_user_id=user_id)
    else:
        if has_search:
            catalog_items = get_all_catalog(connection, search=search or None, viewer_user_id=viewer_id)
            manual_items = get_all_manual_intakes(connection, search=search or None, viewer_user_id=viewer_id)
            recipes = get_all_recipes(connection, search=search or None, viewer_user_id=viewer_id) if include_recipes else []
        else:
            catalog_items = _unique_by_id(
                get_all_catalog(connection, favorite=True, viewer_user_id=viewer_id)
                + (get_all_catalog(connection, users_id=user_id, viewer_user_id=viewer_id) if user_id else [])
            )
            manual_items = _unique_by_id(
                get_all_manual_intakes(connection, favorite=True, viewer_user_id=viewer_id)
                + (get_all_manual_intakes(connection, users_id=user_id, viewer_user_id=viewer_id) if user_id else [])
            )
            recipes = _unique_by_id(
                (get_all_recipes(connection, favorite=True, viewer_user_id=viewer_id) if include_recipes else [])
                + (get_all_recipes(connection, users_id=user_id, viewer_user_id=viewer_id) if include_recipes and user_id else [])
            )
        entries = _sorted_food_entries(catalog_items, manual_items, recipes, viewer_user_id=user_id)

    return entries



def _error_msg(text: str):
    return render_fragment(
        Div(
            P("Error", cls="text-[11px] font-semibold text-red-800"),
            P(text, cls="text-xs text-red-700"),
            cls="web_container p-2 rounded-lg border border-red-200/70 bg-red-50/60",
        )
    )


LIST_PAGE_SIZE = 15


def _search_load_more_node(
    search: str,
    filter_value: str,
    search_mode: str,
    food_mode: str,
    favs_mode: str,
    recipes_mode: str,
    next_page: int,
):
    query = urlencode({
        "search": search,
        "filter": filter_value,
        "search_mode": search_mode,
        "food_mode": food_mode,
        "favs_mode": favs_mode,
        "recipes_mode": recipes_mode,
        "page": next_page,
    })
    return Div(
        "Loading more...",
        hx_get=f"/food/list?{query}",
        hx_trigger="revealed",
        hx_swap="outerHTML",
        hx_target="this",
        data_skip_page_loading="true",
        cls="w-full text-center text-xs text-gray-500 py-2",
    )


def setup_food_routes(rt):
    
    @rt("/food")
    def get(request):
        return render_page(request, food_main)

    @rt("/food/create/catalog/form")
    def get(request: Request, barcode: str = "", existing_id: str = ""):
        clean_barcode = (barcode or "").strip()
        prefill = _off_prefill_by_barcode(clean_barcode) if clean_barcode else {}
        existing_item_id = int(existing_id) if (existing_id or "").isdigit() else None
        if clean_barcode and not existing_item_id:
            with get_connection() as connection:
                user_id = get_default_user_id(connection)
                viewer_id = user_id if user_id else -1
                existing = get_catalog_item_by_barcode(connection, clean_barcode, viewer_user_id=viewer_id)
                if existing:
                    existing_item_id = int(existing["id"])
        with get_connection() as connection:
            brands = get_food_brand_suggestions(connection, search="", limit=500)
            categories = get_category_suggestions(connection, search="", limit=500)
            subtypes = get_subtype_suggestions(connection, search="", limit=500)
        subtype_prefill = (prefill.get("subtype") or "").strip()
        if subtype_prefill:
            prefill["subtype"] = _closest_option(subtype_prefill, subtypes)
        brand_prefill = (prefill.get("brand") or "").strip()
        if brand_prefill:
            prefill["brand"] = _closest_option(brand_prefill, brands)
        return render_page(
            request,
            lambda _: CreateCatalogPage(
                brand_options=brands,
                category_options=categories,
                subtype_options=subtypes,
                prefill=prefill,
                existing_item_id=existing_item_id,
            ),
            show_cart=False,
        )

    @rt("/food/create/manual/form")
    def get(request: Request):
        with get_connection() as connection:
            subtypes = get_subtype_suggestions(connection, search="", limit=500)
            origins = get_manual_origin_suggestions(connection, search="", limit=500)
        return render_page(request, lambda _: CreateManualPage(subtype_options=subtypes, origin_options=origins), show_cart=False)

    @rt("/food/create/recipe/form")
    def get(request: Request):
        return render_page(request, lambda _: CreateRecipePage(), show_cart=False)

    @rt("/food/item/{entry_type}/{entry_id}")
    def get(request: Request, entry_type: str, entry_id: int):
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            entry = None
            recipe_portions = None
            if entry_type == "catalog":
                entry = get_catalog_item(connection, entry_id)
            elif entry_type == "manual_intake":
                entry = get_manual_intake(connection, entry_id)
            elif entry_type == "recipe":
                entry = get_recipe(connection, entry_id)
                recipe_portions = get_portion_detail_by_recipe(connection, entry_id) if entry else []
            if not entry or not _can_view_entry(entry_type, entry, user_id):
                return HTMLResponse(status_code=404)
            summary = _build_detail_summary(entry_type, entry, recipe_portions=recipe_portions)
            can_edit = _can_edit_entry(entry_type, entry, user_id)
            can_delete = can_edit
        return render_page(
            request,
            lambda conn: FoodDetailPage(
                conn,
                user_id=user_id or 0,
                entry_type=entry_type,
                entry=entry,
                summary=summary,
                recipe_portions=recipe_portions,
                can_edit=can_edit,
                can_delete=can_delete,
            ),
            show_cart=False,
        )

    @rt("/food/recipe/{recipe_id}/ingredients/form")
    def get(request: Request, recipe_id: int):
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return HTMLResponse(status_code=404)
            entries = _filtered_entries(connection, search="", filter_value="food", include_recipes=False)
        return render_page(request, lambda _: RecipeIngredientPickerPage(recipe_entry=recipe, foods=entries), show_cart=False)

    @rt("/food/recipe/{recipe_id}/ingredients/list")
    def get(request: Request, recipe_id: int, search: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return HTMLResponse(status_code=404)
            entries = _filtered_entries(connection, search=search, filter_value="food", include_recipes=False)
        return render_fragment(RecipeIngredientPickerList(recipe_id=recipe_id, foods=entries))

    @rt("/food/recipe/{recipe_id}/ingredients/add/{entry_type}/{entry_id}")
    def post(request: Request, recipe_id: int, entry_type: str, entry_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if entry_type not in ("catalog", "manual_intake"):
            return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=400)

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)

            amount_g = 100.0
            if entry_type == "catalog":
                item = get_catalog_item(connection, entry_id)
                if not item or not _can_view_entry("catalog", item, user_id):
                    return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)
                amount_g = max(1.0, float(item.get("default_portion") or 100.0))
            else:
                item = get_manual_intake(connection, entry_id)
                if not item or not _can_view_entry("manual_intake", item, user_id):
                    return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)
                amount_g = max(1.0, float(item.get("amount_g") or 100.0))

            existing = get_recipe_portions_by_origin(connection, recipe_id=recipe_id, origin=entry_type, origin_id=entry_id)
            if existing:
                keep = existing[0]
                total_amount = sum(float(row.get("amount_g") or 0.0) for row in existing) + amount_g
                updated = update_portion_detail_amount(connection, portion_id=int(keep["id"]), amount_g=total_amount)
                deleted_ok = True
                for duplicate in existing[1:]:
                    deleted_ok = delete_portion_detail(connection, int(duplicate["id"])) and deleted_ok
                ok = bool(updated and deleted_ok)
            else:
                created = add_portion_detail(
                    connection,
                    origin=entry_type,
                    origin_id=entry_id,
                    destination="recipe",
                    destination_id=recipe_id,
                    amount_g=amount_g,
                )
                ok = bool(created)

        return HTMLResponse("", headers={"HX-Trigger": "addSuccess" if ok else "addError"})

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/amount")
    def post(request: Request, recipe_id: int, portion_id: int, amount_g: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        parsed_amount = _to_float(amount_g)
        if parsed_amount is None or parsed_amount <= 0:
            return render_fragment(P("Invalid amount.", cls="text-red-700"))

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return render_fragment(P("Recipe not found.", cls="text-red-700"))
            portion = get_portion_detail(connection, portion_id)
            if not portion or int(portion.get("recipe_id") or 0) != recipe_id:
                return render_fragment(P("Ingredient not found.", cls="text-red-700"))
            updated = update_portion_detail_amount(connection, portion_id=portion_id, amount_g=parsed_amount)
            recipe_portions = get_portion_detail_by_recipe(connection, recipe_id) if updated else []
            recipe_total_amount = sum(float(row.get("amount_g") or 0.0) for row in recipe_portions)

        if not updated:
            return render_fragment(P("Could not update ingredient.", cls="text-red-700"))
        response = render_fragment(P("Saved", cls="text-green-700"))
        response.headers["HX-Trigger"] = json.dumps(
            {
                "recipe-amount-updated": {
                    "recipe_id": recipe_id,
                    "total_amount": recipe_total_amount,
                }
            }
        )
        return response

    @rt("/food/recipe/{recipe_id}/macros")
    def get(request: Request, recipe_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_view_entry("recipe", recipe, user_id):
                return HTMLResponse(status_code=404)
            portions = get_portion_detail_by_recipe(connection, recipe_id)
            summary = _build_detail_summary("recipe", recipe, recipe_portions=portions)
            per100 = summary.get("per100") or {}
            total_amount = max(1.0, _to_float(str(summary.get("default_amount_g") or 0.0)) or 1.0)
        return render_fragment(RecipeMacrosGrid(recipe_id=recipe_id, per100=per100, total_amount=total_amount))

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/advanced")
    def post(
        request: Request,
        recipe_id: int,
        portion_id: int,
        cooking: str = "",
        final_state: str = "",
        conservation: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_cooking, cooking_error = _coerce_choice(
            cooking,
            options=COOKING_OPTIONS,
            allow_add=False,
            added=False,
            required=False,
            label="Cooking",
        )
        if cooking_error:
            return render_fragment(P(cooking_error, cls="text-red-700"))
        clean_final_state, final_state_error = _coerce_choice(
            final_state,
            options=INITIAL_STATE_OPTIONS,
            allow_add=False,
            added=False,
            required=False,
            label="Final state",
        )
        if final_state_error:
            return render_fragment(P(final_state_error, cls="text-red-700"))
        clean_conservation, conservation_error = _coerce_choice(
            conservation,
            options=CONSERVATION_OPTIONS,
            allow_add=False,
            added=False,
            required=False,
            label="Conservation",
        )
        if conservation_error:
            return render_fragment(P(conservation_error, cls="text-red-700"))

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return render_fragment(P("Recipe not found.", cls="text-red-700"))
            portion = get_portion_detail(connection, portion_id)
            if not portion or int(portion.get("recipe_id") or 0) != recipe_id:
                return render_fragment(P("Ingredient not found.", cls="text-red-700"))
            updated = update_portion_detail_fields(
                connection,
                portion_id=portion_id,
                cooking=clean_cooking,
                final_state=clean_final_state,
                conservation=clean_conservation,
            )

        if not updated:
            return render_fragment(P("Could not save advanced fields.", cls="text-red-700"))
        return render_fragment(P("Advanced saved", cls="text-green-700"))

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/delete")
    def post(request: Request, recipe_id: int, portion_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return HTMLResponse(status_code=404)
            portion = get_portion_detail(connection, portion_id)
            if not portion or int(portion.get("recipe_id") or 0) != recipe_id:
                return HTMLResponse(status_code=404)
            ok = delete_portion_detail(connection, portion_id)

        return HTMLResponse("", status_code=200 if ok else 400)

    @rt("/food/copy/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if entry_type not in ("catalog", "manual_intake", "recipe"):
            return _error_msg("Unsupported entry type.")

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return _error_msg("No users found.")

            if entry_type == "catalog":
                source = get_catalog_item(connection, entry_id)
            elif entry_type == "manual_intake":
                source = get_manual_intake(connection, entry_id)
            else:
                source = get_recipe(connection, entry_id)

            if not source or not _can_view_entry(entry_type, source, user_id):
                return _error_msg("Item not found.")

            if _can_edit_entry(entry_type, source, user_id):
                location = f"/food/edit/{entry_type if entry_type != 'manual_intake' else 'manual_intake'}/{entry_id}/form"
                return HTMLResponse("", headers={"HX-Redirect": location})

            root_id = _copy_root_id(source) or int(source["id"])
            copy_name = _next_copy_name(connection, entry_type, str(source.get("name") or ""), int(user_id))

            if entry_type == "catalog":
                payload = {
                    "created_by": int(user_id),
                    "origin_root_id": root_id,
                    "name": copy_name,
                    "brand": source.get("brand"),
                    "category": source.get("category"),
                    "subtype": source.get("subtype"),
                    "initial_state": source.get("initial_state"),
                    "nutriscore": source.get("nutriscore"),
                    "nova": source.get("nova"),
                    "yuka": source.get("yuka"),
                    "default_portion": source.get("default_portion"),
                    "calories_100g": source.get("calories_100g"),
                    "carbs_100g": source.get("carbs_100g"),
                    "sugars_100g": source.get("sugars_100g"),
                    "fats_100g": source.get("fats_100g"),
                    "saturated_100g": source.get("saturated_100g"),
                    "proteins_100g": source.get("proteins_100g"),
                    "fiber_100g": source.get("fiber_100g"),
                    "caffeine": source.get("caffeine"),
                    "alcohol": source.get("alcohol"),
                    "barcode": source.get("barcode"),
                    "cooking_factor": source.get("cooking_factor"),
                    "favorite": False,
                    "is_private": False,
                }
                created_id = add_catalog_item(connection, payload)
                if payload.get("brand"):
                    add_food_brand(connection, str(payload["brand"]))
            elif entry_type == "manual_intake":
                payload = {
                    "created_by": int(user_id),
                    "origin_root_id": root_id,
                    "name": copy_name,
                    "description": source.get("description"),
                    "subtype": source.get("subtype"),
                    "origin": source.get("origin"),
                    "amount_g": source.get("amount_g"),
                    "calories_100g": source.get("calories_100g"),
                    "carbs_100g": source.get("carbs_100g"),
                    "sugars_100g": source.get("sugars_100g"),
                    "fats_100g": source.get("fats_100g"),
                    "saturated_100g": source.get("saturated_100g"),
                    "proteins_100g": source.get("proteins_100g"),
                    "fiber_100g": source.get("fiber_100g"),
                    "caffeine": source.get("caffeine"),
                    "alcohol": source.get("alcohol"),
                    "glycemic_index": source.get("glycemic_index"),
                    "ig_confidence": source.get("ig_confidence"),
                    "favorite": False,
                    "is_private": False,
                }
                created_id = add_manual_intake(connection, payload)
            else:
                created_id = add_recipe(
                    connection,
                    users_id=int(user_id),
                    origin_root_id=root_id,
                    name=copy_name,
                    meal_type=source.get("meal_type"),
                    notes=source.get("notes"),
                    favorite=False,
                    is_private=False,
                )
                if created_id:
                    source_portions = get_portion_detail_by_recipe(connection, int(source["id"]))
                    for portion in source_portions:
                        origin = "catalog" if portion.get("catalog_id") else "manual_intake"
                        origin_id = int(portion.get("catalog_id") or portion.get("manual_intake_id") or 0)
                        amount_g = float(portion.get("amount_g") or 0.0)
                        if origin_id <= 0:
                            continue
                        if amount_g <= 0:
                            continue
                        add_portion_detail(
                            connection,
                            origin=origin,
                            origin_id=origin_id,
                            destination="recipe",
                            destination_id=int(created_id),
                            amount_g=amount_g,
                            cooking=portion.get("cooking"),
                            conservation=portion.get("conservation"),
                            final_state=portion.get("final_state"),
                            strictly_weighed=portion.get("strictly_weighed"),
                            macros_quality=portion.get("macros_quality"),
                            plate_amount=portion.get("plate_amount"),
                            is_cooked_weight=bool(portion.get("is_cooked_weight")),
                        )

            if not created_id:
                return _error_msg("Could not create editable copy.")

            target_type = "manual_intake" if entry_type == "manual_intake" else entry_type
            return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/{target_type}/{created_id}/form"})

    @rt("/food/edit/{entry_type}/{entry_id}/form")
    def get(request: Request, entry_type: str, entry_id: int):
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            entry = None
            if entry_type == "catalog":
                entry = get_catalog_item(connection, entry_id)
                if not entry or not _can_view_entry("catalog", entry, user_id):
                    return HTMLResponse(status_code=404)
                if not _can_edit_entry("catalog", entry, user_id):
                    return HTMLResponse(status_code=403)
                brands = get_food_brand_suggestions(connection, search="", limit=500)
                categories = get_category_suggestions(connection, search="", limit=500)
                subtypes = get_subtype_suggestions(connection, search="", limit=500)
                return render_page(
                    request,
                    lambda _: EditCatalogPage(
                        entry=entry,
                        brand_options=brands,
                        category_options=categories,
                        subtype_options=subtypes,
                        show_private=_can_toggle_private("catalog", entry, user_id),
                    ),
                    show_cart=False,
                )
            if entry_type == "manual_intake":
                entry = get_manual_intake(connection, entry_id)
                if not entry or not _can_view_entry("manual_intake", entry, user_id):
                    return HTMLResponse(status_code=404)
                if not _can_edit_entry("manual_intake", entry, user_id):
                    return HTMLResponse(status_code=403)
                subtypes = get_subtype_suggestions(connection, search="", limit=500)
                origins = get_manual_origin_suggestions(connection, search="", limit=500)
                return render_page(
                    request,
                    lambda _: EditManualPage(
                        entry=entry,
                        subtype_options=subtypes,
                        origin_options=origins,
                        show_private=_can_toggle_private("manual_intake", entry, user_id),
                    ),
                    show_cart=False,
                )
            if entry_type == "recipe":
                entry = get_recipe(connection, entry_id)
                if not entry or not _can_view_entry("recipe", entry, user_id):
                    return HTMLResponse(status_code=404)
                if not _can_edit_entry("recipe", entry, user_id):
                    return HTMLResponse(status_code=403)
                return render_page(
                    request,
                    lambda _: EditRecipePage(entry=entry, show_private=_can_toggle_private("recipe", entry, user_id)),
                    show_cart=False,
                )
        return HTMLResponse(status_code=404)

    @rt("/food/delete/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if entry_type not in ("catalog", "manual_intake", "recipe"):
            return _error_msg("Unsupported entry type.")

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return _error_msg("No users found.")

            current = None
            deleted = False
            if entry_type == "catalog":
                current = get_catalog_item(connection, entry_id)
                if not current or not _can_view_entry("catalog", current, user_id):
                    return _error_msg("Catalog item not found.")
                if not _can_edit_entry("catalog", current, user_id):
                    return _error_msg("Only the owner can delete this item.")
                deleted = delete_catalog_item(connection, entry_id)
            elif entry_type == "manual_intake":
                current = get_manual_intake(connection, entry_id)
                if not current or not _can_view_entry("manual_intake", current, user_id):
                    return _error_msg("Manual intake not found.")
                if not _can_edit_entry("manual_intake", current, user_id):
                    return _error_msg("Only the owner can delete this item.")
                deleted = delete_manual_intake(connection, entry_id)
            else:
                current = get_recipe(connection, entry_id)
                if not current or not _can_view_entry("recipe", current, user_id):
                    return _error_msg("Recipe not found.")
                if not _can_edit_entry("recipe", current, user_id):
                    return _error_msg("Only the owner can delete this item.")
                deleted = delete_recipe(connection, entry_id)

            if not deleted:
                return _error_msg("Could not delete this item. It may be in use.")
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/log/{entry_type}/{entry_id}")
    def post(
        request: Request,
        entry_type: str,
        entry_id: int,
        amount_g: str = "",
        total_amount_g: str = "",
        intake_event_id: str = "",
        cooking: str = "",
        final_state: str = "",
        conservation: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        parsed_amount = _to_float(amount_g)
        parsed_total = _to_float(total_amount_g)
        if parsed_amount is None or parsed_amount <= 0:
            return render_fragment(P("Amount must be greater than 0.", cls="text-red-700"))
        if parsed_total is not None and parsed_total > 0:
            parsed_amount = min(parsed_amount, parsed_total)
        clean_cooking, cooking_error = _coerce_choice(
            cooking,
            options=COOKING_OPTIONS,
            allow_add=False,
            added=False,
            required=False,
            label="Cooking",
        )
        if cooking_error:
            return render_fragment(P(cooking_error, cls="text-red-700"))
        clean_final_state, final_state_error = _coerce_choice(
            final_state,
            options=INITIAL_STATE_OPTIONS,
            allow_add=False,
            added=False,
            required=False,
            label="Final state",
        )
        if final_state_error:
            return render_fragment(P(final_state_error, cls="text-red-700"))
        clean_conservation, conservation_error = _coerce_choice(
            conservation,
            options=CONSERVATION_OPTIONS,
            allow_add=False,
            added=False,
            required=False,
            label="Conservation",
        )
        if conservation_error:
            return render_fragment(P(conservation_error, cls="text-red-700"))

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return render_fragment(P("No users available.", cls="text-red-700"))
            origin_item = None
            if entry_type == "catalog":
                origin_item = get_catalog_item(connection, entry_id)
            elif entry_type == "manual_intake":
                origin_item = get_manual_intake(connection, entry_id)
            elif entry_type == "recipe":
                origin_item = get_recipe(connection, entry_id)
            if not origin_item or not _can_view_entry(entry_type, origin_item, user_id):
                return render_fragment(P("Item not found.", cls="text-red-700"))

            if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                event_id = int(intake_event_id)
            else:
                event_id = add_intake_event(connection, users_id=user_id, state="planned")

            if not event_id:
                return render_fragment(P("Could not create meal event.", cls="text-red-700"))

            event_data = get_intake_event(connection, event_id)
            offset_minutes = 0
            if event_data and event_data.get("meal_time"):
                delta = datetime.now() - event_data["meal_time"]
                offset_minutes = int(delta.total_seconds() // 60)

            created = []
            if entry_type == "catalog":
                created.append(
                    add_portion_detail(
                        connection,
                        origin="catalog",
                        origin_id=entry_id,
                        destination="intake_event",
                        destination_id=event_id,
                        amount_g=parsed_amount,
                        cooking=clean_cooking,
                        final_state=clean_final_state,
                        conservation=clean_conservation,
                        strictly_weighed=True,
                        macros_quality=True,
                        plate_amount=parsed_amount,
                        offset_minutes=offset_minutes,
                    )
                )
            elif entry_type == "manual_intake":
                created.append(
                    add_portion_detail(
                        connection,
                        origin="manual_intake",
                        origin_id=entry_id,
                        destination="intake_event",
                        destination_id=event_id,
                        amount_g=parsed_amount,
                        cooking=clean_cooking,
                        final_state=clean_final_state,
                        conservation=clean_conservation,
                        strictly_weighed=True,
                        macros_quality=True,
                        plate_amount=parsed_amount,
                        offset_minutes=offset_minutes,
                    )
                )
            elif entry_type == "recipe":
                recipe_rows = get_portion_detail_by_recipe(connection, entry_id)
                total_recipe_amount = sum(float(row.get("amount_g") or 0.0) for row in recipe_rows)
                if total_recipe_amount <= 0:
                    return render_fragment(P("Recipe has no ingredients to log.", cls="text-red-700"))
                factor = parsed_amount / total_recipe_amount
                for row in recipe_rows:
                    row_amount = float(row.get("amount_g") or 0.0) * factor
                    if row_amount <= 0:
                        continue
                    if row.get("catalog_id"):
                        created.append(
                            add_portion_detail(
                                connection,
                                origin="catalog",
                                origin_id=int(row["catalog_id"]),
                                destination="intake_event",
                                destination_id=event_id,
                                amount_g=row_amount,
                                cooking=row.get("cooking"),
                                conservation=row.get("conservation"),
                                final_state=row.get("final_state"),
                                strictly_weighed=True,
                                macros_quality=True,
                                plate_amount=row_amount,
                                is_cooked_weight=bool(row.get("is_cooked_weight")),
                                offset_minutes=offset_minutes,
                            )
                        )
                    elif row.get("manual_intake_id"):
                        created.append(
                            add_portion_detail(
                                connection,
                                origin="manual_intake",
                                origin_id=int(row["manual_intake_id"]),
                                destination="intake_event",
                                destination_id=event_id,
                                amount_g=row_amount,
                                cooking=row.get("cooking"),
                                conservation=row.get("conservation"),
                                final_state=row.get("final_state"),
                                strictly_weighed=True,
                                macros_quality=True,
                                plate_amount=row_amount,
                                is_cooked_weight=bool(row.get("is_cooked_weight")),
                                offset_minutes=offset_minutes,
                            )
                        )
            else:
                return render_fragment(P("Unsupported entry type.", cls="text-red-700"))

            ok = bool(created) and all(created)
            if ok:
                return HTMLResponse("", headers={"HX-Redirect": "/food"})
            return render_fragment(P("Could not log food.", cls="text-red-700"))

    @rt("/food/list")
    def get(
        request: Request,
        search: str = "",
        filter: str = "all",
        search_mode: str = "recommended",
        food_mode: str = "catalog",
        favs_mode: str = "catalog",
        recipes_mode: str = "mine",
        page: int = 1,
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        clean_search = (search or "").strip()
        page = max(1, int(page or 1))
        food_mode_norm = (food_mode or "catalog").strip().lower()
        if food_mode_norm not in ("catalog", "manual"):
            food_mode_norm = "catalog"
        favs_mode_norm = (favs_mode or "catalog").strip().lower()
        if favs_mode_norm not in ("catalog", "manual", "recipes"):
            favs_mode_norm = "catalog"
        recipes_mode_norm = (recipes_mode or "mine").strip().lower()
        if recipes_mode_norm not in ("mine", "discover"):
            recipes_mode_norm = "mine"
        with get_connection() as connection:
            if filter == "all":
                mode = (search_mode or "recommended").strip().lower()
                if mode == "global":
                    entries = _community_entries(connection, search=clean_search)
                else:
                    mode = "recommended"
                    entries = _recommended_entries(connection, search=clean_search, days=28)
            elif filter == "recipes":
                mode = (search_mode or "recommended").strip().lower()
                entries = _recipes_entries(connection, search=clean_search, recipes_mode=recipes_mode_norm)
            else:
                mode = (search_mode or "recommended").strip().lower()
                entries = _filtered_entries(connection, search=clean_search, filter_value=filter)
                if filter == "food":
                    desired_entry_type = "catalog" if food_mode_norm == "catalog" else "manual_intake"
                    entries = [item for item in entries if item.get("entry_type") == desired_entry_type]
                elif filter == "favs":
                    desired_entry_type = {
                        "catalog": "catalog",
                        "manual": "manual_intake",
                        "recipes": "recipe",
                    }[favs_mode_norm]
                    entries = [item for item in entries if item.get("entry_type") == desired_entry_type]

        if not entries:
            return render_fragment(H2("No items", cls="text-gray-600"))

        start = (page - 1) * LIST_PAGE_SIZE
        end = start + LIST_PAGE_SIZE
        chunk = entries[start:end]
        has_more = end < len(entries)

        if filter == "all" and mode == "recommended":
            nodes = [FoodCard(item) for item in chunk]
            if has_more:
                nodes.append(
                    _search_load_more_node(
                        clean_search,
                        filter,
                        mode,
                        food_mode_norm,
                        favs_mode_norm,
                        recipes_mode_norm,
                        page + 1,
                    )
                )
            return render_fragment(tuple(nodes))

        if filter == "all" and mode == "global":
            if page == 1:
                nodes = list(_community_sections_content(chunk))
            else:
                nodes = [FoodCard(item) for item in chunk]
            if has_more:
                nodes.append(
                    _search_load_more_node(
                        clean_search,
                        filter,
                        mode,
                        food_mode_norm,
                        favs_mode_norm,
                        recipes_mode_norm,
                        page + 1,
                    )
                )
            return render_fragment(tuple(nodes))

        if page == 1:
            nodes = list(FoodSectionsContent(chunk))
            if has_more:
                nodes.append(
                    _search_load_more_node(
                        clean_search,
                        filter,
                        mode,
                        food_mode_norm,
                        favs_mode_norm,
                        recipes_mode_norm,
                        page + 1,
                    )
                )
            return render_fragment(tuple(nodes))

        nodes = [FoodCard(item) for item in chunk]
        if has_more:
            nodes.append(
                _search_load_more_node(
                    clean_search,
                    filter,
                    mode,
                    food_mode_norm,
                    favs_mode_norm,
                    recipes_mode_norm,
                    page + 1,
                )
            )
        return render_fragment(tuple(nodes))

    @rt("/search_food")
    def get(request: Request, search: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            entries = _filtered_entries(connection, search=search, filter_value="all")
        if not entries:
            return render_fragment(H2("No items", cls="text-gray-600"))
        return render_fragment(tuple(FoodSectionsContent(entries)))

    @rt("/add_food/{food_id}")
    def post(request: Request, food_id: int, intake_event_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return HTMLResponse("No users", status_code=400)

            event_id = None
            if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                event_id = int(intake_event_id)
            else:
                event_id = add_intake_event(
                    connection,
                    users_id=user_id,
                    state="planned",
                )

            catalog_item = get_catalog_item(connection, food_id)
            if not catalog_item or not _can_view_entry("catalog", catalog_item, user_id):
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)
            portion_amount = 100
            if catalog_item.get("default_portion"):
                portion_amount = catalog_item["default_portion"]

            portion_id = None
            if event_id:
                event_data = get_intake_event(connection, event_id)
                offset_minutes = 0
                if event_data and event_data.get("meal_time"):
                    delta = datetime.now() - event_data["meal_time"]
                    offset_minutes = int(delta.total_seconds() // 60)

                portion_id = add_portion_detail(
                    connection,
                    origin="catalog",
                    origin_id=food_id,
                    destination="intake_event",
                    destination_id=event_id,
                    amount_g=portion_amount,
                    macros_quality=True,
                    offset_minutes=offset_minutes,
                )

            headers = {"HX-Trigger": "addSuccess" if portion_id else "addError"}
            return HTMLResponse("", headers=headers)

    @rt("/add_manual_intake/{intake_id}")
    def post(request: Request, intake_id: int, intake_event_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return HTMLResponse("No users", status_code=400)

            event_id = None
            if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                event_id = int(intake_event_id)
            else:
                event_id = add_intake_event(connection, users_id=user_id, state="planned")

            intake_item = get_manual_intake(connection, intake_id)
            if not intake_item or not _can_view_entry("manual_intake", intake_item, user_id):
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)

            portion_amount = float(intake_item.get("amount_g") or 100.0)
            event_data = get_intake_event(connection, event_id)
            offset_minutes = 0
            if event_data and event_data.get("meal_time"):
                delta = datetime.now() - event_data["meal_time"]
                offset_minutes = int(delta.total_seconds() // 60)

            portion_id = add_portion_detail(
                connection,
                origin="manual_intake",
                origin_id=intake_id,
                destination="intake_event",
                destination_id=event_id,
                amount_g=portion_amount,
                macros_quality=True,
                offset_minutes=offset_minutes,
            )
            headers = {"HX-Trigger": "addSuccess" if portion_id else "addError"}
            return HTMLResponse("", headers=headers)

    @rt("/add_recipe/{recipe_id}")
    def post(request: Request, recipe_id: int, intake_event_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return HTMLResponse("No users", status_code=400)

            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_view_entry("recipe", recipe, user_id):
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)

            if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                event_id = int(intake_event_id)
            else:
                event_id = add_intake_event(
                    connection,
                    users_id=user_id,
                    state="planned",
                    meal_type=recipe.get("meal_type"),
                    name=recipe.get("name"),
                )

            event_data = get_intake_event(connection, event_id)
            offset_minutes = 0
            if event_data and event_data.get("meal_time"):
                delta = datetime.now() - event_data["meal_time"]
                offset_minutes = int(delta.total_seconds() // 60)

            recipe_portions = get_portion_detail_by_recipe(connection, recipe_id)
            created_ids = []
            for row in recipe_portions:
                if row.get("catalog_id"):
                    created_ids.append(
                        add_portion_detail(
                            connection,
                            origin="catalog",
                            origin_id=int(row["catalog_id"]),
                            destination="intake_event",
                            destination_id=event_id,
                            amount_g=float(row.get("amount_g") or 0.0),
                            cooking=row.get("cooking"),
                            conservation=row.get("conservation"),
                            final_state=row.get("final_state"),
                            macros_quality=True,
                            plate_amount=row.get("plate_amount"),
                            is_cooked_weight=bool(row.get("is_cooked_weight")),
                            offset_minutes=offset_minutes,
                        )
                    )
                elif row.get("manual_intake_id"):
                    created_ids.append(
                        add_portion_detail(
                            connection,
                            origin="manual_intake",
                            origin_id=int(row["manual_intake_id"]),
                            destination="intake_event",
                            destination_id=event_id,
                            amount_g=float(row.get("amount_g") or 0.0),
                            cooking=row.get("cooking"),
                            conservation=row.get("conservation"),
                            final_state=row.get("final_state"),
                            macros_quality=True,
                            plate_amount=row.get("plate_amount"),
                            is_cooked_weight=bool(row.get("is_cooked_weight")),
                            offset_minutes=offset_minutes,
                        )
                    )

            ok = bool(recipe_portions) and all(created_ids)
            headers = {"HX-Trigger": "addSuccess" if ok else "addError"}
            return HTMLResponse("", headers=headers)

    @rt("/food/favorite/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            current = None
            updated = False
            if entry_type == "catalog":
                current = get_catalog_item(connection, entry_id)
                if current and _can_view_entry("catalog", current, user_id):
                    updated = update_catalog_favorite(connection, entry_id, not bool(current.get("favorite")))
                    current["favorite"] = not bool(current.get("favorite"))
            elif entry_type == "manual_intake":
                current = get_manual_intake(connection, entry_id)
                if current and _can_view_entry("manual_intake", current, user_id):
                    new_value = not bool(current.get("favorite"))
                    updated = update_manual_intake(connection, entry_id, {"favorite": new_value})
                    current["favorite"] = new_value
            elif entry_type == "recipe":
                current = get_recipe(connection, entry_id)
                if current and _can_view_entry("recipe", current, user_id):
                    new_value = not bool(current.get("favorite"))
                    updated = update_recipe(connection, entry_id, favorite=new_value)
                    current["favorite"] = new_value

            if not current or not updated:
                return HTMLResponse(status_code=400)

            return render_fragment(FavoriteButton(entry_type, entry_id, bool(current.get("favorite"))))

    @rt("/food/edit/catalog/{entry_id}")
    def post(
        request: Request,
        entry_id: int,
        name: str = "",
        brand: str = "",
        brand__added: str = "",
        category: str = "",
        category__added: str = "",
        subtype: str = "",
        subtype__added: str = "",
        initial_state: str = "",
        nutriscore: str = "",
        nova: str = "",
        yuka: str = "",
        default_portion: str = "",
        calories_100g: str = "",
        carbs_100g: str = "",
        sugars_100g: str = "",
        fats_100g: str = "",
        saturated_100g: str = "",
        proteins_100g: str = "",
        fiber_100g: str = "",
        caffeine: str = "",
        alcohol: str = "",
        barcode: str = "",
        cooking_factor: str = "",
        favorite: str = "",
        is_private: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name:
            return _error_msg("Name, category and subtype are required.")

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            current = get_catalog_item(connection, entry_id)
            if not current or not _can_view_entry("catalog", current, user_id):
                return _error_msg("Catalog item not found.")
            if not _can_edit_entry("catalog", current, user_id):
                return _error_msg("Only the owner can edit this item. Create a copy to edit it.")
            brand_options = get_food_brand_suggestions(connection, search="", limit=500)
            category_options = get_category_suggestions(connection, search="", limit=500)
            subtype_options = get_subtype_suggestions(connection, search="", limit=500)

            clean_brand, brand_error = _coerce_choice(
                brand,
                options=brand_options,
                allow_add=True,
                added=_to_bool(brand__added),
                required=False,
                label="Brand",
            )
            if brand_error:
                return _error_msg(brand_error)

            clean_category, category_error = _coerce_choice(
                category,
                options=category_options,
                allow_add=True,
                added=_to_bool(category__added),
                required=True,
                label="Category",
            )
            if category_error:
                return _error_msg(category_error)

            clean_subtype, subtype_error = _coerce_choice(
                subtype,
                options=subtype_options,
                allow_add=True,
                added=_to_bool(subtype__added),
                required=True,
                label="Subtype",
            )
            if subtype_error:
                return _error_msg(subtype_error)

            clean_initial_state, initial_state_error = _coerce_choice(
                initial_state,
                options=INITIAL_STATE_OPTIONS,
                allow_add=False,
                added=False,
                required=False,
                label="Initial state",
            )
            if initial_state_error:
                return _error_msg(initial_state_error)

            clean_nutriscore, nutriscore_error = _coerce_choice(
                nutriscore,
                options=["A", "B", "C", "D", "E"],
                allow_add=False,
                added=False,
                required=False,
                label="Nutriscore",
            )
            if nutriscore_error:
                return _error_msg(nutriscore_error)

            existing = get_all_catalog(connection, search=clean_name)
            duplicated = any(
                ((item.get("name") or "").strip().lower() == clean_name.lower()) and int(item.get("id") or 0) != entry_id
                for item in existing
            )
            if duplicated:
                return _error_msg("A catalog item with that name already exists.")

            normalized_brand = normalize_brand_name(clean_brand or "")
            favorite_value = None if (favorite or "").strip() == "" else _to_bool(favorite)
            can_toggle_private = _can_toggle_private("catalog", current, user_id)
            payload = {
                "name": clean_name,
                "brand": normalized_brand or None,
                "category": clean_category,
                "subtype": clean_subtype,
                "initial_state": clean_initial_state,
                "nutriscore": clean_nutriscore,
                "nova": _to_int(nova),
                "yuka": _to_int(yuka),
                "default_portion": _to_float(default_portion),
                "calories_100g": _to_float(calories_100g),
                "carbs_100g": _to_float(carbs_100g),
                "sugars_100g": _to_float(sugars_100g),
                "fats_100g": _to_float(fats_100g),
                "saturated_100g": _to_float(saturated_100g),
                "proteins_100g": _to_float(proteins_100g),
                "fiber_100g": _to_float(fiber_100g),
                "caffeine": _to_float(caffeine),
                "alcohol": _to_float(alcohol),
                "barcode": barcode.strip() or None,
                "cooking_factor": _to_float(cooking_factor),
                "favorite": favorite_value,
            }
            if can_toggle_private:
                payload["is_private"] = _to_bool(is_private)
            updated = update_catalog_item(connection, entry_id, payload)
            if not updated:
                return _error_msg("Catalog item could not be updated.")
            if normalized_brand:
                add_food_brand(connection, normalized_brand)
            return HTMLResponse("", headers={"HX-Redirect": f"/food/item/catalog/{entry_id}"})

    @rt("/food/edit/manual/{entry_id}")
    def post(
        request: Request,
        entry_id: int,
        name: str = "",
        description: str = "",
        subtype: str = "",
        subtype__added: str = "",
        source_origin: str = "",
        source_origin__added: str = "",
        amount_g: str = "",
        calories_100g: str = "",
        carbs_100g: str = "",
        sugars_100g: str = "",
        fats_100g: str = "",
        saturated_100g: str = "",
        proteins_100g: str = "",
        fiber_100g: str = "",
        caffeine: str = "",
        alcohol: str = "",
        glycemic_index: str = "",
        ig_confidence: str = "",
        favorite: str = "",
        is_private: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name or not amount_g:
            return _error_msg("Name, subtype and amount are required.")

        try:
            amount_value = float(amount_g)
            if amount_value <= 0:
                return _error_msg("Amount must be greater than zero.")
        except (TypeError, ValueError):
            return _error_msg("Amount must be numeric.")

        with get_connection() as connection:
            current = get_manual_intake(connection, entry_id)
            user_id = get_default_user_id(connection)
            if not current or not _can_view_entry("manual_intake", current, user_id):
                return _error_msg("Manual intake not found.")
            if not _can_edit_entry("manual_intake", current, user_id):
                return _error_msg("Only the owner can edit this item. Create a copy to edit it.")
            subtype_options = get_subtype_suggestions(connection, search="", limit=500)
            origin_options = get_manual_origin_suggestions(connection, search="", limit=500)

            clean_subtype, subtype_error = _coerce_choice(
                subtype,
                options=subtype_options,
                allow_add=True,
                added=_to_bool(subtype__added),
                required=True,
                label="Subtype",
            )
            if subtype_error:
                return _error_msg(subtype_error)

            clean_origin, origin_error = _coerce_choice(
                source_origin,
                options=origin_options,
                allow_add=True,
                added=_to_bool(source_origin__added),
                required=False,
                label="Origin",
            )
            if origin_error:
                return _error_msg(origin_error)

            clean_glycemic, glycemic_error = _coerce_choice(
                glycemic_index,
                options=GLYCEMIC_INDEX_OPTIONS,
                allow_add=False,
                added=False,
                required=False,
                label="Glycemic index",
            )
            if glycemic_error:
                return _error_msg(glycemic_error)

            existing = get_all_manual_intakes(connection, users_id=user_id, search=clean_name)
            duplicated = any(
                ((item.get("name") or "").strip().lower() == clean_name.lower()) and int(item.get("id") or 0) != entry_id
                for item in existing
            )
            if duplicated:
                return _error_msg("A manual intake with that name already exists for this user.")

            can_toggle_private = _can_toggle_private("manual_intake", current, user_id)
            payload = {
                "name": clean_name,
                "description": description.strip() or None,
                "subtype": clean_subtype,
                "origin": clean_origin,
                "amount_g": amount_value,
                "calories_100g": _to_float(calories_100g),
                "carbs_100g": _to_float(carbs_100g),
                "sugars_100g": _to_float(sugars_100g),
                "fats_100g": _to_float(fats_100g),
                "saturated_100g": _to_float(saturated_100g),
                "proteins_100g": _to_float(proteins_100g),
                "fiber_100g": _to_float(fiber_100g),
                "caffeine": _to_float(caffeine),
                "alcohol": _to_float(alcohol),
                "glycemic_index": clean_glycemic,
                "ig_confidence": _to_int(ig_confidence),
                "favorite": (None if (favorite or "").strip() == "" else _to_bool(favorite)),
            }
            if can_toggle_private:
                payload["is_private"] = _to_bool(is_private)
            updated = update_manual_intake(connection, entry_id, payload)
            if not updated:
                return _error_msg("Manual intake could not be updated.")
            return HTMLResponse("", headers={"HX-Redirect": f"/food/item/manual_intake/{entry_id}"})

    @rt("/food/edit/recipe/{entry_id}")
    def post(
        request: Request,
        entry_id: int,
        name: str = "",
        meal_type: str = "",
        notes: str = "",
        favorite: str = "",
        is_private: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name:
            return _error_msg("Recipe name is required.")
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            current = get_recipe(connection, entry_id)
            if not current or not _can_view_entry("recipe", current, user_id):
                return _error_msg("Recipe not found.")
            if not _can_edit_entry("recipe", current, user_id):
                return _error_msg("Only the owner can edit this item. Create a copy to edit it.")
            clean_meal_type, meal_type_error = _coerce_choice(
                meal_type,
                options=MEAL_TYPES,
                allow_add=False,
                added=False,
                required=False,
                label="Meal type",
            )
            if meal_type_error:
                return _error_msg(meal_type_error)
            can_toggle_private = _can_toggle_private("recipe", current, user_id)
            updated = update_recipe(
                connection,
                entry_id,
                name=clean_name,
                meal_type=clean_meal_type,
                notes=notes.strip() or None,
                favorite=(None if (favorite or "").strip() == "" else _to_bool(favorite)),
                is_private=_to_bool(is_private) if can_toggle_private else None,
            )
            if not updated:
                return _error_msg("Recipe could not be updated.")
            return HTMLResponse("", headers={"HX-Redirect": f"/food/item/recipe/{entry_id}"})

    @rt("/food/create/catalog")
    def post(
        request: Request,
        name: str = "",
        brand: str = "",
        brand__added: str = "",
        category: str = "",
        category__added: str = "",
        subtype: str = "",
        subtype__added: str = "",
        initial_state: str = "",
        nutriscore: str = "",
        nova: str = "",
        yuka: str = "",
        default_portion: str = "",
        calories_100g: str = "",
        carbs_100g: str = "",
        sugars_100g: str = "",
        fats_100g: str = "",
        saturated_100g: str = "",
        proteins_100g: str = "",
        fiber_100g: str = "",
        caffeine: str = "",
        alcohol: str = "",
        barcode: str = "",
        cooking_factor: str = "",
        favorite: str = "",
        is_private: str = "",
        catalog_smart_macros_enabled: str = "",
        catalog_smart_macros_raw: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        clean_category = (category or "").strip()
        clean_subtype = (subtype or "").strip()
        if not clean_name or not clean_category or not clean_subtype:
            return _error_msg("Name, category and subtype are required.")

        with get_connection() as connection:
            brand_options = get_food_brand_suggestions(connection, search="", limit=500)
            category_options = get_category_suggestions(connection, search="", limit=500)
            subtype_options = get_subtype_suggestions(connection, search="", limit=500)

            clean_brand, brand_error = _coerce_choice(
                brand,
                options=brand_options,
                allow_add=True,
                added=_to_bool(brand__added),
                required=False,
                label="Brand",
            )
            if brand_error:
                return _error_msg(brand_error)

            clean_category, category_error = _coerce_choice(
                category,
                options=category_options,
                allow_add=True,
                added=_to_bool(category__added),
                required=True,
                label="Category",
            )
            if category_error:
                return _error_msg(category_error)

            clean_subtype, subtype_error = _coerce_choice(
                subtype,
                options=subtype_options,
                allow_add=True,
                added=_to_bool(subtype__added),
                required=True,
                label="Subtype",
            )
            if subtype_error:
                return _error_msg(subtype_error)

            clean_initial_state, initial_state_error = _coerce_choice(
                initial_state,
                options=INITIAL_STATE_OPTIONS,
                allow_add=False,
                added=False,
                required=False,
                label="Initial state",
            )
            if initial_state_error:
                return _error_msg(initial_state_error)

            clean_nutriscore, nutriscore_error = _coerce_choice(
                nutriscore,
                options=["A", "B", "C", "D", "E"],
                allow_add=False,
                added=False,
                required=False,
                label="Nutriscore",
            )
            if nutriscore_error:
                return _error_msg(nutriscore_error)

            existing = get_all_catalog(connection, search=clean_name)
            if any(((item.get("name") or "").strip().lower() == clean_name.lower()) for item in existing):
                return _error_msg("A catalog item with that name already exists.")

            user_id = get_default_user_id(connection)
            if not user_id:
                return _error_msg("No users found.")
            normalized_brand = normalize_brand_name(clean_brand or "")
            payload = {
                "created_by": user_id,
                "name": clean_name,
                "brand": normalized_brand or None,
                "category": clean_category,
                "subtype": clean_subtype,
                "initial_state": clean_initial_state,
                "nutriscore": clean_nutriscore,
                "nova": _to_int(nova),
                "yuka": _to_int(yuka),
                "default_portion": _to_float(default_portion),
                "calories_100g": _smart_macro_float(catalog_smart_macros_enabled, catalog_smart_macros_raw, calories_100g),
                "carbs_100g": _smart_macro_float(catalog_smart_macros_enabled, catalog_smart_macros_raw, carbs_100g),
                "sugars_100g": _smart_macro_float(catalog_smart_macros_enabled, catalog_smart_macros_raw, sugars_100g),
                "fats_100g": _smart_macro_float(catalog_smart_macros_enabled, catalog_smart_macros_raw, fats_100g),
                "saturated_100g": _smart_macro_float(catalog_smart_macros_enabled, catalog_smart_macros_raw, saturated_100g),
                "proteins_100g": _smart_macro_float(catalog_smart_macros_enabled, catalog_smart_macros_raw, proteins_100g),
                "fiber_100g": _smart_macro_float(catalog_smart_macros_enabled, catalog_smart_macros_raw, fiber_100g),
                "caffeine": _to_float(caffeine),
                "alcohol": _to_float(alcohol),
                "barcode": barcode.strip() or None,
                "cooking_factor": _to_float(cooking_factor),
                "favorite": _to_bool(favorite),
                "is_private": _to_bool(is_private),
            }
            created_id = add_catalog_item(connection, payload)
            if not created_id:
                return _error_msg("Catalog item could not be created. Check required fields and uniqueness constraints.")
            if normalized_brand:
                add_food_brand(connection, normalized_brand)
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/create/manual")
    def post(
        request: Request,
        name: str = "",
        description: str = "",
        subtype: str = "",
        subtype__added: str = "",
        source_origin: str = "",
        source_origin__added: str = "",
        amount_g: str = "",
        calories_100g: str = "",
        carbs_100g: str = "",
        sugars_100g: str = "",
        fats_100g: str = "",
        saturated_100g: str = "",
        proteins_100g: str = "",
        fiber_100g: str = "",
        caffeine: str = "",
        alcohol: str = "",
        glycemic_index: str = "",
        ig_confidence: str = "",
        favorite: str = "",
        is_private: str = "",
        manual_smart_macros_enabled: str = "",
        manual_smart_macros_raw: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name or not amount_g:
            return _error_msg("Name, subtype and amount are required.")

        try:
            amount_value = float(amount_g)
            if amount_value <= 0:
                return _error_msg("Amount must be greater than zero.")
        except (TypeError, ValueError):
            return _error_msg("Amount must be numeric.")

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return _error_msg("No users found.")
            subtype_options = get_subtype_suggestions(connection, search="", limit=500)
            origin_options = get_manual_origin_suggestions(connection, search="", limit=500)

            clean_subtype, subtype_error = _coerce_choice(
                subtype,
                options=subtype_options,
                allow_add=True,
                added=_to_bool(subtype__added),
                required=True,
                label="Subtype",
            )
            if subtype_error:
                return _error_msg(subtype_error)

            clean_origin, origin_error = _coerce_choice(
                source_origin,
                options=origin_options,
                allow_add=True,
                added=_to_bool(source_origin__added),
                required=False,
                label="Origin",
            )
            if origin_error:
                return _error_msg(origin_error)

            clean_glycemic, glycemic_error = _coerce_choice(
                glycemic_index,
                options=GLYCEMIC_INDEX_OPTIONS,
                allow_add=False,
                added=False,
                required=False,
                label="Glycemic index",
            )
            if glycemic_error:
                return _error_msg(glycemic_error)

            existing = get_all_manual_intakes(connection, users_id=user_id, search=clean_name)
            if any(((item.get("name") or "").strip().lower() == clean_name.lower()) for item in existing):
                return _error_msg("A manual intake with that name already exists for this user.")

            payload = {
                "created_by": user_id,
                "name": clean_name,
                "description": description.strip() or None,
                "subtype": clean_subtype,
                "origin": clean_origin,
                "amount_g": amount_value,
                "calories_100g": _smart_macro_float(manual_smart_macros_enabled, manual_smart_macros_raw, calories_100g),
                "carbs_100g": _smart_macro_float(manual_smart_macros_enabled, manual_smart_macros_raw, carbs_100g),
                "sugars_100g": _smart_macro_float(manual_smart_macros_enabled, manual_smart_macros_raw, sugars_100g),
                "fats_100g": _smart_macro_float(manual_smart_macros_enabled, manual_smart_macros_raw, fats_100g),
                "saturated_100g": _smart_macro_float(manual_smart_macros_enabled, manual_smart_macros_raw, saturated_100g),
                "proteins_100g": _smart_macro_float(manual_smart_macros_enabled, manual_smart_macros_raw, proteins_100g),
                "fiber_100g": _smart_macro_float(manual_smart_macros_enabled, manual_smart_macros_raw, fiber_100g),
                "caffeine": _to_float(caffeine),
                "alcohol": _to_float(alcohol),
                "glycemic_index": clean_glycemic,
                "ig_confidence": _to_int(ig_confidence),
                "favorite": _to_bool(favorite),
                "is_private": _to_bool(is_private),
            }
            created_id = add_manual_intake(connection, payload)
            if not created_id:
                return _error_msg("Manual intake could not be created. Check required fields and constraints.")
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/create/recipe")
    def post(
        request: Request,
        name: str = "",
        meal_type: str = "",
        notes: str = "",
        favorite: str = "",
        is_private: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name:
            return _error_msg("Recipe name is required.")

        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return _error_msg("No users found.")
            clean_meal_type, meal_type_error = _coerce_choice(
                meal_type,
                options=MEAL_TYPES,
                allow_add=False,
                added=False,
                required=False,
                label="Meal type",
            )
            if meal_type_error:
                return _error_msg(meal_type_error)
            created_id = add_recipe(
                connection,
                users_id=user_id,
                name=clean_name,
                meal_type=clean_meal_type,
                notes=notes.strip() or None,
                favorite=_to_bool(favorite),
                is_private=_to_bool(is_private),
            )
            if not created_id:
                return _error_msg("Recipe could not be created. Check required fields and constraints.")
            return HTMLResponse("", headers={"HX-Redirect": f"/food/item/recipe/{created_id}"})
    
    @rt("/meal_selector_input")
    def get(request: Request, intake_event_id: str):
        if intake_event_id != "0":
            return render_fragment("")
        
        return render_fragment(Div(
            Input(
                placeholder="Meal name",
                name="meal_name",
                id="meal_name_input_text",
                autofocus="autofocus",
                data_skip_page_loading="true",
                cls="""
                border-[1px] px-2 py-1
                md:text-sm lg:text-sm text-base
                shadow-sm rounded-md focus:outline-none
                border-gray-300 w-full
                """,
                hx_post="/create_named_event",
                hx_trigger="keyup[keyCode==13]",
                hx_target="#meal_name_input",
                hx_swap="none",
                hx_push_url="false",
                hx_include="this",
                **on_after("add_meal_btn")
            ),
            Button(
                "Add",
                id="add_meal_btn",
                data_skip_page_loading="true",
                cls="""
                border-[1px] px-2 py-1
                md:text-sm lg:text-sm text-xs
                shadow-sm rounded-md cursor-pointer
                border-gray-300 hover:bg-gray-200
                transition-colors duration-300
                """,
                hx_post="/create_named_event",
                hx_target="#meal_name_input",
                hx_swap="none",
                hx_push_url="false",
                hx_include="#meal_name_input_text",
                **on_after()
            ),
            cls="flex gap-2 w-full"        
            ))

    @rt("/create_named_event")
    def post(request: Request, meal_name: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        
        with get_connection() as connection:
            user_id = get_default_user_id(connection)
            if not user_id:
                return HTMLResponse("No users", status_code=400)

            event_id = add_intake_event(
                connection,
                users_id=user_id,
                state="planned",
                name=meal_name or None,
            )

            headers = {"HX-Trigger": "addSuccess" if event_id else "addError"}
            return HTMLResponse("", headers=headers)
