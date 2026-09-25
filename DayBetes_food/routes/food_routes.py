from fasthtml.common import *
from datetime import datetime
from datetime import date
import json
import difflib
import logging
import math
import re
import unicodedata
from urllib.parse import urlencode
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.food.food_main import food_main, plate_selector_options
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.http_errors import app_error_response, request_id
from DayBetes_food.database.queries import (
    create_catalog_item,
    list_catalog_items,
    archive_catalog_item,
    publish_catalog_item,
    unpublish_catalog_item,
    next_catalog_copy_name,
    get_all_manual_intakes,
    get_all_recipes,
    create_portion_detail,
    get_catalog_item,
    get_catalog_item_by_barcode,
    get_manual_intake,
    get_recipe,
    get_portion_detail,
    list_recipe_portions_by_origin,
    list_viewable_recipe_portions,
    list_portions_by_recipe,
    update_catalog_item,
    toggle_user_favorite,
    set_user_favorite,
    update_manual_intake,
    update_recipe,
    delete_manual_intake,
    delete_recipe,
    add_manual_intake,
    add_recipe,
    create_food_brand,
    get_food_brand_id_by_label,
    get_food_brand_suggestions,
    get_subtype_suggestions,
    get_subtype_label,
    get_manual_origin_suggestions,
    get_tag_suggestions,
    get_entry_tags,
    set_entry_tags,
    manual_intake_name_origin_exists,
    get_consumed_food_usage_rankings,
    get_rescue_entries_suggestions,
    update_portion_amount,
    update_portion_detail_fields,
    delete_portion_detail,
    create_intake_event,
    get_intake_event,
    get_planned_intake_event,
    list_planned_intake_events,
    get_meal_type_schedule,
    create_intake_plate,
    ensure_default_plate,
    get_intake_plate,
)
from DayBetes_food.components.food.foods import GLYCEMIC_INDEX_OPTIONS
from DayBetes_food.domain.constants import (
    CLEAR,
    NOVA_MAX,
    NOVA_MIN,
    YUKA_MAX,
    YUKA_MIN,
    AmountInputUnit,
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodPhysicalState,
    Nutriscore,
    PortionDestination,
    PortionOrigin,
    parse_enum,
)
from DayBetes_food.domain.nutrition import (
    NutrientValues,
    NumericRange,
    nutrients_from_smart_text,
    parse_number,
    parse_nutrients,
)
from DayBetes_food.domain.catalog import (
    INITIAL_AMOUNT_WITHOUT_SERVING_G,
    CatalogItemCreate,
    CatalogItemRequest,
    CatalogItemUpdate,
    parse_barcode,
    parse_catalog_name,
    parse_catalog_subtype,
    parse_cooking_factor,
    parse_default_portion,
)
from DayBetes_food.domain.portion_detail import (
    PortionDetailCreate,
    PortionDetailUpdate,
    amount_to_grams,
    parse_amount_grams,
)
from DayBetes_food.integrations.open_food_facts import fetch_product_prefill
from DayBetes_food.components.food.foods import FoodSectionsContent, FoodCard, FavoriteButton, on_after
from DayBetes_food.components.food.foods import catalog_entry_view
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
    PlateSelector,
)
from DayBetes_food.database.connection import get_connection
from DayBetes_food.domain.constants import IntakeEventState, MealType
from DayBetes_food.domain.intake_event import INTAKE_EVENT_NAME_MAX_LENGTH, IntakeEventCreate
from DayBetes_food.domain.intake_plate import IntakePlateCreate
from DayBetes_food.domain.meal_type_schedule import resolve_meal_type_for_time
from DayBetes_food.time_utils import local_naive_to_utc_aware, local_now, local_today, utc_now
from DayBetes_food.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    InfrastructureError,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)


def _default_meal_type_now(connection, user_id: int) -> MealType | None:
    """
    `meal_type` automático para un `intake_event` creado sin pasar por el
    carrito (añadir un alimento directo), a partir de la hora local actual y
    de las franjas horarias del usuario (o los defaults si no las ha
    personalizado en /settings/meal_type_schedule).

    Se calcula aquí, en el momento de crear la fila, y no en el componente
    que la muestra: el `<select>` de `EventHeader` (cart_components.py) debe
    poder confiar en que `event.meal_type` ya es el valor real, nunca uno que
    tenga que inferir en el render (code_conventions.md §7.14, decisión
    2026-09-11).
    """
    overrides = get_meal_type_schedule(connection, user_id)
    return resolve_meal_type_for_time(local_now().time(), overrides)


def _event_auto_offset_minutes(event_data) -> int:
    """Offset autocalculado de una tanda nueva (measurement_conventions.md §4.5).

    Diferencia en minutos entre el `meal_time` del evento y este instante. Es
    el valor con el que nace la tanda; a partir de ahí lo heredan sus
    porciones, que es lo que evita corregirlo ingrediente a ingrediente
    (§4.6.2).
    """
    if not event_data or not event_data.meal_time:
        return 0
    delta = utc_now() - event_data.meal_time
    return int(delta.total_seconds() // 60)


def _resolve_event_plate(connection, user_id: int, event_id: int, plate_id: str, offset_minutes: int) -> int:
    """Tanda a la que va un alimento que se añade a un evento (§4.6.1, §7.7).

    - Un id concreto: esa tanda, validando dentro del SQL que es del usuario y
      del evento (§5.3); el `event_id` de la petición no basta como prueba.
    - `"0"`: la opción `+ New plate` del selector, que crea la tanda en el acto.
    - Vacío o ausente: la última tanda del evento y, si no hay ninguna, la
      primera creada implícitamente.

    Raises:
        NotFoundError: la tanda no existe, no es del usuario o es de otro evento.
    """
    raw = (plate_id or "").strip()
    if raw.isdigit() and int(raw) != 0:
        plate = get_intake_plate(connection, user_id, int(raw))
        if plate.intake_event_id != int(event_id):
            raise NotFoundError(f"Intake plate {raw} does not belong to event {event_id}")
        return plate.id
    if raw == "0":
        return create_intake_plate(
            connection,
            IntakePlateCreate(intake_event_id=int(event_id), offset_minutes=offset_minutes),
            commit=False,
        )
    return ensure_default_plate(
        connection, int(event_id), offset_minutes=offset_minutes, commit=False
    )


# Half of the last decimal the food page shows for the plated grams
# (food_detail.js formats it with one decimal): the widest gap between the
# typed value and the real total that is only display rounding.
_PLATE_DISPLAY_TOLERANCE_G = 0.05


def _to_float(value: str):
    normalized = (value or "").strip().replace(",", ".")
    if not normalized:
        return None
    try:
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _parse_strict_bool(raw_value: str) -> bool:
    """Strict parser for HTML transport booleans (§7.6).

    True = {"true", "1"} (checkboxes send "true"; the autocomplete `__added`
    flags send "1"); False = {"", "false", "0"}; any other value is rejected
    with ValidationError instead of silently becoming False.
    """
    normalized = (raw_value or "").strip().lower()
    if normalized in ("true", "1"):
        return True
    if normalized in ("", "false", "0"):
        return False
    raise ValidationError("Unrecognized checkbox value.")


MANUAL_AMOUNT_LIMITS = (0.0, 5000.0)

_NOVA_RANGE = NumericRange(NOVA_MIN, NOVA_MAX)
_YUKA_RANGE = NumericRange(YUKA_MIN, YUKA_MAX)


def _strict_float(value, label: str, minimum: float = None, maximum: float = None):
    text = "" if value is None else str(value).strip().replace(",", ".")
    if not text:
        return None, None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None, f"{label} must be numeric."
    if not math.isfinite(parsed):
        return None, f"{label} must be a finite number."
    if minimum is not None and parsed < minimum:
        return None, f"{label} must be greater than or equal to {minimum:g}."
    if maximum is not None and parsed > maximum:
        return None, f"{label} must be less than or equal to {maximum:g}."
    return parsed, None


def _strict_int(value, label: str, minimum: int = None, maximum: int = None):
    text = "" if value is None else str(value).strip()
    if not text:
        return None, None
    try:
        parsed = int(text)
    except (TypeError, ValueError):
        return None, f"{label} must be an integer."
    if minimum is not None and parsed < minimum:
        return None, f"{label} must be between {minimum} and {maximum}."
    if maximum is not None and parsed > maximum:
        return None, f"{label} must be between {minimum} and {maximum}."
    return parsed, None


def _parse_manual_nutrients(values: dict, ig_confidence):
    """Parse the nine shared nutrient limits plus the manual_intake IG fields.

    Returns (clean_dict, None) or (None, error_message). `clean_dict` keeps the
    old shape (nine nutrient keys + ig_confidence) so the manual payloads stay
    unchanged, but the values come from the shared parser (decision 2026-09-25).
    """
    try:
        nutrients = parse_nutrients(values)
    except ValidationError as exc:
        return None, str(exc)
    ig, ig_error = _strict_int(ig_confidence, "IG confidence", 1, 5)
    if ig_error:
        return None, ig_error
    clean = {
        "calories_100g": nutrients.calories_100g,
        "carbs_100g": nutrients.carbs_100g,
        "sugars_100g": nutrients.sugars_100g,
        "fats_100g": nutrients.fats_100g,
        "saturated_100g": nutrients.saturated_100g,
        "proteins_100g": nutrients.proteins_100g,
        "fiber_100g": nutrients.fiber_100g,
        "caffeine": nutrients.caffeine,
        "alcohol": nutrients.alcohol,
        "ig_confidence": ig,
    }
    return clean, None


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


def _parse_hhmm(value: str):
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError:
        return None


def _to_str_or_none(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_catalog_item_request(
    *,
    nutrients_source: str,
    name,
    brand,
    brand__added,
    category,
    subtype,
    subtype__added,
    initial_state,
    nutriscore,
    nova,
    yuka,
    default_portion,
    caffeine,
    alcohol,
    barcode,
    cooking_factor,
    favorite=None,
    tags_json=None,
    smart_raw="",
    **visible_nutrients,
) -> CatalogItemRequest:
    """The only parser of catalog create and edit (H21, §7.1).

    `nutrients_source="smart"` parses `smart_raw` and ignores the hidden fields
    (§7.13, H16); `"fields"` parses the visible numeric fields.
    """
    parsed_name = parse_catalog_name(name)
    brand_label = _to_str_or_none(brand)
    brand_is_new = _parse_strict_bool(brand__added)
    parsed_category = parse_enum(FoodCategory, category, field="category")
    if parsed_category is None:
        raise ValidationError("Category is required.", fields={"category": "required"})
    parsed_subtype = parse_catalog_subtype(subtype)
    subtype_is_new = _parse_strict_bool(subtype__added)
    parsed_initial_state = parse_enum(FoodPhysicalState, initial_state, field="initial_state")
    parsed_nutriscore = parse_enum(
        Nutriscore, nutriscore, field="nutriscore", normalize=str.upper
    )
    parsed_nova = parse_number(nova, "nova", _NOVA_RANGE, integer=True)
    parsed_yuka = parse_number(yuka, "yuka", _YUKA_RANGE, integer=True)
    parsed_default_portion = parse_default_portion(default_portion)
    parsed_cooking_factor = parse_cooking_factor(cooking_factor)
    if nutrients_source == "smart":
        nutrients = nutrients_from_smart_text(smart_raw, caffeine, alcohol)
    else:
        fields = dict(visible_nutrients)
        fields["caffeine"] = caffeine
        fields["alcohol"] = alcohol
        nutrients = parse_nutrients(fields)
    parsed_barcode = parse_barcode(barcode)
    parsed_favorite = None if favorite is None else _parse_strict_bool(favorite)
    tags = _parse_tags_json(tags_json) if tags_json is not None else None
    return CatalogItemRequest(
        name=parsed_name,
        brand_label=brand_label,
        brand_is_new=brand_is_new,
        category=parsed_category,
        subtype=parsed_subtype,
        subtype_is_new=subtype_is_new,
        initial_state=parsed_initial_state,
        nutriscore=parsed_nutriscore,
        nova=parsed_nova,
        yuka=parsed_yuka,
        default_portion=parsed_default_portion,
        nutrients=nutrients,
        barcode=parsed_barcode,
        cooking_factor=parsed_cooking_factor,
        favorite=parsed_favorite,
        tags=tags,
    )


def _resolve_catalog_refs(connection, user_id: int, req: CatalogItemRequest):
    """Resolve brand and subtype inside the transaction (brand_id, subtype).

    Validation is by existence in SQL, without the autocomplete's 500-row cap
    (H25). A failure rolls back any brand created in this same transaction.
    """
    brand_id = None
    if req.brand_label:
        brand_id = get_food_brand_id_by_label(connection, req.brand_label)
        if brand_id is None:
            if req.brand_is_new:
                brand_id = create_food_brand(connection, req.brand_label, commit=False)
            else:
                raise ValidationError(
                    "Invalid brand. Use Add to create a new value.",
                    fields={"brand": "invalid"},
                )
    stored_subtype = get_subtype_label(connection, req.subtype)
    if stored_subtype is None:
        if req.subtype_is_new:
            stored_subtype = req.subtype
        else:
            raise ValidationError(
                "Invalid subtype. Use Add to create a new value.",
                fields={"subtype": "invalid"},
            )
    return brand_id, stored_subtype


def _catalog_create(req: CatalogItemRequest, user_id: int, brand_id, subtype) -> CatalogItemCreate:
    return CatalogItemCreate(
        created_by=user_id,
        origin_root_id=None,
        name=req.name,
        brand_id=brand_id,
        category=req.category,
        subtype=subtype,
        initial_state=req.initial_state,
        nutriscore=req.nutriscore,
        nova=req.nova,
        yuka=req.yuka,
        default_portion=req.default_portion,
        nutrients=req.nutrients,
        barcode=req.barcode,
        cooking_factor=req.cooking_factor,
    )


def _catalog_update(req: CatalogItemRequest, brand_id, subtype) -> CatalogItemUpdate:
    return CatalogItemUpdate(
        name=req.name,
        brand_id=brand_id,
        category=req.category,
        subtype=subtype,
        initial_state=req.initial_state,
        nutriscore=req.nutriscore,
        nova=req.nova,
        yuka=req.yuka,
        default_portion=req.default_portion,
        nutrients=req.nutrients,
        barcode=req.barcode,
        cooking_factor=req.cooking_factor,
    )


def _prefill_view(prefill, barcode: str) -> dict:
    """OffProductPrefill -> presentation dict of the create form."""
    nutrients = prefill.nutrients

    def text_or_empty(value):
        return "" if value is None else value

    return {
        "barcode": barcode,
        "name": prefill.name or "",
        "brand": prefill.brand or "",
        "category": prefill.category.value if prefill.category else "",
        "subtype": prefill.subtype or "",
        "default_portion": text_or_empty(prefill.default_portion_g),
        "initial_state": prefill.initial_state.value if prefill.initial_state else "",
        "nutriscore": prefill.nutriscore.value if prefill.nutriscore else "",
        "nova": text_or_empty(prefill.nova),
        "calories_100g": text_or_empty(nutrients.calories_100g),
        "carbs_100g": text_or_empty(nutrients.carbs_100g),
        "sugars_100g": text_or_empty(nutrients.sugars_100g),
        "fats_100g": text_or_empty(nutrients.fats_100g),
        "saturated_100g": text_or_empty(nutrients.saturated_100g),
        "proteins_100g": text_or_empty(nutrients.proteins_100g),
        "fiber_100g": text_or_empty(nutrients.fiber_100g),
        "caffeine": text_or_empty(nutrients.caffeine),
        "alcohol": text_or_empty(nutrients.alcohol),
        "alcohol_source_note": prefill.alcohol_source_note,
    }


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


def _parse_tags_json(raw: str) -> list[str]:
    """Parse the tags field. Empty clears the tags; malformed JSON is a 422 (§7.2)."""
    text = (raw or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except ValueError:
        raise ValidationError("Invalid tags.", fields={"tags_json": "invalid"})
    if not isinstance(payload, list):
        raise ValidationError("Invalid tags.", fields={"tags_json": "invalid"})
    tags = []
    seen = set()
    for item in payload:
        tag = " ".join(str(item or "").strip().split())
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            tags.append(tag)
    return tags


def _macro_value(portion, macro_key: str):
    return getattr(portion.source, f"{macro_key}_100g", None)


def _catalog_detail_summary(item) -> dict:
    """Presentation summary of a CatalogItemRead (H15, H23).

    `default_amount_g` may be None (no serving). `per100` keeps None. `info_rows`
    shows 0 as 0 (f"{v:g}") and omits a row whose value is None."""
    def fmt(value):
        if isinstance(value, float):
            return f"{value:g}"
        return str(value)

    per100 = {
        "calories_100g": item.calories_100g,
        "carbs_100g": item.carbs_100g,
        "sugars_100g": item.sugars_100g,
        "fats_100g": item.fats_100g,
        "saturated_100g": item.saturated_100g,
        "proteins_100g": item.proteins_100g,
        "fiber_100g": item.fiber_100g,
    }
    candidates = [
        ("Category", item.category.value),
        ("Subtype", item.subtype),
        ("Initial state", item.initial_state.value if item.initial_state else None),
        ("Nutriscore", item.nutriscore.value if item.nutriscore else None),
        ("NOVA", item.nova),
        ("Yuka", item.yuka),
        ("Caffeine", item.caffeine),
        ("Alcohol", item.alcohol),
        ("Barcode", item.barcode),
        ("Cooking factor", item.cooking_factor),
    ]
    info_rows = [(label, fmt(value)) for label, value in candidates if value is not None]
    return {
        "subtitle": item.brand or "No brand",
        "default_amount_g": item.default_portion,
        "per100": per100,
        "info_rows": info_rows,
    }


def _build_detail_summary(entry_type: str, entry: dict, recipe_portions: list | None = None) -> dict:
    if entry_type == "catalog":
        return _catalog_detail_summary(entry)

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
    total_amount = sum(float(row.amount or 0.0) for row in portions)
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
        amount = float(row.amount or 0.0)
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
            item.get("entry_type") or "",
            int(item.get("id") or 0),
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
    viewer_user_id = get_current_user_id()
    search_value = (search or "").strip() or None

    catalog_items = (
        [
            catalog_entry_view(item)
            for item in list_catalog_items(connection, int(viewer_user_id), search=search_value)
        ]
        if viewer_user_id
        else []
    )
    manual_items = get_all_manual_intakes(
        connection,
        search=search_value,
        viewer_user_id=(viewer_user_id if viewer_user_id else -1),
    )

    if viewer_user_id:
        catalog_items = [item for item in catalog_items if not _is_owned_by_viewer("catalog", item, viewer_user_id)]
        manual_items = [item for item in manual_items if not _is_owned_by_viewer("manual_intake", item, viewer_user_id)]

    entries = []
    for item in manual_items:
        entries.append({"entry_type": "manual_intake", "is_owned": False, **item})
    for item in catalog_items:
        entries.append({"entry_type": "catalog", "is_owned": False, **item})
    return entries


def _recommended_entries(connection, search: str = "", days: int = 60) -> list[dict]:
    viewer_user_id = get_current_user_id()
    search_value = (search or "").strip() or None

    catalog_items = (
        [
            catalog_entry_view(item)
            for item in list_catalog_items(connection, int(viewer_user_id), search=search_value)
        ]
        if viewer_user_id
        else []
    )
    manual_items = get_all_manual_intakes(
        connection,
        search=search_value,
        viewer_user_id=(viewer_user_id if viewer_user_id else -1),
    )
    recipes = get_all_recipes(
        connection,
        search=search_value,
        viewer_user_id=(viewer_user_id if viewer_user_id else -1),
    )

    if not viewer_user_id:
        return []

    rankings = get_consumed_food_usage_rankings(connection, users_id=viewer_user_id, days=days)
    usage_by_entry = {}
    for row in rankings:
        entry_type = str(row.get("entry_type") or "")
        try:
            entry_id = int(row.get("entry_id"))
        except (TypeError, ValueError):
            continue
        usage_by_entry[(entry_type, entry_id)] = {
            "usage_count": int(row.get("usage_count") or 0),
            "rank_score": float(row.get("rank_score") or 0.0),
        }

    def _search_relevance(item: dict) -> float:
        if not search_value:
            return 0.0
        query = _normalize_text(search_value)
        candidates = [item.get("name") or ""]
        if item.get("entry_type") == "catalog":
            candidates.append(item.get("brand") or "")
        elif item.get("entry_type") == "manual_intake":
            candidates.append(item.get("origin") or "")

        best = 0.0
        for raw_candidate in candidates:
            candidate = _normalize_text(str(raw_candidate))
            if not candidate:
                continue
            if candidate == query:
                score = 1000.0
            elif candidate.startswith(query):
                score = 800.0
            elif query in candidate:
                score = 600.0
            else:
                score = difflib.SequenceMatcher(None, query, candidate).ratio() * 300.0
            best = max(best, score)
        return best

    entries = []
    for entry_type, items in (
        ("catalog", catalog_items),
        ("manual_intake", manual_items),
        ("recipe", recipes),
    ):
        for item in items:
            try:
                entry_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue
            usage = usage_by_entry.get((entry_type, entry_id), {})
            enriched = {
                "entry_type": entry_type,
                "is_owned": _is_owned_by_viewer(entry_type, item, viewer_user_id),
                "usage_count": int(usage.get("usage_count") or 0),
                "rank_score": float(usage.get("rank_score") or 0.0),
                "search_relevance": _search_relevance({"entry_type": entry_type, **item}),
                **item,
            }
            entries.append(enriched)

    entries.sort(
        key=lambda item: (
            -float(item.get("search_relevance") or 0.0) if search_value else 0.0,
            -float(item.get("rank_score") or 0.0),
            0 if item.get("favorite") else 1,
            0 if item.get("is_owned") else 1,
            (item.get("name") or "").lower(),
            item.get("entry_type") or "",
            int(item.get("id") or 0),
        )
    )
    return entries


def _recipes_entries(connection, search: str = "", recipes_mode: str = "mine") -> list[dict]:
    user_id = get_current_user_id()
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
    """Viewability of a `manual_intake`/`recipe` row (catalog is resolved to
    CatalogItemRead before this point)."""
    if not entry:
        return False
    if bool(entry.get("is_published")):
        return True
    owner_id = _entry_owner_id(entry_type, entry)
    return bool(viewer_user_id and owner_id == viewer_user_id)


def _can_toggle_published(entry_type: str, entry: dict, viewer_user_id: int | None) -> bool:
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
    """Copy-name helper for `manual_intake` and `recipe` only.

    `catalog` uses `next_catalog_copy_name` (queries layer, H21). Rewriting this
    one into the queries layer for those two tables belongs to their audits.
    """
    base = (base_name or "").strip() or "Untitled"
    for index in range(1, 5000):
        suffix = " (copy)" if index == 1 else f" (copy {index})"
        candidate = f"{base}{suffix}"
        with connection.cursor() as cursor:
            if entry_type == "manual_intake":
                cursor.execute(
                    "SELECT 1 FROM manual_intake WHERE created_by = %(user_id)s AND deleted_at IS NULL AND lower(name) = lower(%(name)s) LIMIT 1;",
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


def _filtered_entries(
    connection,
    search: str = "",
    filter_value: str = "all",
    include_recipes: bool = True,
    entry_type: str | None = None,
):
    user_id = get_current_user_id()
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

    def _catalog(search_value=None, *, favorites_only=False, include_retained=False, owned_only=False):
        # No session -> the catalog branch is empty (the middleware already
        # requires a session); catalog never falls back to viewer_id = -1.
        if not user_id:
            return []
        return [
            catalog_entry_view(item)
            for item in list_catalog_items(
                connection,
                int(user_id),
                search=search_value,
                favorites_only=favorites_only,
                include_retained=include_retained,
                owned_only=owned_only,
            )
        ]

    if filter_value == "food":
        selected_types = {"catalog", "manual_intake"} if entry_type is None else {entry_type}
        catalog_items = []
        manual_items = []
        if "catalog" in selected_types:
            if has_search:
                catalog_items = _catalog(search or None)
            else:
                catalog_items = _unique_by_id(
                    _catalog(favorites_only=True, include_retained=True) + _catalog(owned_only=True)
                )
        if "manual_intake" in selected_types:
            if has_search:
                manual_items = get_all_manual_intakes(connection, search=search or None, viewer_user_id=viewer_id)
            else:
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
        selected_types = {"catalog", "manual_intake", "recipe"} if entry_type is None else {entry_type}
        catalog_items = (
            _catalog(search or None, favorites_only=True, include_retained=True)
            if "catalog" in selected_types
            else []
        )
        manual_items = (
            get_all_manual_intakes(connection, search=search or None, favorite=True, viewer_user_id=viewer_id)
            if "manual_intake" in selected_types
            else []
        )
        recipes = (
            get_all_recipes(connection, search=search or None, favorite=True, viewer_user_id=viewer_id)
            if include_recipes and "recipe" in selected_types
            else []
        )
        entries = _sorted_food_entries(catalog_items, manual_items, recipes, viewer_user_id=user_id)
    else:
        if has_search:
            catalog_items = _catalog(search or None)
            manual_items = get_all_manual_intakes(connection, search=search or None, viewer_user_id=viewer_id)
            recipes = get_all_recipes(connection, search=search or None, viewer_user_id=viewer_id) if include_recipes else []
        else:
            catalog_items = _unique_by_id(
                _catalog(favorites_only=True, include_retained=True) + _catalog(owned_only=True)
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



def _error_msg(text: str, status_code: int = 200):
    return render_fragment(
        Div(
            P("Error", cls="text-[11px] font-semibold text-red-800"),
            P(text, cls="text-xs text-red-700"),
            cls="web_container p-2 rounded-lg border border-red-200/70 bg-red-50/60",
        ),
        status_code=status_code,
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
        clean = (barcode or "").strip()
        try:
            valid_barcode = parse_barcode(clean) if clean else None
            barcode_notice = None
        except ValidationError:
            valid_barcode, barcode_notice = None, "Invalid barcode: it must contain only digits (8 to 48)."
        prefill, off_notice = None, None
        if valid_barcode:
            try:
                prefill = fetch_product_prefill(valid_barcode)
            except ExternalServiceError as error:
                logger.warning(
                    "Open Food Facts lookup failed",
                    extra={"error_code": error.code, "request_id": request_id(request)},
                )
                off_notice = "Product data could not be loaded. You can fill the form by hand."
        existing_item_id = int(existing_id) if (existing_id or "").isdigit() else None
        user_id = get_current_user_id()
        with get_connection() as connection:
            if valid_barcode and not existing_item_id and user_id:
                existing = get_catalog_item_by_barcode(connection, int(user_id), valid_barcode)
                existing_item_id = existing.id if existing else None
            # Autocomplete only; validation is SQL (F4.1).
            brands = get_food_brand_suggestions(connection, search="", limit=500)
            subtypes = get_subtype_suggestions(connection, search="", limit=500)
            tags = get_tag_suggestions(connection, search="", limit=500)
        prefill_view = _prefill_view(prefill, valid_barcode) if prefill else {"barcode": clean}
        subtype_prefill = (prefill_view.get("subtype") or "").strip()
        if subtype_prefill:
            prefill_view["subtype"] = _closest_option(subtype_prefill, subtypes)
        brand_prefill = (prefill_view.get("brand") or "").strip()
        if brand_prefill:
            prefill_view["brand"] = _closest_option(brand_prefill, brands)
        return render_page(
            request,
            lambda _: CreateCatalogPage(
                brand_options=brands,
                subtype_options=subtypes,
                tag_options=tags,
                prefill=prefill_view,
                existing_item_id=existing_item_id,
                off_notice=off_notice,
                barcode_notice=barcode_notice,
                alcohol_source_note=prefill.alcohol_source_note if prefill else None,
            ),
            show_cart=False,
        )

    @rt("/food/create/manual/form")
    def get(request: Request):
        user_id = get_current_user_id()
        with get_connection() as connection:
            subtypes = get_subtype_suggestions(connection, search="", limit=500)
            origins = get_manual_origin_suggestions(connection, user_id=user_id, search="", limit=500)
            tags = get_tag_suggestions(connection, search="", limit=500)
        return render_page(
            request,
            lambda _: CreateManualPage(subtype_options=subtypes, origin_options=origins, tag_options=tags),
            show_cart=False,
        )

    @rt("/food/create/recipe/form")
    def get(request: Request):
        with get_connection() as connection:
            tags = get_tag_suggestions(connection, search="", limit=500)
        return render_page(request, lambda _: CreateRecipePage(tag_options=tags), show_cart=False)

    @rt("/food/tags/suggestions")
    def get(request: Request, q: str = ""):
        with get_connection() as connection:
            tags = get_tag_suggestions(connection, search=(q or "").strip(), limit=500)
        return JSONResponse({"tags": tags})

    @rt("/food/rescue/options")
    def get(request: Request, q: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                return render_fragment(P("No user.", cls="text-xs text-red-700"))
            rows = get_rescue_entries_suggestions(connection, users_id=int(user_id), search=(q or "").strip(), limit=30)
        if not rows:
            return render_fragment(P("No rescue items found.", cls="text-xs text-gray-600 px-1 py-1"))
        nodes = []
        for row in rows:
            name = str(row.get("name") or "").strip() or "Unnamed"
            subtitle = str(row.get("subtitle") or "").strip()
            available_g = row.get("available_g")
            serving_g = row.get("serving_g")
            nodes.append(
                Button(
                    Div(
                        Span(name, cls="font-semibold text-gray-900 text-sm"),
                        Span(subtitle or row.get("entry_type") or "", cls="text-[11px] text-gray-500"),
                        cls="flex flex-col items-start",
                    ),
                    type="button",
                    cls="w-full text-left px-2.5 py-2 rounded-xl border border-gray-200 bg-white hover:bg-gray-50",
                    data_rescue_pick="true",
                    data_entry_type=str(row.get("entry_type") or ""),
                    data_entry_id=str(int(row.get("entry_id") or 0)),
                    data_entry_name=name,
                    data_serving_g=("" if serving_g is None else f"{float(serving_g):.3f}"),
                    data_available_g=("" if available_g is None else f"{float(available_g):.3f}"),
                )
            )
        return render_fragment(Div(*nodes, cls="flex flex-col gap-1"))

    @rt("/food/rescue/log")
    def post(
        request: Request,
        entry_type: str = "",
        entry_id: str = "",
        meal_hour: str = "",
        consumed_g: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        origin_id = _to_int(entry_id)
        meal_t = _parse_hhmm(meal_hour)
        try:
            origin = PortionOrigin((entry_type or "").strip())
        except ValueError:
            origin = None
        if origin is None or not origin_id:
            return render_fragment(P("Choose a rescue item.", cls="text-xs text-red-700"))
        try:
            # Finite, > 0 and <= 100000 g (decision 2026-09-22), validated here
            # so the form gets its own message instead of a CHECK violation.
            grams = parse_amount_grams(_to_float(consumed_g))
        except ValidationError:
            return render_fragment(
                P("Consumed amount must be greater than 0 g and at most 100000 g.", cls="text-xs text-red-700")
            )
        if not meal_t:
            return render_fragment(P("Choose a valid time.", cls="text-xs text-red-700"))

        local_dt = datetime.combine(local_today(), meal_t)
        utc_dt = local_naive_to_utc_aware(local_dt)
        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                return app_error_response(request, AuthenticationError, "Your session has expired.")
            if origin is PortionOrigin.CATALOG:
                item = get_catalog_item(connection, int(user_id), int(origin_id))
                if item is None:
                    return app_error_response(request, NotFoundError, "Rescue item not found.")
            else:
                item = get_manual_intake(connection, int(origin_id))
                if not item or not _can_view_entry("manual_intake", item, user_id):
                    return app_error_response(request, NotFoundError, "Rescue item not found.")
            try:
                with connection.transaction():
                    event_id = create_intake_event(
                        connection,
                        IntakeEventCreate(
                            user_id=int(user_id),
                            state=IntakeEventState.CONSUMED,
                            meal_type=MealType.RESCUE,
                            meal_time=utc_dt,
                        ),
                        commit=False,
                    )
                    # Un rescate es una única toma: nace con su tanda propia y
                    # offset 0, el mismo que ya tenía la porción (§4.6.1).
                    plate_id = create_intake_plate(
                        connection,
                        IntakePlateCreate(intake_event_id=int(event_id), offset_minutes=0),
                        commit=False,
                    )
                    create_portion_detail(
                        connection,
                        int(user_id),
                        PortionDetailCreate(
                            origin=origin,
                            origin_id=int(origin_id),
                            destination=PortionDestination.INTAKE_EVENT,
                            destination_id=int(event_id),
                            amount=grams,
                            offset_minutes=0,
                            plate_id=plate_id,
                        ),
                        commit=False,
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Meal event not found.")
            except ConflictError:
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
        return render_fragment(P("Rescue registered.", cls="text-xs text-green-700"))

    @rt("/food/item/{entry_type}/{entry_id}")
    def get(request: Request, entry_type: str, entry_id: int):
        with get_connection() as connection:
            user_id = get_current_user_id()
            if entry_type == "catalog":
                item = get_catalog_item(connection, int(user_id), entry_id) if user_id else None
                if item is None:
                    raise NotFoundError("Food not found.")
                summary = _catalog_detail_summary(item)
                tags = get_entry_tags(connection, "catalog", entry_id)
                events = list_planned_intake_events(connection, int(user_id)) if user_id else []
                plate_options, selected_plate_id = (
                    plate_selector_options(connection, int(user_id), events[0].id) if events else ([], None)
                )
                return render_page(
                    request,
                    lambda _: FoodDetailPage(
                        user_id=user_id or 0,
                        entry_type="catalog",
                        entry=catalog_entry_view(item),
                        summary=summary,
                        recipe_portions=None,
                        tags=tags,
                        events=events,
                        plate_options=plate_options,
                        selected_plate_id=selected_plate_id,
                        can_edit=item.can_edit,
                        can_archive=item.can_edit,
                        can_publish=item.can_edit,
                        is_published=item.is_published,
                        is_archived=item.is_archived,
                        is_library=item.is_library,
                        has_serving=item.default_portion is not None,
                        cooking_factor=item.cooking_factor,
                    ),
                    show_cart=False,
                )
            entry = None
            recipe_portions = None
            if entry_type == "manual_intake":
                entry = get_manual_intake(connection, entry_id, viewer_user_id=user_id)
            elif entry_type == "recipe":
                entry = get_recipe(connection, entry_id, viewer_user_id=user_id)
                recipe_portions = list_viewable_recipe_portions(connection, int(user_id), entry_id) if entry else []
            if not entry or not _can_view_entry(entry_type, entry, user_id):
                return HTMLResponse(status_code=404)
            summary = _build_detail_summary(entry_type, entry, recipe_portions=recipe_portions)
            tags = get_entry_tags(connection, entry_type, entry_id)
            can_edit = _can_edit_entry(entry_type, entry, user_id)
            can_delete = can_edit
            events = list_planned_intake_events(connection, int(user_id)) if user_id else []
            # Las tandas del evento que el selector va a mostrar seleccionado
            # (§7.7): sin esto el selector de tanda nacería vacío y solo se
            # llenaría al cambiar de comida.
            plate_options, selected_plate_id = (
                plate_selector_options(connection, int(user_id), events[0].id) if events else ([], None)
            )
        return render_page(
            request,
            lambda _: FoodDetailPage(
                user_id=user_id or 0,
                entry_type=entry_type,
                entry=entry,
                summary=summary,
                recipe_portions=recipe_portions,
                tags=tags,
                events=events,
                plate_options=plate_options,
                selected_plate_id=selected_plate_id,
                can_edit=can_edit,
                can_delete=can_delete,
                is_archived=False,
            ),
            show_cart=False,
        )

    @rt("/food/recipe/{recipe_id}/ingredients/form")
    def get(request: Request, recipe_id: int):
        with get_connection() as connection:
            user_id = get_current_user_id()
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
            user_id = get_current_user_id()
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return HTMLResponse(status_code=404)
            entries = _filtered_entries(connection, search=search, filter_value="food", include_recipes=False)
        return render_fragment(RecipeIngredientPickerList(recipe_id=recipe_id, foods=entries))

    @rt("/food/recipe/{recipe_id}/ingredients/add/{entry_type}/{entry_id}")
    def post(request: Request, recipe_id: int, entry_type: str, entry_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            origin = PortionOrigin(entry_type)
        except ValueError:
            # Value outside the closed set of the URL: validation_error (7.7).
            return app_error_response(request, ValidationError, "Unknown ingredient type.")

        with get_connection() as connection:
            user_id = get_current_user_id()
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return app_error_response(request, NotFoundError, "Recipe not found.")

            if origin is PortionOrigin.CATALOG:
                item = get_catalog_item(connection, int(user_id), entry_id)
                if item is None:
                    return app_error_response(request, NotFoundError, "Food not found.")
                # R3: no serving -> 100 g initial amount for a one-click add.
                amount_g = (
                    item.default_portion
                    if item.default_portion is not None
                    else INITIAL_AMOUNT_WITHOUT_SERVING_G
                )
            else:
                item = get_manual_intake(connection, entry_id)
                if not item or not _can_view_entry("manual_intake", item, user_id):
                    return app_error_response(request, NotFoundError, "Food not found.")
                amount_g = max(1.0, float(item.get("amount_g") or 100.0))

            existing = list_recipe_portions_by_origin(
                connection, int(user_id), recipe_id, origin, entry_id
            )
            try:
                with connection.transaction():
                    if existing:
                        # Recipe portions have plate_id NULL and stay outside the
                        # unique index of 4.6.4, so the same food is merged here.
                        keep = existing[0]
                        total_amount = sum(float(row.amount or 0.0) for row in existing) + amount_g
                        update_portion_amount(connection, int(user_id), int(keep.id), total_amount, commit=False)
                        for duplicate in existing[1:]:
                            delete_portion_detail(connection, int(user_id), int(duplicate.id), commit=False)
                    else:
                        create_portion_detail(
                            connection,
                            int(user_id),
                            PortionDetailCreate(
                                origin=origin,
                                origin_id=entry_id,
                                destination=PortionDestination.RECIPE,
                                destination_id=recipe_id,
                                amount=amount_g,
                            ),
                            commit=False,
                        )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            except ValidationError:
                return app_error_response(
                    request, ValidationError, "The ingredient amount would exceed 100000 g."
                )

        return HTMLResponse("", headers={"HX-Trigger": "addSuccess"})

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/amount")
    def post(
        request: Request,
        recipe_id: int,
        portion_id: int,
        amount_value: str = "",
        amount_unit: str = AmountInputUnit.PORTION.value,
    ):
        """Set the amount of a recipe ingredient from value + unit (11, decision 2026-09-22)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            unit = AmountInputUnit((amount_unit or "").strip())
        except ValueError:
            return app_error_response(request, ValidationError, "Unknown amount unit.")
        typed_amount = _to_float(amount_value)

        with get_connection() as connection:
            user_id = get_current_user_id()
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return app_error_response(request, NotFoundError, "Recipe not found.")
            try:
                portion = get_portion_detail(connection, int(user_id), portion_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            if portion.destination is not PortionDestination.RECIPE or int(portion.destination_id) != recipe_id:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            try:
                # Serving read from the food in the database (7.13). With no
                # serving, amount_to_grams rejects the `portion` unit (H15).
                parsed_amount = parse_amount_grams(
                    amount_to_grams(typed_amount, unit, portion.source.unit_g)
                    if typed_amount is not None
                    else None
                )
            except ValidationError:
                return app_error_response(
                    request, ValidationError, "The amount must be greater than 0 g and at most 100000 g."
                )
            update_portion_amount(connection, int(user_id), portion_id, parsed_amount)
            recipe_portions = list_portions_by_recipe(connection, int(user_id), recipe_id)
            recipe_total_amount = sum(float(row.amount or 0.0) for row in recipe_portions)

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
            user_id = get_current_user_id()
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_view_entry("recipe", recipe, user_id):
                return HTMLResponse(status_code=404)
            portions = list_viewable_recipe_portions(connection, int(user_id), recipe_id)
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
        try:
            parsed_cooking = parse_enum(CookingMethod, cooking, field="cooking")
            parsed_final_state = parse_enum(FoodPhysicalState, final_state, field="final_state")
            parsed_conservation = parse_enum(ConservationMethod, conservation, field="conservation")
        except ValidationError as error:
            return render_fragment(P(str(error), cls="text-red-700"))

        with get_connection() as connection:
            user_id = get_current_user_id()
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return app_error_response(request, NotFoundError, "Recipe not found.")
            try:
                portion = get_portion_detail(connection, int(user_id), portion_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            if portion.destination is not PortionDestination.RECIPE or int(portion.destination_id) != recipe_id:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            update_portion_detail_fields(
                connection,
                int(user_id),
                portion_id,
                PortionDetailUpdate(
                    cooking=(CLEAR if parsed_cooking is None else parsed_cooking),
                    final_state=(CLEAR if parsed_final_state is None else parsed_final_state),
                    conservation=(CLEAR if parsed_conservation is None else parsed_conservation),
                ),
            )

        return render_fragment(P("Advanced saved", cls="text-green-700"))

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/delete")
    def post(request: Request, recipe_id: int, portion_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_current_user_id()
            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_edit_entry("recipe", recipe, user_id):
                return app_error_response(request, NotFoundError, "Recipe not found.")
            try:
                portion = get_portion_detail(connection, int(user_id), portion_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            if portion.destination is not PortionDestination.RECIPE or int(portion.destination_id) != recipe_id:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            delete_portion_detail(connection, int(user_id), portion_id)

        return HTMLResponse("")

    def _copy_catalog_item(request: Request, user_id: int, catalog_id: int):
        with get_connection() as connection:
            source = get_catalog_item(connection, user_id, catalog_id)
            if source is None:
                return app_error_response(request, NotFoundError, "Food not found.")
            if source.can_edit:
                return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/catalog/{catalog_id}/form"})
            name = next_catalog_copy_name(connection, user_id, source.name, source.brand_id)
            root = source.origin_root_id or source.id
            try:
                with connection.transaction():
                    created_id = create_catalog_item(
                        connection,
                        CatalogItemCreate(
                            created_by=user_id,
                            origin_root_id=root,
                            name=name,
                            brand_id=source.brand_id,
                            category=source.category,
                            subtype=source.subtype,
                            initial_state=source.initial_state,
                            nutriscore=source.nutriscore,
                            nova=source.nova,
                            yuka=source.yuka,
                            default_portion=source.default_portion,
                            nutrients=NutrientValues(
                                calories_100g=source.calories_100g,
                                carbs_100g=source.carbs_100g,
                                sugars_100g=source.sugars_100g,
                                fats_100g=source.fats_100g,
                                saturated_100g=source.saturated_100g,
                                proteins_100g=source.proteins_100g,
                                fiber_100g=source.fiber_100g,
                                caffeine=source.caffeine,
                                alcohol=source.alcohol,
                            ),
                            barcode=source.barcode,
                            cooking_factor=source.cooking_factor,
                        ),
                        commit=False,
                    )
                    set_user_favorite(connection, user_id, "catalog", int(created_id), True, commit=False)
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
            except ValidationError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/catalog/{created_id}/form"})

    @rt("/food/copy/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if entry_type not in ("catalog", "manual_intake", "recipe"):
            return app_error_response(request, NotFoundError, "Unsupported entry type.")
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        if entry_type == "catalog":
            return _copy_catalog_item(request, int(user_id), entry_id)

        with get_connection() as connection:
            if entry_type == "manual_intake":
                source = get_manual_intake(connection, entry_id)
            else:
                source = get_recipe(connection, entry_id)

            if not source or not _can_view_entry(entry_type, source, user_id):
                return app_error_response(request, NotFoundError, "Item not found.")

            if _can_edit_entry(entry_type, source, user_id):
                return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/{entry_type}/{entry_id}/form"})

            root_id = _copy_root_id(source) or int(source["id"])
            copy_name = _next_copy_name(connection, entry_type, str(source.get("name") or ""), int(user_id))

            if entry_type == "manual_intake":
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
                }
                try:
                    with connection.transaction():
                        created_id = add_manual_intake(connection, payload, commit=False)
                        if not created_id:
                            raise ValueError("Could not create editable copy.")
                except ValueError as error:
                    return app_error_response(request, InfrastructureError, str(error))
                return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/manual_intake/{created_id}/form"})

            try:
                with connection.transaction():
                    created_id = add_recipe(
                        connection,
                        users_id=int(user_id),
                        origin_root_id=root_id,
                        name=copy_name,
                        meal_type=source.get("meal_type"),
                        notes=source.get("notes"),
                        commit=False,
                    )
                    if not created_id:
                        raise ValueError("Could not create editable copy.")
                    source_portions = list_viewable_recipe_portions(connection, int(user_id), int(source["id"]))
                    for portion in source_portions:
                        amount_g = float(portion.amount or 0.0)
                        if portion.origin_id <= 0 or amount_g <= 0:
                            continue
                        create_portion_detail(
                            connection,
                            int(user_id),
                            PortionDetailCreate(
                                origin=portion.origin,
                                origin_id=portion.origin_id,
                                destination=PortionDestination.RECIPE,
                                destination_id=int(created_id),
                                amount=amount_g,
                                cooking=portion.cooking,
                                conservation=portion.conservation,
                                final_state=portion.final_state,
                                strictly_weighed=portion.strictly_weighed,
                                macros_quality=portion.macros_quality,
                                is_cooked_weight=bool(portion.is_cooked_weight),
                            ),
                            commit=False,
                        )
            except ValueError as error:
                return app_error_response(request, InfrastructureError, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/recipe/{created_id}/form"})

    @rt("/food/edit/{entry_type}/{entry_id}/form")
    def get(request: Request, entry_type: str, entry_id: int):
        with get_connection() as connection:
            user_id = get_current_user_id()
            entry = None
            if entry_type == "catalog":
                item = get_catalog_item(connection, int(user_id), entry_id) if user_id else None
                if item is None:
                    raise NotFoundError("Food not found.")
                if not item.can_edit:
                    raise AuthorizationError(
                        "Only the owner can edit this food. Create a copy to edit it."
                    )
                brands = get_food_brand_suggestions(connection, search="", limit=500)
                subtypes = get_subtype_suggestions(connection, search="", limit=500)
                tags = get_tag_suggestions(connection, search="", limit=500)
                selected_tags = [str(row.get("name") or "") for row in get_entry_tags(connection, "catalog", entry_id)]
                return render_page(
                    request,
                    lambda _: EditCatalogPage(
                        entry=catalog_entry_view(item),
                        brand_options=brands,
                        subtype_options=subtypes,
                        tag_options=tags,
                        selected_tags=selected_tags,
                    ),
                    show_cart=False,
                )
            if entry_type == "manual_intake":
                entry = get_manual_intake(connection, entry_id, viewer_user_id=user_id)
                if not entry or not _can_view_entry("manual_intake", entry, user_id):
                    return HTMLResponse(status_code=404)
                if not _can_edit_entry("manual_intake", entry, user_id):
                    return HTMLResponse(status_code=403)
                subtypes = get_subtype_suggestions(connection, search="", limit=500)
                origins = get_manual_origin_suggestions(connection, user_id=user_id, search="", limit=500)
                tags = get_tag_suggestions(connection, search="", limit=500)
                selected_tags = [str(row.get("name") or "") for row in get_entry_tags(connection, "manual_intake", entry_id)]
                return render_page(
                    request,
                    lambda _: EditManualPage(
                        entry=entry,
                        subtype_options=subtypes,
                        origin_options=origins,
                        show_published=_can_toggle_published("manual_intake", entry, user_id),
                        tag_options=tags,
                        selected_tags=selected_tags,
                    ),
                    show_cart=False,
                )
            if entry_type == "recipe":
                entry = get_recipe(connection, entry_id, viewer_user_id=user_id)
                if not entry or not _can_view_entry("recipe", entry, user_id):
                    return HTMLResponse(status_code=404)
                if not _can_edit_entry("recipe", entry, user_id):
                    return HTMLResponse(status_code=403)
                tags = get_tag_suggestions(connection, search="", limit=500)
                selected_tags = [str(row.get("name") or "") for row in get_entry_tags(connection, "recipe", entry_id)]
                return render_page(
                    request,
                    lambda _: EditRecipePage(
                        entry=entry,
                        show_published=_can_toggle_published("recipe", entry, user_id),
                        tag_options=tags,
                        selected_tags=selected_tags,
                    ),
                    show_cart=False,
                )
        return HTMLResponse(status_code=404)

    def _archive_catalog_item(request: Request, user_id: int, catalog_id: int):
        with get_connection() as connection:
            try:
                with connection.transaction():
                    # False = already archived: idempotent no-op (§9.6).
                    archive_catalog_item(connection, user_id, catalog_id, commit=False)
                    set_user_favorite(connection, user_id, "catalog", catalog_id, False, commit=False)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Food not found.")
        return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/archive/catalog/{catalog_id}")
    def post(request: Request, catalog_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        return _archive_catalog_item(request, int(user_id), catalog_id)

    @rt("/food/publish/catalog/{catalog_id}")
    def post(request: Request, catalog_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                publish_catalog_item(connection, int(user_id), catalog_id, commit=True)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Food not found.")
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/catalog/{catalog_id}"})

    @rt("/food/unpublish/catalog/{catalog_id}")
    def post(request: Request, catalog_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                unpublish_catalog_item(connection, int(user_id), catalog_id, commit=True)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Food not found.")
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/catalog/{catalog_id}"})

    @rt("/food/delete/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if entry_type not in ("catalog", "manual_intake", "recipe"):
            return app_error_response(request, NotFoundError, "Unsupported entry type.")
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        if entry_type == "catalog":
            # Old cached pages still call /food/delete/catalog/{id}.
            return _archive_catalog_item(request, int(user_id), entry_id)

        with get_connection() as connection:
            current = None
            deleted = False
            if entry_type == "manual_intake":
                current = get_manual_intake(connection, entry_id)
                if not current or not _can_view_entry("manual_intake", current, user_id):
                    return app_error_response(request, NotFoundError, "Manual intake not found.")
                if not _can_edit_entry("manual_intake", current, user_id):
                    return app_error_response(request, AuthorizationError, "Only the owner can delete this item.")
                deleted = delete_manual_intake(connection, entry_id)
            else:
                current = get_recipe(connection, entry_id)
                if not current or not _can_view_entry("recipe", current, user_id):
                    return app_error_response(request, NotFoundError, "Recipe not found.")
                if not _can_edit_entry("recipe", current, user_id):
                    return app_error_response(request, AuthorizationError, "Only the owner can delete this item.")
                deleted = delete_recipe(connection, entry_id)

            if not deleted:
                action = "archive" if entry_type == "manual_intake" else "delete"
                return app_error_response(
                    request, NotFoundError, f"Could not {action} this item. It may not exist or you may not own it."
                )
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/log/{entry_type}/{entry_id}")
    def post(
        request: Request,
        entry_type: str,
        entry_id: int,
        amount_value: str = "",
        amount_unit: str = AmountInputUnit.PORTION.value,
        plate_value: str = "",
        plate_unit: str = AmountInputUnit.PERCENT.value,
        intake_event_id: str = "",
        plate_id: str = "",
        cooking: str = "",
        final_state: str = "",
        conservation: str = "",
        is_cooked_weight: str = "",
    ):
        """Add a food or a recipe from its page to a planned event.

        The form sends what the user typed, value + unit, and the server
        converts it (measurement_conventions.md 11, decision 2026-09-22):
        `amount_value`/`amount_unit` is the cooked total (`portion`, `g`, `lb`,
        `oz`) and `plate_value`/`plate_unit` the part of it that is plated
        (`%` of the total or `g`). Only the plated amount is persisted; the
        cooked total is used to bound it and is not stored (decision
        2026-09-18). The JavaScript only repaints the numbers.
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if entry_type not in ("catalog", "manual_intake", "recipe"):
            return app_error_response(request, ValidationError, "Unknown food type.")

        try:
            cooked_weight = _parse_strict_bool(is_cooked_weight)
        except ValidationError:
            return app_error_response(request, ValidationError, "No se ha entendido la casilla 'Cooked weight'.")
        try:
            unit = AmountInputUnit((amount_unit or "").strip())
            plated_unit = AmountInputUnit((plate_unit or "").strip())
        except ValueError:
            return render_fragment(P("Choose a valid unit.", cls="text-red-700"))
        if unit is AmountInputUnit.PERCENT or plated_unit not in (AmountInputUnit.PERCENT, AmountInputUnit.GRAMS):
            return render_fragment(P("Choose a valid unit.", cls="text-red-700"))
        typed_amount = _to_float(amount_value)
        typed_plate = _to_float(plate_value)
        if typed_amount is None or typed_plate is None:
            return render_fragment(P("Amount must be a number.", cls="text-red-700"))
        try:
            parsed_cooking = parse_enum(CookingMethod, cooking, field="cooking")
            parsed_final_state = parse_enum(FoodPhysicalState, final_state, field="final_state")
            parsed_conservation = parse_enum(ConservationMethod, conservation, field="conservation")
        except ValidationError as error:
            return render_fragment(P(str(error), cls="text-red-700"))

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                # Defence in depth: the middleware already covers these routes
                # (finding 26 of audit_intake_event).
                return app_error_response(request, AuthenticationError, "Your session has expired.")
            origin_item = None
            recipe_rows = []
            if entry_type == "catalog":
                origin_item = get_catalog_item(connection, int(user_id), entry_id)
                if origin_item is None:
                    return app_error_response(request, NotFoundError, "Item not found.")
                # R4: the 422 applies only when the user ticks the box.
                if cooked_weight and origin_item.cooking_factor is None:
                    return _error_msg("This food has no cooking factor, so it cannot be weighed cooked.")
                serving_grams = origin_item.default_portion
                if unit is AmountInputUnit.PORTION and serving_grams is None:
                    return _error_msg("This food has no serving. Use grams, lb or oz.")
            elif entry_type == "manual_intake":
                origin_item = get_manual_intake(connection, entry_id)
                if not origin_item or not _can_view_entry("manual_intake", origin_item, user_id):
                    return app_error_response(request, NotFoundError, "Item not found.")
                recipe_rows = []
                summary = _build_detail_summary(entry_type, origin_item, recipe_portions=recipe_rows)
                serving_grams = max(1.0, float(summary.get("default_amount_g") or 100.0))
            else:
                origin_item = get_recipe(connection, entry_id)
                if not origin_item or not _can_view_entry("recipe", origin_item, user_id):
                    return app_error_response(request, NotFoundError, "Item not found.")
                recipe_rows = list_viewable_recipe_portions(connection, int(user_id), entry_id)
                summary = _build_detail_summary(entry_type, origin_item, recipe_portions=recipe_rows)
                serving_grams = max(1.0, float(summary.get("default_amount_g") or 100.0))
            try:
                total_grams = parse_amount_grams(amount_to_grams(typed_amount, unit, serving_grams))
                if plated_unit is AmountInputUnit.PERCENT:
                    if not (0.0 < typed_plate <= 100.0):
                        raise ValidationError("plate_percent_out_of_range")
                    plated_grams = total_grams * typed_plate / 100.0
                else:
                    # The page shows the plated grams with one decimal, so
                    # "all of it" can exceed the total by that rounding.
                    if not (0.0 < typed_plate <= total_grams + _PLATE_DISPLAY_TOLERANCE_G):
                        raise ValidationError("plate_grams_out_of_range")
                    plated_grams = min(typed_plate, total_grams)
                plated_grams = parse_amount_grams(plated_grams)
            except ValidationError:
                # Form validation: 200 + fragment inside the form (9.5).
                return render_fragment(
                    P(
                        "The amount must be greater than 0 g and at most 100000 g, and the "
                        "amount to plate must be between 0 and the total.",
                        cls="text-red-700",
                    )
                )

            try:
                with connection.transaction():
                    if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                        event_id = get_planned_intake_event(connection, int(user_id), int(intake_event_id))
                    else:
                        event_id = create_intake_event(
                            connection,
                            IntakeEventCreate(
                                user_id=int(user_id),
                                state=IntakeEventState.PLANNED,
                                meal_type=_default_meal_type_now(connection, int(user_id)),
                            ),
                            commit=False,
                        )
                    event_data = get_intake_event(connection, int(user_id), event_id)
                    offset_minutes = _event_auto_offset_minutes(event_data)

                    if entry_type != "recipe":
                        target_plate_id = _resolve_event_plate(
                            connection, int(user_id), event_id, plate_id, offset_minutes
                        )
                        create_portion_detail(
                            connection,
                            int(user_id),
                            PortionDetailCreate(
                                origin=PortionOrigin(entry_type),
                                origin_id=entry_id,
                                destination=PortionDestination.INTAKE_EVENT,
                                destination_id=event_id,
                                plate_id=target_plate_id,
                                amount=plated_grams,
                                cooking=parsed_cooking,
                                final_state=parsed_final_state,
                                conservation=parsed_conservation,
                                is_cooked_weight=(cooked_weight if entry_type == "catalog" else False),
                            ),
                            commit=False,
                        )
                    else:
                        total_recipe_amount = sum(float(row.amount or 0.0) for row in recipe_rows)
                        if total_recipe_amount <= 0:
                            raise ValidationError("recipe_without_ingredients")
                        factor = plated_grams / total_recipe_amount
                        # Una receta importada entra como tanda propia, con el
                        # nombre de la receta (§4.6.5): es un plato completo,
                        # no ingredientes sueltos que se mezclen con los demás.
                        recipe_plate_id = create_intake_plate(
                            connection,
                            IntakePlateCreate(
                                intake_event_id=event_id,
                                name=(origin_item.get("name") or None),
                                offset_minutes=offset_minutes,
                            ),
                            commit=False,
                        )
                        created = 0
                        for row in recipe_rows:
                            row_amount = float(row.amount or 0.0) * factor
                            if row_amount <= 0 or row.origin_id <= 0:
                                continue
                            create_portion_detail(
                                connection,
                                int(user_id),
                                PortionDetailCreate(
                                    origin=row.origin,
                                    origin_id=row.origin_id,
                                    destination=PortionDestination.INTAKE_EVENT,
                                    destination_id=event_id,
                                    plate_id=recipe_plate_id,
                                    amount=row_amount,
                                    cooking=row.cooking,
                                    conservation=row.conservation,
                                    final_state=row.final_state,
                                    is_cooked_weight=bool(row.is_cooked_weight),
                                ),
                                commit=False,
                            )
                            created += 1
                        if not created:
                            raise ValidationError("recipe_without_ingredients")
            except NotFoundError:
                # intake_event_id ajeno o archivado: recurso inexistente (§5.4),
                # no un fallo de servidor (hallazgo 23).
                return app_error_response(request, NotFoundError, "That meal no longer exists.")
            except ConflictError:
                # El evento ya no está 'planned'.
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError as error:
                if str(error) == "recipe_without_ingredients":
                    return render_fragment(P("Recipe has no ingredients to log.", cls="text-red-700"))
                return render_fragment(P("Could not log this food: check the amounts.", cls="text-red-700"))
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

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
                    entries = _recommended_entries(connection, search=clean_search, days=60)
            elif filter == "recipes":
                mode = (search_mode or "recommended").strip().lower()
                entries = _recipes_entries(connection, search=clean_search, recipes_mode=recipes_mode_norm)
            else:
                mode = (search_mode or "recommended").strip().lower()
                selected_entry_type = None
                if filter == "food":
                    selected_entry_type = "catalog" if food_mode_norm == "catalog" else "manual_intake"
                elif filter == "favs":
                    selected_entry_type = {
                        "catalog": "catalog",
                        "manual": "manual_intake",
                        "recipes": "recipe",
                    }[favs_mode_norm]
                entries = _filtered_entries(
                    connection,
                    search=clean_search,
                    filter_value=filter,
                    entry_type=selected_entry_type,
                )

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
    def post(request: Request, food_id: int, intake_event_id: str = "", plate_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                return app_error_response(request, AuthenticationError, "Your session has expired.")
            catalog_item = get_catalog_item(connection, int(user_id), food_id)
            if catalog_item is None:
                return app_error_response(request, NotFoundError, "Food not found.")
            # R3: no serving -> 100 g initial amount for a one-click add.
            portion_amount = (
                catalog_item.default_portion
                if catalog_item.default_portion is not None
                else INITIAL_AMOUNT_WITHOUT_SERVING_G
            )
            try:
                with connection.transaction():
                    if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                        event_id = get_planned_intake_event(connection, int(user_id), int(intake_event_id))
                    else:
                        event_id = create_intake_event(
                            connection,
                            IntakeEventCreate(
                                user_id=int(user_id),
                                state=IntakeEventState.PLANNED,
                                meal_type=_default_meal_type_now(connection, int(user_id)),
                            ),
                            commit=False,
                        )
                    event_data = get_intake_event(connection, int(user_id), event_id)
                    offset_minutes = _event_auto_offset_minutes(event_data)
                    target_plate_id = _resolve_event_plate(
                        connection, int(user_id), event_id, plate_id, offset_minutes
                    )
                    create_portion_detail(
                        connection,
                        int(user_id),
                        PortionDetailCreate(
                            origin=PortionOrigin.CATALOG,
                            origin_id=food_id,
                            destination=PortionDestination.INTAKE_EVENT,
                            destination_id=event_id,
                            plate_id=target_plate_id,
                            amount=portion_amount,
                        ),
                        commit=False,
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal no longer exists.")
            except ConflictError:
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            return HTMLResponse("", headers={"HX-Trigger": "addSuccess"})

    @rt("/add_manual_intake/{intake_id}")
    def post(request: Request, intake_id: int, intake_event_id: str = "", plate_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                # Sin sesión: 401 (error_conventions.md §3.3). Defensa en
                # profundidad; el middleware ya cubre estas rutas (hallazgo 26).
                return HTMLResponse(status_code=401)

            intake_item = get_manual_intake(connection, intake_id)
            if not intake_item or not _can_view_entry("manual_intake", intake_item, user_id):
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)

            try:
                with connection.transaction():
                    if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                        event_id = get_planned_intake_event(connection, int(user_id), int(intake_event_id))
                    else:
                        event_id = create_intake_event(
                            connection,
                            IntakeEventCreate(
                                user_id=int(user_id),
                                state=IntakeEventState.PLANNED,
                                meal_type=_default_meal_type_now(connection, int(user_id)),
                            ),
                            commit=False,
                        )
                    portion_amount = float(intake_item.get("amount_g") or 100.0)
                    event_data = get_intake_event(connection, int(user_id), event_id)
                    offset_minutes = _event_auto_offset_minutes(event_data)
                    target_plate_id = _resolve_event_plate(
                        connection, int(user_id), event_id, plate_id, offset_minutes
                    )

                    portion_id = create_portion_detail(
                        connection,
                        int(user_id),
                        PortionDetailCreate(
                            origin=PortionOrigin.MANUAL_INTAKE,
                            origin_id=intake_id,
                            destination=PortionDestination.INTAKE_EVENT,
                            destination_id=event_id,
                            plate_id=target_plate_id,
                            amount=portion_amount,
                        ),
                        commit=False,
                    )
                    if not portion_id:
                        raise ValueError("Could not add manual intake.")
            except NotFoundError:
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)
            except ConflictError:
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=409)
            except ValueError:
                portion_id = None
            headers = {"HX-Trigger": "addSuccess" if portion_id else "addError"}
            return HTMLResponse("", headers=headers)

    @rt("/add_recipe/{recipe_id}")
    def post(request: Request, recipe_id: int, intake_event_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                # Sin sesión: 401 (error_conventions.md §3.3). Defensa en
                # profundidad; el middleware ya cubre estas rutas (hallazgo 26).
                return HTMLResponse(status_code=401)

            recipe = get_recipe(connection, recipe_id)
            if not recipe or not _can_view_entry("recipe", recipe, user_id):
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)

            try:
                with connection.transaction():
                    if intake_event_id and intake_event_id.isdigit() and int(intake_event_id) != 0:
                        event_id = get_planned_intake_event(connection, int(user_id), int(intake_event_id))
                    else:
                        try:
                            recipe_meal_type = MealType(recipe["meal_type"]) if recipe.get("meal_type") else None
                        except ValueError:
                            recipe_meal_type = None
                        # La receta manda si trae su propio meal_type; si no,
                        # cae al mismo default por franja horaria que el resto
                        # de altas automáticas (§7.14, decisión 2026-09-11).
                        if recipe_meal_type is None:
                            recipe_meal_type = _default_meal_type_now(connection, int(user_id))
                        event_id = create_intake_event(
                            connection,
                            IntakeEventCreate(
                                user_id=int(user_id),
                                state=IntakeEventState.PLANNED,
                                meal_type=recipe_meal_type,
                                name=recipe.get("name"),
                            ),
                            commit=False,
                        )

                    event_data = get_intake_event(connection, int(user_id), event_id)
                    offset_minutes = _event_auto_offset_minutes(event_data)
                    # La receta entra como tanda propia con su nombre (§4.6.5).
                    recipe_plate_id = create_intake_plate(
                        connection,
                        IntakePlateCreate(
                            intake_event_id=event_id,
                            name=(recipe.get("name") or None),
                            offset_minutes=offset_minutes,
                        ),
                        commit=False,
                    )

                    recipe_portions = list_viewable_recipe_portions(connection, int(user_id), recipe_id)
                    created_ids = []
                    for row in recipe_portions:
                        if row.origin_id <= 0:
                            continue
                        created_ids.append(
                            create_portion_detail(
                                connection,
                                int(user_id),
                                PortionDetailCreate(
                                    origin=row.origin,
                                    origin_id=row.origin_id,
                                    destination=PortionDestination.INTAKE_EVENT,
                                    destination_id=event_id,
                                    plate_id=recipe_plate_id,
                                    amount=float(row.amount or 0.0),
                                    cooking=row.cooking,
                                    conservation=row.conservation,
                                    final_state=row.final_state,
                                    is_cooked_weight=bool(row.is_cooked_weight),
                                ),
                                commit=False,
                            )
                        )
                    if not recipe_portions or not created_ids or not all(created_ids):
                        raise ValueError("Could not add recipe.")
                    ok = True
            except NotFoundError:
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=404)
            except ConflictError:
                return HTMLResponse("", headers={"HX-Trigger": "addError"}, status_code=409)
            except ValueError:
                ok = False
            headers = {"HX-Trigger": "addSuccess" if ok else "addError"}
            return HTMLResponse("", headers=headers)

    @rt("/food/favorite/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: int):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_current_user_id()

            if entry_type == "catalog":
                if not user_id:
                    return app_error_response(request, AuthenticationError, "Your session has expired.")
                item = get_catalog_item(connection, int(user_id), entry_id)
                if item is None:
                    return app_error_response(request, NotFoundError, "Food not found.")
                if not item.is_favorite and not item.is_listable:
                    return app_error_response(
                        request,
                        ConflictError,
                        "Archived or unpublished foods cannot be added to favorites.",
                    )
                new_favorite = toggle_user_favorite(connection, int(user_id), entry_type, entry_id)
                if new_favorite is None:
                    return app_error_response(request, NotFoundError, "Food not found.")
                return render_fragment(FavoriteButton(entry_type, entry_id, new_favorite))

            current = None
            new_favorite = None
            if entry_type == "manual_intake":
                current = get_manual_intake(connection, entry_id, viewer_user_id=user_id)
                if current and _can_view_entry("manual_intake", current, user_id):
                    new_favorite = toggle_user_favorite(connection, user_id, entry_type, entry_id)
            elif entry_type == "recipe":
                current = get_recipe(connection, entry_id, viewer_user_id=user_id)
                if current and _can_view_entry("recipe", current, user_id):
                    new_favorite = toggle_user_favorite(connection, user_id, entry_type, entry_id)

            if not current or new_favorite is None:
                return HTMLResponse(status_code=400)

            return render_fragment(FavoriteButton(entry_type, entry_id, new_favorite))

    @rt("/food/edit/catalog/{entry_id}")
    def post(
        request: Request,
        entry_id: int,
        name: str = "",
        brand: str = "",
        brand__added: str = "",
        category: str = "",
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
        tags_json: str | None = None,
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_catalog_item_request(
                nutrients_source="fields",
                name=name,
                brand=brand,
                brand__added=brand__added,
                category=category,
                subtype=subtype,
                subtype__added=subtype__added,
                initial_state=initial_state,
                nutriscore=nutriscore,
                nova=nova,
                yuka=yuka,
                default_portion=default_portion,
                caffeine=caffeine,
                alcohol=alcohol,
                barcode=barcode,
                cooking_factor=cooking_factor,
                tags_json=tags_json,
                calories_100g=calories_100g,
                carbs_100g=carbs_100g,
                sugars_100g=sugars_100g,
                fats_100g=fats_100g,
                saturated_100g=saturated_100g,
                proteins_100g=proteins_100g,
                fiber_100g=fiber_100g,
            )
        except ValidationError as error:
            return _error_msg(str(error))

        with get_connection() as connection:
            try:
                with connection.transaction():
                    brand_id, subtype = _resolve_catalog_refs(connection, int(user_id), req)
                    update_catalog_item(
                        connection,
                        int(user_id),
                        entry_id,
                        _catalog_update(req, brand_id, subtype),
                        commit=False,
                    )
                    if req.tags is not None:
                        set_entry_tags(connection, "catalog", entry_id, req.tags, commit=False)
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Food not found or no longer editable.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
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
        is_published: str = "",
        tags_json: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name or not amount_g:
            return _error_msg("Name, subtype and amount are required.")

        amount_value, amount_error = _strict_float(
            amount_g, "Amount", MANUAL_AMOUNT_LIMITS[0], MANUAL_AMOUNT_LIMITS[1]
        )
        if amount_error or amount_value <= 0:
            return _error_msg(amount_error or "Amount must be greater than zero.", status_code=422)
        nutrition, nutrition_error = _parse_manual_nutrients(
            {
                "calories_100g": calories_100g,
                "carbs_100g": carbs_100g,
                "sugars_100g": sugars_100g,
                "fats_100g": fats_100g,
                "saturated_100g": saturated_100g,
                "proteins_100g": proteins_100g,
                "fiber_100g": fiber_100g,
                "caffeine": caffeine,
                "alcohol": alcohol,
            },
            ig_confidence,
        )
        if nutrition_error:
            return _error_msg(nutrition_error, status_code=422)

        with get_connection() as connection:
            current = get_manual_intake(connection, entry_id)
            user_id = get_current_user_id()
            if not current or not _can_view_entry("manual_intake", current, user_id):
                return _error_msg("Manual intake not found.")
            if not _can_edit_entry("manual_intake", current, user_id):
                return _error_msg("Only the owner can edit this item. Create a copy to edit it.")
            subtype_options = get_subtype_suggestions(connection, search="", limit=500)
            origin_options = get_manual_origin_suggestions(connection, user_id=user_id, search="", limit=500)

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

            if manual_intake_name_origin_exists(
                connection,
                users_id=user_id,
                name=clean_name,
                origin=clean_origin,
                exclude_id=entry_id,
            ):
                return _error_msg("A manual intake with that name and origin already exists for this user.")

            can_toggle_published = _can_toggle_published("manual_intake", current, user_id)
            payload = {
                "name": clean_name,
                "description": description.strip() or None,
                "subtype": clean_subtype,
                "origin": clean_origin,
                "amount_g": amount_value,
                **nutrition,
                "glycemic_index": clean_glycemic,
                "favorite": (None if (favorite or "").strip() == "" else _to_bool(favorite)),
            }
            if can_toggle_published:
                try:
                    payload["is_published"] = _parse_strict_bool(is_published)
                except ValidationError as error:
                    return _error_msg(str(error))
            try:
                with connection.transaction():
                    if not update_manual_intake(connection, entry_id, payload, commit=False):
                        raise ValueError("Manual intake could not be updated.")
                    if (favorite or "").strip() != "" and not set_user_favorite(
                        connection,
                        int(user_id),
                        "manual_intake",
                        entry_id,
                        _to_bool(favorite),
                        commit=False,
                    ):
                        raise ValueError("Could not save the favorite status.")
                    if (tags_json or "").strip() and not set_entry_tags(
                        connection,
                        "manual_intake",
                        entry_id,
                        _parse_tags_json(tags_json),
                        commit=False,
                    ):
                        raise ValueError("Could not save the tags.")
            except (ValueError, ValidationError) as error:
                return _error_msg(str(error))
            return HTMLResponse("", headers={"HX-Redirect": f"/food/item/manual_intake/{entry_id}"})

    @rt("/food/edit/recipe/{entry_id}")
    def post(
        request: Request,
        entry_id: int,
        name: str = "",
        meal_type: str = "",
        notes: str = "",
        favorite: str = "",
        is_published: str = "",
        tags_json: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name:
            return _error_msg("Recipe name is required.")
        with get_connection() as connection:
            user_id = get_current_user_id()
            current = get_recipe(connection, entry_id)
            if not current or not _can_view_entry("recipe", current, user_id):
                return _error_msg("Recipe not found.")
            if not _can_edit_entry("recipe", current, user_id):
                return _error_msg("Only the owner can edit this item. Create a copy to edit it.")
            clean_meal_type, meal_type_error = _coerce_choice(
                meal_type,
                options=[meal_type.value for meal_type in MealType],
                allow_add=False,
                added=False,
                required=False,
                label="Meal type",
            )
            if meal_type_error:
                return _error_msg(meal_type_error)
            can_toggle_published = _can_toggle_published("recipe", current, user_id)
            try:
                with connection.transaction():
                    if not update_recipe(
                        connection,
                        entry_id,
                        name=clean_name,
                        meal_type=clean_meal_type,
                        notes=notes.strip() or None,
                        is_published=_parse_strict_bool(is_published) if can_toggle_published else None,
                        commit=False,
                    ):
                        raise ValueError("Recipe could not be updated.")
                    if (favorite or "").strip() != "" and not set_user_favorite(
                        connection,
                        int(user_id),
                        "recipe",
                        entry_id,
                        _to_bool(favorite),
                        commit=False,
                    ):
                        raise ValueError("Could not save the favorite status.")
                    if (tags_json or "").strip() and not set_entry_tags(
                        connection,
                        "recipe",
                        entry_id,
                        _parse_tags_json(tags_json),
                        commit=False,
                    ):
                        raise ValueError("Could not save the tags.")
            except (ValueError, ValidationError) as error:
                return _error_msg(str(error))
            return HTMLResponse("", headers={"HX-Redirect": f"/food/item/recipe/{entry_id}"})

    @rt("/food/create/catalog")
    def post(
        request: Request,
        name: str = "",
        brand: str = "",
        brand__added: str = "",
        category: str = "",
        subtype: str = "",
        subtype__added: str = "",
        initial_state: str = "",
        nutriscore: str = "",
        nova: str = "",
        yuka: str = "",
        default_portion: str = "",
        caffeine: str = "",
        alcohol: str = "",
        barcode: str = "",
        cooking_factor: str = "",
        favorite: str = "",
        tags_json: str | None = None,
        catalog_smart_macros_raw: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_catalog_item_request(
                nutrients_source="smart",
                name=name,
                brand=brand,
                brand__added=brand__added,
                category=category,
                subtype=subtype,
                subtype__added=subtype__added,
                initial_state=initial_state,
                nutriscore=nutriscore,
                nova=nova,
                yuka=yuka,
                default_portion=default_portion,
                caffeine=caffeine,
                alcohol=alcohol,
                barcode=barcode,
                cooking_factor=cooking_factor,
                favorite=favorite,
                tags_json=tags_json,
                smart_raw=catalog_smart_macros_raw,
            )
        except ValidationError as error:
            return _error_msg(str(error))

        with get_connection() as connection:
            try:
                with connection.transaction():
                    brand_id, subtype = _resolve_catalog_refs(connection, int(user_id), req)
                    created_id = create_catalog_item(
                        connection,
                        _catalog_create(req, int(user_id), brand_id, subtype),
                        commit=False,
                    )
                    # The food is born personal (R5). Favorite and tags are user data.
                    set_user_favorite(connection, int(user_id), "catalog", created_id, bool(req.favorite), commit=False)
                    if req.tags is not None:
                        set_entry_tags(connection, "catalog", created_id, req.tags, commit=False)
            except ValidationError as error:
                return _error_msg(str(error))
            except ConflictError as error:
                return app_error_response(request, error, str(error))
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
        tags_json: str = "",
        manual_smart_macros_raw: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name or not amount_g:
            return _error_msg("Name, subtype and amount are required.")

        amount_value, amount_error = _strict_float(
            amount_g, "Amount", MANUAL_AMOUNT_LIMITS[0], MANUAL_AMOUNT_LIMITS[1]
        )
        if amount_error or amount_value <= 0:
            return _error_msg(amount_error or "Amount must be greater than zero.", status_code=422)
        try:
            # Server-side smart macros; the hidden fields are ignored (H16).
            nutrients = nutrients_from_smart_text(manual_smart_macros_raw, caffeine, alcohol)
        except ValidationError as error:
            return _error_msg(str(error), status_code=422)
        ig_value, ig_error = _strict_int(ig_confidence, "IG confidence", 1, 5)
        if ig_error:
            return _error_msg(ig_error, status_code=422)
        nutrition = {
            "calories_100g": nutrients.calories_100g,
            "carbs_100g": nutrients.carbs_100g,
            "sugars_100g": nutrients.sugars_100g,
            "fats_100g": nutrients.fats_100g,
            "saturated_100g": nutrients.saturated_100g,
            "proteins_100g": nutrients.proteins_100g,
            "fiber_100g": nutrients.fiber_100g,
            "caffeine": nutrients.caffeine,
            "alcohol": nutrients.alcohol,
            "ig_confidence": ig_value,
        }

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                return _error_msg("No users found.")
            subtype_options = get_subtype_suggestions(connection, search="", limit=500)
            origin_options = get_manual_origin_suggestions(connection, user_id=user_id, search="", limit=500)

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

            if manual_intake_name_origin_exists(connection, users_id=user_id, name=clean_name, origin=clean_origin):
                return _error_msg("A manual intake with that name and origin already exists for this user.")

            payload = {
                "created_by": user_id,
                "name": clean_name,
                "description": description.strip() or None,
                "subtype": clean_subtype,
                "origin": clean_origin,
                "amount_g": amount_value,
                **nutrition,
                "glycemic_index": clean_glycemic,
            }

            try:
                with connection.transaction():
                    created_id = add_manual_intake(connection, payload, commit=False)
                    if not created_id:
                        raise ValueError("Manual intake could not be created.")
                    favorite_value = _to_bool(favorite)
                    if not set_user_favorite(
                        connection,
                        int(user_id),
                        "manual_intake",
                        int(created_id),
                        favorite_value,
                        commit=False,
                    ):
                        raise ValueError("Manual intake favorite could not be saved.")
                    if (tags_json or "").strip() and not set_entry_tags(
                        connection,
                        "manual_intake",
                        int(created_id),
                        _parse_tags_json(tags_json),
                        commit=False,
                    ):
                        raise ValueError("Manual intake tags could not be saved.")
            except (ValueError, ValidationError) as error:
                return _error_msg(str(error))
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/create/recipe")
    def post(
        request: Request,
        name: str = "",
        meal_type: str = "",
        notes: str = "",
        favorite: str = "",
        tags_json: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        clean_name = (name or "").strip()
        if not clean_name:
            return _error_msg("Recipe name is required.")

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                return _error_msg("No users found.")
            clean_meal_type, meal_type_error = _coerce_choice(
                meal_type,
                options=[meal_type.value for meal_type in MealType],
                allow_add=False,
                added=False,
                required=False,
                label="Meal type",
            )
            if meal_type_error:
                return _error_msg(meal_type_error)
            try:
                with connection.transaction():
                    created_id = add_recipe(
                        connection,
                        users_id=user_id,
                        name=clean_name,
                        meal_type=clean_meal_type,
                        notes=notes.strip() or None,
                        commit=False,
                    )
                    if not created_id:
                        raise ValueError("Recipe could not be created.")
                    if not set_user_favorite(
                        connection,
                        int(user_id),
                        "recipe",
                        int(created_id),
                        _to_bool(favorite),
                        commit=False,
                    ):
                        raise ValueError("Recipe favorite could not be saved.")
                    if (tags_json or "").strip() and not set_entry_tags(
                        connection,
                        "recipe",
                        int(created_id),
                        _parse_tags_json(tags_json),
                        commit=False,
                    ):
                        raise ValueError("Recipe tags could not be saved.")
            except (ValueError, ValidationError) as error:
                return _error_msg(str(error))
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
                maxlength=str(INTAKE_EVENT_NAME_MAX_LENGTH),
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

    @rt("/food/plate_selector")
    def get(request: Request, intake_event_id: str = ""):
        """Selector de tanda del evento elegido en el selector de comida (§7.7).

        Devuelve vacío solo cuando no hay evento del que listar tandas (ninguno
        seleccionado, `New Meal`, o un evento que ya no está en el carrito).
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        raw_event_id = (intake_event_id or "").strip()
        if not raw_event_id.isdigit() or int(raw_event_id) == 0:
            return render_fragment(PlateSelector([]))

        with get_connection() as connection:
            try:
                event_id = get_planned_intake_event(connection, int(user_id), int(raw_event_id))
            except (NotFoundError, ConflictError):
                return render_fragment(PlateSelector([]))
            # Preseleccionada la última tanda a la que se añadió algo: montando
            # el segundo plato se añaden varios alimentos seguidos al mismo (§7.7).
            options, last_used = plate_selector_options(connection, int(user_id), event_id)
            return render_fragment(PlateSelector(options, selected_id=last_used))

    @rt("/create_named_event")
    def post(request: Request, meal_name: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        clean_name = (meal_name or "").strip()
        if len(clean_name) > INTAKE_EVENT_NAME_MAX_LENGTH:
            # §7.3: no truncar silenciosamente; el exceso sobre el VARCHAR(255)
            # se rechaza en el boundary (decisión 2026-09-09, hallazgo 24).
            return HTMLResponse(status_code=422)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                # Sin sesión: 401 (error_conventions.md §3.3). Defensa en
                # profundidad; el middleware ya cubre estas rutas (hallazgo 26).
                return HTMLResponse(status_code=401)

            event_id = create_intake_event(
                connection,
                IntakeEventCreate(
                    user_id=int(user_id),
                    state=IntakeEventState.PLANNED,
                    name=clean_name or None,
                    meal_type=_default_meal_type_now(connection, int(user_id)),
                ),
            )

            headers = {"HX-Trigger": "addSuccess" if event_id else "addError"}
            return HTMLResponse("", headers=headers)
