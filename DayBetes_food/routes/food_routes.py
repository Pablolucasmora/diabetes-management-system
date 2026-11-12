from fasthtml.common import *
from datetime import datetime
from datetime import date
import json
import difflib
import logging
import re
import unicodedata
from urllib.parse import urlencode
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.food.food_main import food_main, plate_selector_options
from DayBetes_food.components.ui import render_fragment, render_page
from DayBetes_food.http_errors import app_error_response, request_id
from DayBetes_food.services.fridge import (
    create_fridge_container,
    list_fridge_items,
    store_in_fridge,
    store_recipe_in_fridge,
    take_from_fridge,
)
from DayBetes_food.services.intake_event import confirm_planned_event
from DayBetes_food.database.queries import (
    create_catalog_item,
    get_off_product_by_code,
    list_catalog_items,
    search_off_products,
    get_ciqual_food,
    search_ciqual_foods,
    archive_catalog_item,
    publish_catalog_item,
    unpublish_catalog_item,
    next_catalog_copy_name,
    create_manual_intake,
    list_manual_intakes,
    archive_manual_intake,
    publish_manual_intake,
    unpublish_manual_intake,
    next_manual_intake_copy_name,
    list_recipes,
    create_recipe,
    create_portion_detail,
    get_catalog_item,
    get_catalog_item_by_barcode,
    get_manual_intake,
    get_recipe,
    get_portion_detail,
    ensure_default_recipe_plate,
    create_recipe_plate,
    delete_recipe_plate,
    get_recipe_plate,
    list_recipe_plates,
    move_portion_to_recipe_plate,
    swap_recipe_plate_position,
    update_portion_flag,
    update_recipe_plate_name,
    list_viewable_recipe_portions,
    update_catalog_item,
    get_user_favorite_access,
    set_user_favorite,
    update_manual_intake,
    update_recipe,
    delete_recipe,
    create_food_brand,
    get_food_brand_id_by_label,
    get_food_brand_suggestions,
    get_subtype_suggestions,
    get_subtype_label,
    get_manual_origin_suggestions,
    get_consumed_food_usage_rankings,
    get_rescue_entries_suggestions,
    list_tags,
    get_system_tag,
    get_tag_by_name,
    create_tag,
    list_entry_tags,
    set_entry_tag,
    update_intake_event,
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
    get_fridge,
)
from DayBetes_food.domain.constants import (
    CLEAR,
    PathId,
    NOVA_MAX,
    NOVA_MIN,
    YUKA_MAX,
    YUKA_MIN,
    AmountInputUnit,
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodPhysicalState,
    GlycemicIndex,
    Nutriscore,
    NutrientEntryMode,
    PortionDestination,
    PrefillSource,
    FoodEntryType,
    PortionOrigin,
    StorageLocation,
    parse_enum,
    parse_optional_id,
)
from DayBetes_food.domain.nutrition import (
    NutrientValues,
    NumericRange,
    nutrients_from_smart_text,
    parse_number,
    parse_nutrient_input,
    parse_nutrients,
)
from DayBetes_food.domain.catalog import (
    CatalogItemCreate,
    CatalogItemRead,
    CatalogItemRequest,
    CatalogItemUpdate,
    parse_barcode,
    parse_prefill_reference,
    parse_catalog_name,
    parse_cooking_factor,
)
from DayBetes_food.domain.food_entry import FoodEntrySummary
from DayBetes_food.domain.food import (
    INITIAL_AMOUNT_WITHOUT_SERVING_G,
    parse_declared_confidence,
    parse_default_portion,
    parse_food_subtype,
)
from DayBetes_food.domain.manual_intake import (
    ManualIntakeCreate,
    ManualIntakeRead,
    ManualIntakeRequest,
    ManualIntakeUpdate,
    QuickAddRequest,
    parse_manual_intake_description,
    parse_manual_intake_name,
    parse_manual_intake_origin,
    parse_quick_add_weight,
    require_carbs,
    validate_ig_confidence,
)
from DayBetes_food.domain.portion_detail import (
    PortionDetailCreate,
    PortionDetailUpdate,
    amount_to_grams,
    parse_amount_grams,
)
from DayBetes_food.components.data_sources import ciqual_attribution, off_attribution
from DayBetes_food.domain.ciqual_food import parse_ciqual_code
from DayBetes_food.integrations.ciqual import prefill_from_ciqual_food, reliability_note
from DayBetes_food.integrations.open_food_facts import fetch_product_prefill, prefill_from_off_product
from DayBetes_food.components.food.foods import (
    FoodSectionsContent,
    FoodCard,
    FavoriteButton,
    meal_option_label,
    on_after,
)
from DayBetes_food.components.food.food_actions import (
    FOOD_ACTIONS_BODY_ID,
    FOOD_ACTIONS_STORE_MESSAGE_ID,
    FoodActionsStore,
    FoodActionsCopyConfirm,
    FoodActionsFavoriteConfirm,
    FoodActionsMenu,
    FoodActionsRecipes,
    FoodActionsRecipePlates,
    food_card_id,
)
from DayBetes_food.components.food.fridge import FridgeListContent, FridgeListOob
from DayBetes_food.components.modal import ModalFormError
from DayBetes_food.components.food.tags import EntryTags, system_tag_for_label
from DayBetes_food.components.food.rescue import (
    RescueForm,
    RescueLine,
    RescueOptions,
)
from DayBetes_food.components.food.foods import catalog_entry_view, manual_intake_entry_view, recipe_entry_view
from DayBetes_food.components.food.foods import (
    CONFIDENCE_LABELS,
    GLYCEMIC_INDEX_LABELS,
    MACROS_QUALITY_LABELS,
    WEIGHED_LABELS,
)
from DayBetes_food.components.food.foods import (
    CreateCatalogPage,
    ExternalFoodSection,
    ciqual_food_cards,
    off_product_cards,
    CreateManualPage,
    CreateRecipePage,
    EditCatalogPage,
    EditManualPage,
    EditRecipePage,
    FoodDetailPage,
    QuickAddPage,
    RecipeIngredientPickerCard,
    RecipeIngredientPickerPage,
    RecipeIngredientsBlock,
    RecipeSummaryOob,
    PlateSelector,
)
from DayBetes_food.database.connection import get_connection
from DayBetes_food.domain.constants import IntakeEventState, MealType, SystemTag
from DayBetes_food.domain.tag import TagCreate, parse_tag_name, tag_color_from_name
from DayBetes_food.domain.intake_event import INTAKE_EVENT_NAME_MAX_LENGTH, IntakeEventCreate, IntakeEventUpdate
from DayBetes_food.domain.intake_plate import IntakePlateCreate, auto_offset_minutes, derive_plate_name
from DayBetes_food.domain.recipe import (
    PortionPreparation,
    RecipeAddRequest,
    RecipeCreate,
    RecipeRead,
    RecipeRequest,
    RecipeUpdate,
    parse_recipe_add_servings,
    parse_recipe_meal_type,
    parse_recipe_extra_meal_types,
    parse_recipe_meal_types,
    parse_recipe_name,
    parse_recipe_notes,
    parse_recipe_servings,
)
from DayBetes_food.services.recipe import add_recipe_to_meal, copy_recipe, recipe_plates_with_portions
from DayBetes_food.domain.recipe_plate import parse_recipe_plate_name
from DayBetes_food.domain.fridge import FridgeContent, FridgeStoreCommand
from DayBetes_food.domain.portion_detail import portion_macro_amount
from DayBetes_food.components.food.recipe_add import RecipeAddForm
from DayBetes_food.components.stats.stats_shared import MEAL_TYPE_LABELS
from DayBetes_food.domain.meal_type_schedule import resolve_meal_type_for_time
from DayBetes_food.time_utils import local_naive_to_utc_aware, local_now, utc_now
from DayBetes_food.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)


def _default_meal_type_now(connection, user_id: int) -> MealType | None:
    """
    Automatic `meal_type` for an `intake_event` created without going through
    the cart (adding a food directly), from the current local time and the
    user's time slots (or the defaults if they have not customized them in
    /settings/meal_type_schedule).

    It is computed here, when the row is created, and not in the component
    that shows it: the `<select>` in `EventHeader` (cart_components.py) must
    be able to trust that `event.meal_type` already is the real value, never
    one it has to infer at render time (code_conventions.md §7.14, decision
    2026-09-11).
    """
    overrides = get_meal_type_schedule(connection, user_id)
    return resolve_meal_type_for_time(local_now().time(), overrides)


def _event_auto_offset_minutes(event_data) -> int | None:
    """Offset of a new plate (measurement_conventions.md §4.5, §4.6.2). From then
    on its portions inherit it, which avoids correcting them one by one."""
    return auto_offset_minutes(event_data.meal_time if event_data else None, utc_now())


def _resolve_event_plate(connection, user_id: int, event_id: int, plate_id: str, offset_minutes: int | None) -> int:
    """Plate a food added to an event goes to (§4.6.1, §7.7).

    - A specific id: that plate, checking inside the SQL that it belongs to
      the user and to the event (§5.3); the request's `event_id` is not proof.
    - `"0"`: the selector's `+ New plate` option, which creates the plate on the spot.
    - Empty or missing: the event's last plate and, if there is none, a first
      one created implicitly.

    Raises:
        NotFoundError: the plate does not exist, is not the user's or belongs to another event.
    """
    chosen = parse_optional_id(plate_id, "plate")
    if chosen:
        plate = get_intake_plate(connection, user_id, chosen)
        if plate.intake_event_id != int(event_id):
            raise NotFoundError(f"Intake plate {chosen} does not belong to event {event_id}")
        return plate.id
    if chosen == 0:
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


_NOVA_RANGE = NumericRange(NOVA_MIN, NOVA_MAX)
_YUKA_RANGE = NumericRange(YUKA_MIN, YUKA_MAX)


def _to_int(value: str):
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        return int(normalized)
    except (TypeError, ValueError):
        return None


_TYPED_AMOUNT_RANGE = NumericRange(0, 1_000_000)


def _parse_typed_amount(raw) -> float | None:
    """A typed amount through the common number parser (§7.5), or None if it is not
    one, so "1e3" or "1_0" are not amounts. Its unit and limits are checked after."""
    try:
        return parse_number(raw, "amount", _TYPED_AMOUNT_RANGE)
    except ValidationError:
        return None


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
    macros_quality,
    default_strictly_weighed,
    macros_confidence,
    favorite=None,
    smart_raw="",
    prefill_source="",
    prefill_source_id="",
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
    parsed_subtype = parse_food_subtype(subtype, required=True)
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
    parsed_macros_quality = _parse_optional_bool(macros_quality)
    parsed_default_strictly_weighed = _parse_optional_bool(default_strictly_weighed)
    parsed_macros_confidence = parse_declared_confidence(macros_confidence, field="macros_confidence")
    parsed_favorite = None if favorite is None else _parse_strict_bool(favorite)
    parsed_prefill_source, parsed_prefill_source_id = parse_prefill_reference(prefill_source, prefill_source_id)
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
        macros_quality=parsed_macros_quality,
        default_strictly_weighed=parsed_default_strictly_weighed,
        macros_confidence=parsed_macros_confidence,
        favorite=parsed_favorite,
        prefill_source=parsed_prefill_source,
        prefill_source_id=parsed_prefill_source_id,
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
        macros_quality=req.macros_quality,
        default_strictly_weighed=req.default_strictly_weighed,
        macros_confidence=req.macros_confidence,
        prefill_source=req.prefill_source,
        prefill_source_id=req.prefill_source_id,
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
        macros_quality=req.macros_quality,
        default_strictly_weighed=req.default_strictly_weighed,
        macros_confidence=req.macros_confidence,
    )


def _parse_optional_bool(raw: str | None) -> bool | None:
    """Tri-state select of the dish defaults (frontend §6): '' -> None
    ("unknown"); otherwise _parse_strict_bool (unknown value -> ValidationError, §7.6)."""
    return None if (raw or "").strip() == "" else _parse_strict_bool(raw)


def _parse_recipe_request(
    *, name, meal_type, extra_meal_types, notes, servings, favorite=None
) -> RecipeRequest:
    """The only parser of the recipe create and edit forms (§7.1, §7.11)."""
    main_meal_type = parse_recipe_meal_type(meal_type)
    return RecipeRequest(
        name=parse_recipe_name(name),
        meal_type=main_meal_type,
        extra_meal_types=parse_recipe_extra_meal_types(extra_meal_types, main_meal_type),
        notes=parse_recipe_notes(notes),
        servings=parse_recipe_servings(servings),
        favorite=None if favorite is None else _parse_strict_bool(favorite),
    )


_RECIPE_WITHOUT_INGREDIENTS = "This recipe has no ingredients yet."
_MEAL_CONFIRMED = "That meal has already been confirmed."


def _parse_recipe_add_request(form, recipe: RecipeRead) -> RecipeAddRequest:
    """The form of the step before adding a recipe (§7.1, §7.7, §7.8). The selectors
    use "0" for a new meal or plate. Amounts never come from the client (§7.13)."""
    portion_ids = form.getlist("portion_id")
    cookings = form.getlist("cooking")
    final_states = form.getlist("final_state")
    conservations = form.getlist("conservation")
    if not len(portion_ids) == len(cookings) == len(final_states) == len(conservations):
        raise ValidationError("The ingredients of the form are incomplete.")
    preparations = {}
    for raw_id, cooking, final_state, conservation in zip(portion_ids, cookings, final_states, conservations):
        portion_id = parse_optional_id(str(raw_id), "ingredient")
        if portion_id is None:
            raise ValidationError("Invalid ingredient.")
        preparations[portion_id] = PortionPreparation(
            cooking=parse_enum(CookingMethod, str(cooking), field="cooking"),
            conservation=parse_enum(ConservationMethod, str(conservation), field="conservation"),
            final_state=parse_enum(FoodPhysicalState, str(final_state), field="final_state"),
        )
    event_id = parse_optional_id(form.get("intake_event_id"), "meal") or None
    plate_id = parse_optional_id(form.get("plate_id"), "plate") or None
    return RecipeAddRequest(
        event_id=event_id,
        plate_id=plate_id if event_id else None,
        servings=parse_recipe_add_servings(form.get("servings")) if recipe.servings else None,
        preparations=preparations,
    )


def _parse_manual_intake_request(
    *,
    name,
    description,
    subtype,
    subtype__added,
    origin,
    default_portion,
    nutrient_mode,
    glycemic_index,
    ig_confidence,
    macros_confidence,
    macros_quality,
    default_strictly_weighed,
    favorite=None,
    smart_raw=None,
    **nutrient_fields,
) -> ManualIntakeRequest:
    """The only parser of the reusable-dish create and edit forms (§7.1, H10).

    `smart_raw` not None: the seven macros come from the smart-macros text and
    `nutrient_fields` only carries caffeine/alcohol (create form); None: the
    nine nutrients come from the visible fields (edit form). `nutrient_mode`
    says whether they are per 100 g or the total of one serving (measurement §5.4).
    """
    parsed_name = parse_manual_intake_name(name)
    parsed_description = parse_manual_intake_description(description)
    parsed_subtype = parse_food_subtype(subtype, required=False)
    subtype_is_new = _parse_strict_bool(subtype__added)
    parsed_origin = parse_manual_intake_origin(origin)  # free text, no "Add" (H7)
    parsed_portion = parse_default_portion(default_portion)
    mode = parse_enum(NutrientEntryMode, nutrient_mode, field="nutrient_mode")
    if mode is None:
        raise ValidationError(
            "Choose how the nutrients are entered.", fields={"nutrient_mode": "required"}
        )
    nutrients = parse_nutrient_input(
        mode, weight_g=parsed_portion, fields=nutrient_fields, smart_text=smart_raw
    )
    require_carbs(nutrients)
    parsed_glycemic_index = parse_enum(GlycemicIndex, glycemic_index, field="glycemic_index")
    parsed_ig_confidence = parse_declared_confidence(ig_confidence, field="ig_confidence")
    validate_ig_confidence(parsed_glycemic_index, parsed_ig_confidence)
    return ManualIntakeRequest(
        name=parsed_name,
        description=parsed_description,
        subtype=parsed_subtype,
        subtype_is_new=subtype_is_new,
        origin=parsed_origin,
        default_portion=parsed_portion,
        nutrients=nutrients,
        glycemic_index=parsed_glycemic_index,
        ig_confidence=parsed_ig_confidence,
        macros_confidence=parse_declared_confidence(macros_confidence, field="macros_confidence"),
        macros_quality=_parse_optional_bool(macros_quality),
        default_strictly_weighed=_parse_optional_bool(default_strictly_weighed),
        favorite=None if favorite is None else _parse_strict_bool(favorite),
    )


def _resolve_manual_subtype(connection, req: ManualIntakeRequest) -> str | None:
    """Same rule as catalog (_resolve_catalog_refs): the stored label by SQL
    lookup, or a new one only with Add (subtype__added). None stays None: the
    subtype of a dish is optional (decision 2026-10-09)."""
    if req.subtype is None:
        return None
    stored_subtype = get_subtype_label(connection, req.subtype)
    if stored_subtype is not None:
        return stored_subtype
    if req.subtype_is_new:
        return req.subtype
    raise ValidationError(
        "Invalid subtype. Use Add to create a new value.", fields={"subtype": "invalid"}
    )


def _manual_intake_create(req: ManualIntakeRequest, user_id: int, subtype) -> ManualIntakeCreate:
    return ManualIntakeCreate(
        created_by=user_id,
        origin_root_id=None,
        name=req.name,
        description=req.description,
        subtype=subtype,
        origin=req.origin,
        default_portion=req.default_portion,
        nutrients=req.nutrients,
        glycemic_index=req.glycemic_index,
        ig_confidence=req.ig_confidence,
        macros_confidence=req.macros_confidence,
        macros_quality=req.macros_quality,
        default_strictly_weighed=req.default_strictly_weighed,
    )


def _manual_intake_update(req: ManualIntakeRequest, subtype) -> ManualIntakeUpdate:
    return ManualIntakeUpdate(
        name=req.name,
        description=req.description,
        subtype=subtype,
        origin=req.origin,
        default_portion=req.default_portion,
        nutrients=req.nutrients,
        glycemic_index=req.glycemic_index,
        ig_confidence=req.ig_confidence,
        macros_confidence=req.macros_confidence,
        macros_quality=req.macros_quality,
        default_strictly_weighed=req.default_strictly_weighed,
    )


def _parse_quick_add_request(*, name, weight_g, smart_raw, notes) -> QuickAddRequest:
    """Quick-add form (§11.2.3): the smart-macros text is always the total of
    what was eaten (measurement §5.4); name, estimated weight and carbs are
    required."""
    weight = parse_quick_add_weight(weight_g)
    nutrients = parse_nutrient_input(
        NutrientEntryMode.PORTION_TOTAL, weight_g=weight, fields={}, smart_text=smart_raw
    )
    require_carbs(nutrients)
    return QuickAddRequest(
        name=parse_manual_intake_name(name),
        weight_g=weight,
        nutrients=nutrients,
        description=parse_manual_intake_description(notes),
    )


def _quick_add_create(req: QuickAddRequest, user_id: int) -> ManualIntakeCreate:
    """A quick add stores only what its form asks (§11.2.3): the weight becomes
    default_portion, default_strictly_weighed is FALSE because the weight is an
    estimate, and everything else stays NULL."""
    return ManualIntakeCreate(
        created_by=user_id,
        origin_root_id=None,
        name=req.name,
        description=req.description,
        subtype=None,
        origin=None,
        default_portion=req.weight_g,
        nutrients=req.nutrients,
        glycemic_index=None,
        ig_confidence=None,
        macros_confidence=None,
        macros_quality=None,
        default_strictly_weighed=False,
        is_quick_add=True,
    )


def _entry_tags_block(connection, user_id: int, kind: FoodEntryType, entry_id: int, open_panel: bool = False):
    """The tags block of a detail page, painted from what is stored (§9.4.1)."""
    return EntryTags(
        kind.value,
        entry_id,
        linked=list_entry_tags(connection, user_id, kind, entry_id),
        available=list_tags(connection, user_id),
        open_panel=open_panel,
    )


def _tag_id_for_name(connection, user_id: int, name: str) -> int:
    """The tag the user means by a typed name, inside the caller's transaction: a
    system tag by its label, one of their own by its name (ignoring case), or a new
    personal tag (§9.4.1). A tag of that name created meanwhile by another request
    is reused, not a 409: the insert runs in a savepoint (§6.2)."""
    system_key = system_tag_for_label(name)
    if system_key is not None:
        tag = get_system_tag(connection, system_key)
        if tag is None:
            raise NotFoundError("Tag not found.")
        return tag.id
    tag = get_tag_by_name(connection, user_id, name)
    if tag is not None:
        return tag.id
    try:
        with connection.transaction():
            return create_tag(
                connection, TagCreate(user_id=user_id, name=name, color=tag_color_from_name(name)), commit=False
            )
    except ConflictError:
        tag = get_tag_by_name(connection, user_id, name)
        if tag is None:
            raise
        return tag.id


def _get_rescue_food(connection, user_id: int, origin: PortionOrigin, entry_id: int):
    """A food or dish of the rescue pop-up, read with the SQL visibility rule.
    None if the user cannot see it."""
    if origin is PortionOrigin.CATALOG:
        return get_catalog_item(connection, user_id, entry_id)
    return get_manual_intake(connection, user_id, entry_id)


def _rescue_error(message: str):
    """Validation error of the rescue pop-up: 200 + message inside the form (§9.5)."""
    return render_fragment(ModalFormError(message))


def _portion_defaults(item: CatalogItemRead | ManualIntakeRead) -> dict:
    """measurement_conventions.md §6.11: a new portion of a food is born with
    the food's default_strictly_weighed, written when the portion is created
    (§7.14). macros_quality is not copied: the portion reads the food's live.
    Every route that creates a portion from a catalog food or a manual dish
    must use it."""
    return {"strictly_weighed": item.default_strictly_weighed}


def _detail_origin(
    connection, user_id: int, kind: FoodEntryType, entry_id: int, cooked_weight: bool, unit: AmountInputUnit
) -> CatalogItemRead | ManualIntakeRead:
    """The food or dish of a detail page, read with its visibility rule, and checked
    against what the form asks of it: a cooked weight needs a cooking factor
    (measurement §5.2, R4) and the `portion` unit needs a serving. Shared by
    /food/log and /food/fridge/store.

    Raises:
        NotFoundError: it does not exist or is not visible to the user.
        ValidationError: with the public message for the form.
    """
    if kind is FoodEntryType.CATALOG:
        item = get_catalog_item(connection, user_id, entry_id)
        if item is None:
            raise NotFoundError("Item not found.")
        # R4: the 422 applies only when the user ticks the box.
        if cooked_weight and item.cooking_factor is None:
            raise ValidationError("This food has no cooking factor, so it cannot be weighed cooked.")
        noun = "food"
    else:
        item = get_manual_intake(connection, user_id, entry_id)
        if item is None:
            raise NotFoundError("Item not found.")
        # measurement §5.2: a manual dish has no cooking factor; the box is never
        # turned into False silently (§7.2).
        if cooked_weight:
            raise ValidationError("Cooked weight only applies to catalog foods.")
        noun = "dish"
    if unit is AmountInputUnit.PORTION and item.default_portion is None:
        raise ValidationError(f"This {noun} has no serving. Use grams, lb or oz.")
    return item


def _resolve_target_event(connection, user_id: int, intake_event_id: str) -> tuple[int, bool]:
    """Planned event a food goes to, and whether it was created now: the chosen one
    (checked in SQL, NotFoundError or ConflictError otherwise) or a new one with the
    automatic meal_type (§7.14). Same logic as /food/log and /add_food."""
    chosen = parse_optional_id(intake_event_id, "meal")
    if chosen:
        return get_planned_intake_event(connection, user_id, chosen), False
    event_id = create_intake_event(
        connection,
        IntakeEventCreate(
            user_id=user_id,
            state=IntakeEventState.PLANNED,
            meal_type=_default_meal_type_now(connection, user_id),
        ),
        commit=False,
    )
    return event_id, True


def _meal_created_event(connection, user_id: int, event_id: int) -> dict:
    """`mealCreated` (HX-Trigger, frontend §7.7): the page adds the new meal to its
    meal selector and leaves it chosen, so the next add goes to the same meal
    instead of creating another one."""
    event = get_intake_event(connection, user_id, event_id)
    return {"mealCreated": {"id": event_id, "label": meal_option_label(event)}}


def _prefill_view(prefill, barcode: str, source_id: str, source: PrefillSource = PrefillSource.OPEN_FOOD_FACTS) -> dict:
    """FoodPrefill -> presentation dict of the create form."""
    nutrients = prefill.nutrients

    def text_or_empty(value):
        return "" if value is None else value

    return {
        "barcode": barcode,
        "prefill_source": source.value,
        "prefill_source_id": source_id,
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
        ("Macros quality", MACROS_QUALITY_LABELS.get(item.macros_quality)),
        ("Weighed by default", WEIGHED_LABELS.get(item.default_strictly_weighed)),
        ("Macros confidence", CONFIDENCE_LABELS.get(item.macros_confidence)),
    ]
    info_rows = [(label, fmt(value)) for label, value in candidates if value is not None]
    return {
        "subtitle": item.brand or "No brand",
        "default_amount_g": item.default_portion,
        "per100": per100,
        "info_rows": info_rows,
    }


def _manual_intake_detail_summary(item: ManualIntakeRead) -> dict:
    """Presentation summary of a ManualIntakeRead (H2), like _catalog_detail_summary.

    `default_amount_g` may be None (no serving). `per100` keeps None: an unknown
    macro is never shown as 0 (measurement §2, code_conventions.md §10.3).
    `info_rows` shows 0 as 0 and omits a row whose value is None."""
    def fmt(value: float) -> str:
        return f"{value:g}"

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
        ("Description", item.description),
        ("Subtype", item.subtype),
        ("Default serving", None if item.default_portion is None else f"{fmt(item.default_portion)} g"),
        ("Glycemic index", GLYCEMIC_INDEX_LABELS.get(item.glycemic_index)),
        ("IG confidence", CONFIDENCE_LABELS.get(item.ig_confidence)),
        ("Macros confidence", CONFIDENCE_LABELS.get(item.macros_confidence)),
        ("Macros quality", MACROS_QUALITY_LABELS.get(item.macros_quality)),
        ("Weighed by default", WEIGHED_LABELS.get(item.default_strictly_weighed)),
        ("Caffeine", None if item.caffeine is None else f"{fmt(item.caffeine)} mg/100 g"),
        ("Alcohol", None if item.alcohol is None else f"{fmt(item.alcohol)} g/100 g"),
    ]
    return {
        "subtitle": item.origin or "No origin",
        "default_amount_g": item.default_portion,
        "per100": per100,
        "info_rows": [(label, value) for label, value in candidates if value is not None],
    }


_RECIPE_MACROS = ("calories", "carbs", "sugars", "fats", "saturated", "proteins", "fiber")


def _recipe_summary(entry: dict, portions: list) -> dict:
    """Totals of a recipe, as the cart computes them (measurement §5.2, §6.9.4): a
    cooked weight is converted, and an unknown macro is not 0. Without ingredients
    there is no amount to show."""
    total_amount = sum(float(row.amount) for row in portions)
    per100 = {}
    partial = []
    for macro in _RECIPE_MACROS:
        known = [(row, value) for row in portions if (value := _macro_value(row, macro)) is not None]
        if not known or total_amount <= 0:
            per100[f"{macro}_100g"] = None
            continue
        if len(known) < len(portions):
            partial.append(macro)
        grams = sum(portion_macro_amount(row) * float(value) / 100.0 for row, value in known)
        per100[f"{macro}_100g"] = grams * 100.0 / total_amount
    servings = entry.get("servings")
    return {
        "subtitle": "Recipe",
        "default_amount_g": total_amount or None,
        "per100": per100,
        "partial_macros": partial,
        "info_rows": [
            ("Meal type", MEAL_TYPE_LABELS.get(entry.get("meal_type"), "")),
            ("Also for", ", ".join(MEAL_TYPE_LABELS.get(value, value) for value in entry.get("extra_meal_types") or ())),
            ("Ingredients", str(len(portions))),
            ("Recipe amount", f"{total_amount:.1f} g" if total_amount > 0 else ""),
            ("Servings", str(servings) if servings else ""),
            ("Serving amount", f"{total_amount / servings:.1f} g" if servings and total_amount > 0 else ""),
        ],
    }


def _sorted_food_entries(catalog_items, manual_items, recipes, viewer_user_id: int | None = None):
    def _is_owned(entry_type: str, item: dict) -> bool:
        if not viewer_user_id:
            return False
        return item.get("created_by") == int(viewer_user_id)

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
    return item.get("created_by") == int(viewer_user_id)


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
    manual_items = (
        [
            manual_intake_entry_view(item)
            for item in list_manual_intakes(connection, int(viewer_user_id), search=search_value)
        ]
        if viewer_user_id
        else []
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
    manual_items = (
        [
            manual_intake_entry_view(item)
            for item in list_manual_intakes(connection, int(viewer_user_id), search=search_value)
        ]
        if viewer_user_id
        else []
    )
    if not viewer_user_id:
        return []
    recipes = _recipe_views(connection, viewer_user_id, search=search_value)

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
            candidates.append(item.get("barcode") or "")
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


def _recipe_views(connection, user_id, **filters) -> list[dict]:
    """Recipes the viewer may see, for the shared food components. Without a
    session there are none: the middleware already requires one."""
    if not user_id:
        return []
    return [recipe_entry_view(item) for item in list_recipes(connection, int(user_id), **filters)]


def _recipes_entries(connection, search: str = "", recipes_mode: str = "mine", meal_types=()) -> list[dict]:
    user_id = get_current_user_id()
    filters = {"search": (search or "").strip() or None, "meal_types": meal_types}
    if (recipes_mode or "mine").strip().lower() == "discover":
        recipes = _recipe_views(connection, user_id, others_only=True, **filters)
    else:
        recipes = _recipe_views(connection, user_id, owned_only=True, **filters)
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


def _editable_recipe(connection, user_id, recipe_id: int) -> RecipeRead | None:
    """The recipe if this user can edit it. None covers "no session", "does not
    exist" and "not yours": ingredient routes answer them all with 404 (§5.4)."""
    if not user_id:
        return None
    recipe = get_recipe(connection, int(user_id), recipe_id)
    return recipe if recipe is not None and recipe.can_edit else None


def _recipe_portion(connection, user_id: int, recipe_id: int, portion_id: int):
    """An ingredient of that recipe of the user, or None (§5.4)."""
    try:
        portion = get_portion_detail(connection, user_id, portion_id)
    except NotFoundError:
        return None
    if portion.destination is not PortionDestination.RECIPE or int(portion.destination_id) != recipe_id:
        return None
    return portion


def _add_ingredient(connection, user_id: int, recipe_id: int, plate_id: int | None, origin: PortionOrigin, item) -> None:
    """A food into a plate of a recipe, or its last plate. No serving -> the initial
    100 g of a one-click add (R3). Same preparation in that plate -> the amounts add
    up in the index, and the row that was there keeps its flags (§4.6.4, §4.7)."""
    target_plate_id = plate_id or ensure_default_recipe_plate(connection, user_id, recipe_id, commit=False)
    create_portion_detail(
        connection,
        user_id,
        PortionDetailCreate(
            origin=origin,
            origin_id=item.id,
            destination=PortionDestination.RECIPE,
            destination_id=recipe_id,
            recipe_plate_id=target_plate_id,
            amount=item.default_portion if item.default_portion is not None else INITIAL_AMOUNT_WITHOUT_SERVING_G,
            **_portion_defaults(item),
        ),
        commit=False,
    )


def _recipe_block_response(connection, user_id: int, recipe_id: int):
    """The ingredients block with the summary out of band: whatever changes the
    ingredients repaints everything that depends on them (frontend §6)."""
    recipe = get_recipe(connection, user_id, recipe_id)
    portions = list_viewable_recipe_portions(connection, user_id, recipe_id)
    plates = list_recipe_plates(connection, user_id, recipe_id)
    summary = _recipe_summary(recipe_entry_view(recipe), portions)
    return render_fragment(
        (RecipeIngredientsBlock(recipe_id, portions, plates, recipe.can_edit), *RecipeSummaryOob(recipe_id, summary))
    )


def _filtered_entries(
    connection,
    search: str = "",
    filter_value: str = "all",
    entry_type: str | None = None,
):
    user_id = get_current_user_id()
    has_search = bool((search or "").strip())

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

    def _manual(search_value=None, *, favorites_only=False, include_retained=False, owned_only=False):
        # Same contract as _catalog: visibility in SQL, never quick adds (§11.2.3).
        if not user_id:
            return []
        return [
            manual_intake_entry_view(item)
            for item in list_manual_intakes(
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
                manual_items = _manual(search or None)
            else:
                manual_items = _unique_by_id(
                    _manual(favorites_only=True, include_retained=True) + _manual(owned_only=True)
                )
        entries = _sorted_food_entries(catalog_items, manual_items, [], viewer_user_id=user_id)
    elif filter_value == "favs":
        selected_types = {"catalog", "manual_intake", "recipe"} if entry_type is None else {entry_type}
        catalog_items = (
            _catalog(search or None, favorites_only=True, include_retained=True)
            if "catalog" in selected_types
            else []
        )
        manual_items = (
            _manual(search or None, favorites_only=True, include_retained=True)
            if "manual_intake" in selected_types
            else []
        )
        recipes = (
            _recipe_views(connection, user_id, search=search or None, favorites_only=True)
            if "recipe" in selected_types
            else []
        )
        entries = _sorted_food_entries(catalog_items, manual_items, recipes, viewer_user_id=user_id)
    else:
        if has_search:
            catalog_items = _catalog(search or None)
            manual_items = _manual(search or None)
            recipes = _recipe_views(connection, user_id, search=search or None)
        else:
            catalog_items = _unique_by_id(
                _catalog(favorites_only=True, include_retained=True) + _catalog(owned_only=True)
            )
            manual_items = _unique_by_id(
                _manual(favorites_only=True, include_retained=True) + _manual(owned_only=True)
            )
            recipes = _unique_by_id(
                _recipe_views(connection, user_id, favorites_only=True) + _recipe_views(connection, user_id, owned_only=True)
            )
        entries = _sorted_food_entries(catalog_items, manual_items, recipes, viewer_user_id=user_id)

    return entries



_UNKNOWN_ENTRY_TYPE = "Unknown food type."

# Not found, and cannot be added (retained), per food type.
_FAVORITE_MESSAGES = {
    FoodEntryType.CATALOG: ("Food not found.", "Archived or unpublished foods cannot be added to favorites."),
    FoodEntryType.MANUAL_INTAKE: ("Dish not found.", "Archived or unpublished dishes cannot be added to favorites."),
    FoodEntryType.RECIPE: ("Recipe not found.", "Unpublished recipes cannot be added to favorites."),
}


def _parse_food_entry_type(raw: str) -> FoodEntryType | None:
    """The food type of a Food URL, or None when it is not one. The route
    answers None as a validation_error (422, code_conventions.md §7.7)."""
    try:
        return FoodEntryType(raw)
    except ValueError:
        return None


def _food_entry_summary(connection, user_id: int, entry_type: FoodEntryType, entry_id: int) -> FoodEntrySummary | None:
    """What the actions pop-up of a Food row shows (frontend_conventions.md
    §9.3.1), with the same visibility and permission as its detail page.
    None if the user cannot see it."""
    if entry_type is FoodEntryType.CATALOG:
        item = get_catalog_item(connection, user_id, entry_id)
        if item is None:
            return None
        return FoodEntrySummary(
            name=item.name,
            subtitle=(item.brand or "").strip(),
            can_edit=item.can_edit,
            default_portion=item.default_portion,
        )
    if entry_type is FoodEntryType.MANUAL_INTAKE:
        manual_item = get_manual_intake(connection, user_id, entry_id)
        if manual_item is None:
            return None
        return FoodEntrySummary(
            name=manual_item.name,
            subtitle=(manual_item.origin or "").strip(),
            can_edit=manual_item.can_edit,
            default_portion=manual_item.default_portion,
        )
    recipe = get_recipe(connection, user_id, entry_id)
    if recipe is None:
        return None
    return FoodEntrySummary(name=recipe.name, subtitle="Recipe", can_edit=recipe.can_edit)


def _store_error(request: Request, text: str):
    """Form message of /food/fridge/store: solid inside the actions pop-up (frontend
    §8), the page's own message on the food's page. htmx names the target."""
    if request.headers.get("HX-Target") == FOOD_ACTIONS_STORE_MESSAGE_ID:
        return render_fragment(ModalFormError(text))
    return _error_msg(text)


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
SEARCH_PAGE_SIZE = 8  # Short, so the Open Food Facts section stays close (frontend §9.3).


def _search_load_more_node(
    search: str,
    filter_value: str,
    search_mode: str,
    food_mode: str,
    favs_mode: str,
    recipes_mode: str,
    meal_type: str,
    next_page: int,
):
    query = urlencode({
        "search": search,
        "filter": filter_value,
        "search_mode": search_mode,
        "food_mode": food_mode,
        "favs_mode": favs_mode,
        "recipes_mode": recipes_mode,
        "meal_type": meal_type,
        "page": next_page,
    })
    if search:
        # A button, not on scroll: below it comes the Open Food Facts section,
        # which automatic loading would keep pushing down (frontend §9.3).
        return Button(
            "Load more",
            type="button",
            hx_get=f"/food/list?{query}",
            hx_swap="outerHTML",
            hx_target="this",
            hx_disabled_elt="this",
            data_skip_page_loading="true",
            cls="web_button rounded-full px-4 py-1.5 mt-1 text-xs font-semibold text-muted",
        )
    return Div(
        "Loading more...",
        hx_get=f"/food/list?{query}",
        hx_trigger="revealed",
        hx_swap="outerHTML",
        hx_target="this",
        data_skip_page_loading="true",
        cls="w-full text-center text-xs text-gray-500 py-2",
    )


def _recipe_query(recipe_id: int | None, recipe_plate_id: int | None) -> str:
    """What a result of the ingredient search carries to its create form (§9.7)."""
    if recipe_id is None:
        return ""
    return "&" + urlencode({"add_to_recipe": recipe_id, "recipe_plate_id": recipe_plate_id or ""})


def _external_load_more(source: PrefillSource, search: str, next_page: int, recipe_query: str = ""):
    query = recipe_query.lstrip("&") + "&" * bool(recipe_query) + urlencode({"source": source.value, "search": search, "page": next_page})
    return Button(
        "Load more",
        type="button",
        hx_get=f"/food/list/external?{query}",
        hx_swap="outerHTML",
        hx_target="this",
        hx_disabled_elt="this",
        data_skip_page_loading="true",
        cls="web_button rounded-full px-4 py-1.5 mt-1 text-xs font-semibold text-muted",
    )


def _external_page(connection, user_id: int, source: PrefillSource, search: str, page: int, recipe_query: str = ""):
    """(cards, next page's button) of one source. One row more than a page tells
    whether there is a next one."""
    search_fn, cards_fn = (
        (search_ciqual_foods, ciqual_food_cards)
        if source is PrefillSource.CIQUAL
        else (search_off_products, off_product_cards)
    )
    rows = search_fn(
        connection, user_id, search, limit=SEARCH_PAGE_SIZE + 1, offset=(page - 1) * SEARCH_PAGE_SIZE
    )
    load_more = _external_load_more(source, search, page + 1, recipe_query) if len(rows) > SEARCH_PAGE_SIZE else None
    return cards_fn(rows[:SEARCH_PAGE_SIZE], recipe_query), load_more


def _recipe_ingredient_nodes(
    connection, user_id: int, recipe: RecipeRead, *, search: str, filter_value: str, page: int, recipe_plate_id: int | None
) -> list:
    """One page of the ingredient search (frontend §9.7): the same lists as Food, without
    recipes, and on the first page of a search the external sources too."""
    entries = [
        entry
        for entry in _filtered_entries(connection, search=search, filter_value=filter_value)
        if entry.get("entry_type") != FoodEntryType.RECIPE.value
    ]
    start = (page - 1) * SEARCH_PAGE_SIZE
    nodes = [
        RecipeIngredientPickerCard(entry, recipe.id, recipe.name, recipe_plate_id)
        for entry in entries[start : start + SEARCH_PAGE_SIZE]
    ]
    if len(entries) > start + SEARCH_PAGE_SIZE:
        query = urlencode(
            {"search": search, "filter": filter_value, "recipe_plate_id": recipe_plate_id or "", "page": page + 1}
        )
        nodes.append(
            Button(
                "Load more",
                type="button",
                hx_get=f"/food/recipe/{recipe.id}/ingredients/list?{query}",
                hx_swap="outerHTML",
                hx_target="this",
                hx_disabled_elt="this",
                data_skip_page_loading="true",
                cls="web_button rounded-full px-4 py-1.5 mt-1 text-xs font-semibold text-muted",
            )
        )
    if page == 1 and search and filter_value == "food":
        recipe_query = _recipe_query(recipe.id, recipe_plate_id)
        nodes += ExternalFoodSection(
            "From Ciqual",
            *_external_page(connection, user_id, PrefillSource.CIQUAL, search, 1, recipe_query),
            ciqual_attribution(),
        )
        nodes += ExternalFoodSection(
            "From Open Food Facts",
            *_external_page(connection, user_id, PrefillSource.OPEN_FOOD_FACTS, search, 1, recipe_query),
            off_attribution(),
        )
    return nodes or [H2("No items", cls="text-gray-600")]


def setup_food_routes(rt):
    
    @rt("/food")
    def get(request, filter: str = ""):
        """`filter=fridge` opens the Fridge pill (the From fridge button of the home
        page, frontend §9.2); any other value is a 422 (code_conventions §7.7)."""
        selected = (filter or "all").strip()
        if selected not in ("all", "fridge"):
            raise ValidationError("Unknown Food list.", fields={"filter": "invalid"})
        return render_page(request, lambda connection: food_main(connection, selected))

    @rt("/food/create/catalog/form")
    def get(
        request: Request,
        barcode: str = "",
        existing_id: str = "",
        ciqual: str = "",
        add_to_recipe: str = "",
        recipe_plate_id: str = "",
    ):
        clean = (barcode or "").strip()
        target_recipe_id = parse_optional_id(add_to_recipe, "recipe")
        target_plate_id = parse_optional_id(recipe_plate_id, "plate")
        ciqual_food = None
        ciqual_code = parse_ciqual_code(ciqual)
        if ciqual_code is not None:
            with get_connection() as connection:
                ciqual_food = get_ciqual_food(connection, ciqual_code)
            if ciqual_food is None:
                raise NotFoundError("Ciqual food not found.")
        try:
            valid_barcode = parse_barcode(clean) if clean else None
            barcode_notice = None
        except ValidationError:
            valid_barcode, barcode_notice = None, "Invalid barcode: it must contain only digits (8 to 48)."
        prefill, off_notice, prefill_source_id = None, None, None
        local_product = None
        if valid_barcode:
            with get_connection() as connection:
                local_product = get_off_product_by_code(connection, valid_barcode)
        if local_product:
            prefill = prefill_from_off_product(valid_barcode, local_product)
            prefill_source_id = local_product.code
        elif valid_barcode:
            # Not in the local copy, which has a date and a scope: the API may
            # still know it (measurement §12.2).
            try:
                prefill = fetch_product_prefill(valid_barcode)
                prefill_source_id = valid_barcode
            except ExternalServiceError as error:
                # str(error) is the adapter's internal reason (off_network_error,
                # off_status...), never user data (error_conventions.md §10.3).
                logger.warning(
                    "Open Food Facts lookup failed",
                    exc_info=error,
                    extra={
                        "error_code": error.code,
                        "reason": str(error),
                        "request_id": request_id(request),
                    },
                )
                off_notice = "Product data could not be loaded. You can fill the form by hand."
        existing_item_id = parse_optional_id(existing_id, "food")
        user_id = get_current_user_id()
        with get_connection() as connection:
            if valid_barcode and not existing_item_id and user_id:
                existing = get_catalog_item_by_barcode(connection, int(user_id), valid_barcode)
                existing_item_id = existing.id if existing else None
            # Autocomplete only; validation is SQL (F4.1).
            brands = get_food_brand_suggestions(connection, search="", limit=500)
            subtypes = get_subtype_suggestions(connection, search="", limit=500)
        if valid_barcode and prefill is None and off_notice is None and not existing_item_id:
            off_notice = "Product not found. You can fill the form by hand."
        prefill_view = _prefill_view(prefill, valid_barcode, prefill_source_id) if prefill else {"barcode": clean}
        if ciqual_food:
            prefill = prefill_from_ciqual_food(ciqual_food)
            prefill_view = _prefill_view(prefill, "", str(ciqual_food.code), PrefillSource.CIQUAL)
        subtype_prefill = (prefill_view.get("subtype") or "").strip()
        if subtype_prefill:
            prefill_view["subtype"] = _closest_option(subtype_prefill, subtypes)
            # A value the prefill brought counts as added: the user reviews it
            # before saving, and without this the form rejects it (measurement §12.2).
            prefill_view["subtype_is_new"] = prefill_view["subtype"] not in subtypes
        brand_prefill = (prefill_view.get("brand") or "").strip()
        if brand_prefill:
            prefill_view["brand"] = _closest_option(brand_prefill, brands)
            prefill_view["brand_is_new"] = prefill_view["brand"] not in brands
        return render_page(
            request,
            lambda _: CreateCatalogPage(
                brand_options=brands,
                subtype_options=subtypes,
                prefill=prefill_view,
                existing_item_id=existing_item_id,
                off_notice=off_notice,
                barcode_notice=barcode_notice,
                alcohol_source_note=prefill.alcohol_source_note if prefill else None,
                off_prefill_barcode=valid_barcode if prefill and not ciqual_food else None,
                ciqual_note=reliability_note(ciqual_food) if ciqual_food else None,
                add_to_recipe=(target_recipe_id, target_plate_id) if target_recipe_id else None,
            ),
            show_cart=False,
        )

    @rt("/food/create/manual_intake/form")
    def get(request: Request):
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        with get_connection() as connection:
            subtypes = get_subtype_suggestions(connection, search="", limit=500)
            origins = get_manual_origin_suggestions(connection, int(user_id), limit=500)
        return render_page(
            request,
            lambda _: CreateManualPage(subtype_options=subtypes, origin_options=origins),
            show_cart=False,
        )

    @rt("/food/create/recipe/form")
    def get(request: Request):
        return render_page(request, lambda _: CreateRecipePage(), show_cart=False)

    @rt("/food/rescue/form")
    def get(request: Request, kind: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            tab = parse_enum(SystemTag, kind, field="kind") or SystemTag.RESCUE
        except ValidationError as error:
            return app_error_response(request, error, str(error))
        # The initial food list travels with the form: a single response,
        # so the pop-up opens complete instead of growing twice (§9.6).
        with get_connection() as connection:
            rows = get_rescue_entries_suggestions(connection, int(user_id), tab, search="", limit=30)
        now = local_now()
        return render_fragment(RescueForm(now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), rows, tab))

    @rt("/food/rescue/options")
    def get(request: Request, q: str = "", kind: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            tab = parse_enum(SystemTag, kind, field="kind") or SystemTag.RESCUE
        except ValidationError as error:
            return app_error_response(request, error, str(error))
        search = (q or "").strip()
        with get_connection() as connection:
            rows = get_rescue_entries_suggestions(connection, int(user_id), tab, search=search, limit=30)
        return render_fragment(RescueOptions(rows, searching=bool(search), kind=tab))

    @rt("/food/rescue/line/{entry_type}/{entry_id}")
    def get(request: Request, entry_type: str, entry_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            origin = PortionOrigin(entry_type)
        except ValueError:
            # Value outside the closed set of the URL: validation_error (§7.7).
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        with get_connection() as connection:
            item = _get_rescue_food(connection, int(user_id), origin, entry_id)
        if item is None:
            return app_error_response(request, NotFoundError, "Food not found.")
        return render_fragment(
            RescueLine(origin.value, int(item.id), item.name, item.default_portion)
        )

    @rt("/food/rescue/log")
    async def post(request: Request):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        form = await request.form()
        entry_types = form.getlist("entry_type")
        entry_ids = form.getlist("entry_id")
        amount_values = form.getlist("amount_value")
        amount_units = form.getlist("amount_unit")
        if not entry_types:
            return _rescue_error("Choose at least one food.")
        if not (len(entry_types) == len(entry_ids) == len(amount_values) == len(amount_units)):
            return _rescue_error("The rescue lines are incomplete.")

        meal_t = _parse_hhmm(str(form.get("meal_hour") or ""))
        try:
            meal_d = date.fromisoformat(str(form.get("meal_date") or "").strip())
        except ValueError:
            meal_d = None
        if meal_t is None or meal_d is None:
            return _rescue_error("Choose a valid date and time.")
        # Any moment is accepted, also a future one (§9.6, decision 2026-09-06).
        meal_time = local_naive_to_utc_aware(datetime.combine(meal_d, meal_t))
        # Rescue by default; any other type for what is not a rescue (§9.6).
        try:
            meal_type = parse_enum(MealType, str(form.get("meal_type") or ""), field="meal_type")
        except ValidationError:
            return _rescue_error("That meal type does not exist.")
        if meal_type is None:
            return _rescue_error("Choose the meal type.")

        # HTTP payload validation that does not depend on the database (§7.1).
        lines = []
        for raw_type, raw_id, raw_value, raw_unit in zip(entry_types, entry_ids, amount_values, amount_units):
            try:
                origin = PortionOrigin(str(raw_type).strip())
                unit = AmountInputUnit(str(raw_unit).strip())
            except ValueError:
                return _rescue_error("A rescue line is not valid.")
            origin_id = _to_int(str(raw_id))
            value = _to_float(str(raw_value))
            if not origin_id:
                return _rescue_error("A rescue line is not valid.")
            if unit is AmountInputUnit.PERCENT:
                return _rescue_error("Use grams, servings, lb or oz.")
            if value is None:
                return _rescue_error("Enter an amount for every food.")
            lines.append((origin, int(origin_id), value, unit))

        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            # The foods are read with the SQL visibility rule, and the serving
            # comes from the database, never from the form (§7.13).
            portions = []
            for origin, origin_id, value, unit in lines:
                item = _get_rescue_food(connection, int(user_id), origin, origin_id)
                if item is None:
                    return app_error_response(request, NotFoundError, "Rescue food not found.")
                try:
                    grams = parse_amount_grams(amount_to_grams(value, unit, item.default_portion))
                except ValidationError:
                    if unit is AmountInputUnit.PORTION and item.default_portion is None:
                        return _rescue_error(f"{item.name} has no serving. Use grams, lb or oz.")
                    return _rescue_error("Each amount must be greater than 0 g and at most 100000 g.")
                portions.append((origin, origin_id, grams, _portion_defaults(item)))

            try:
                with connection.transaction():
                    event_id = create_intake_event(
                        connection,
                        IntakeEventCreate(
                            user_id=int(user_id),
                            state=IntakeEventState.PLANNED,
                            meal_type=meal_type,
                            meal_time=meal_time,
                        ),
                        commit=False,
                    )
                    # This pop-up never logs insulin, whatever the meal type (§9.6): without this the
                    # column DEFAULT TRUE would create an automatic injection.
                    update_intake_event(
                        connection,
                        user_id=int(user_id),
                        event_id=int(event_id),
                        data=IntakeEventUpdate(insulin_dose=False),
                        commit=False,
                    )
                    # A single plate with offset 0 (measurement_conventions.md §4.6.1).
                    plate_id = create_intake_plate(
                        connection,
                        IntakePlateCreate(intake_event_id=int(event_id), offset_minutes=0),
                        commit=False,
                    )
                    for origin, origin_id, grams, defaults in portions:
                        # A repeated food with the same preparation is merged (§4.6.4).
                        create_portion_detail(
                            connection,
                            int(user_id),
                            PortionDetailCreate(
                                origin=origin,
                                origin_id=origin_id,
                                destination=PortionDestination.INTAKE_EVENT,
                                destination_id=int(event_id),
                                amount=grams,
                                offset_minutes=0,
                                plate_id=plate_id,
                                **defaults,
                            ),
                            commit=False,
                        )
                    # Same confirm as the cart, at 100 % (§6.9.1).
                    confirm_planned_event(connection, int(user_id), int(event_id))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Rescue food not found.")
            except ConflictError:
                return app_error_response(request, ConflictError, "The rescue could not be registered.")
            except ValidationError:
                return _rescue_error("The total amount must be at most 100000 g.")
        return HTMLResponse("", headers={"HX-Trigger": json.dumps({"rescueRegistered": {"meal_type": meal_type.value}})})

    # Tags of a food, dish or recipe on its detail page (frontend_conventions.md §9.4.1).

    @rt("/food/tags/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: PathId, tag_id: str = "", linked: str = "", open: str = ""):
        """Leaves the tag on the entry as asked: repeating it is a no-op (§6.3)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        # Required: an empty value would read as False and take the tag off (§7.4, §7.6).
        if not linked.strip():
            return app_error_response(request, ValidationError, "Say whether to add or remove the tag.")
        try:
            parsed_tag_id = parse_optional_id(tag_id, "tag_id")
            wanted = _parse_strict_bool(linked)
            keep_open = _parse_strict_bool(open)
        except ValidationError as error:
            return app_error_response(request, error, str(error))
        if parsed_tag_id is None:
            return app_error_response(request, ValidationError, "Choose a tag.")
        with get_connection() as connection:
            try:
                set_entry_tag(connection, int(user_id), kind, entry_id, parsed_tag_id, wanted)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That food or tag is not available.")
            return render_fragment(_entry_tags_block(connection, int(user_id), kind, entry_id, keep_open))

    @rt("/food/tags/{entry_type}/{entry_id}/new")
    def post(request: Request, entry_type: str, entry_id: PathId, name: str = ""):
        """Puts a tag on the entry by its name: a system tag or one of the user's is
        reused, otherwise a personal tag is created. Repeating it is a no-op (§6.3)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        try:
            clean_name = parse_tag_name(name)
        except ValidationError as error:
            return app_error_response(request, error, str(error))
        with get_connection() as connection:
            try:
                with connection.transaction():
                    tag_id = _tag_id_for_name(connection, int(user_id), clean_name)
                    set_entry_tag(connection, int(user_id), kind, entry_id, tag_id, True, commit=False)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That food is not available.")
            return render_fragment(_entry_tags_block(connection, int(user_id), kind, entry_id, True))

    @rt("/food/actions/{entry_type}/{entry_id}")
    def get(request: Request, entry_type: str, entry_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        with get_connection() as connection:
            entry = _food_entry_summary(connection, int(user_id), kind, entry_id)
        if entry is None:
            return app_error_response(request, NotFoundError, "Food not found.")
        return render_fragment(FoodActionsMenu(kind, entry_id, entry))

    @rt("/food/actions/{entry_type}/{entry_id}/recipes")
    def get(request: Request, entry_type: str, entry_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        if kind is FoodEntryType.RECIPE:
            return app_error_response(request, ValidationError, "A recipe cannot be an ingredient of another recipe.")
        with get_connection() as connection:
            entry = _food_entry_summary(connection, int(user_id), kind, entry_id)
            if entry is None:
                return app_error_response(request, NotFoundError, "Food not found.")
            # Only the user's own recipes: the only ones they can edit.
            recipes = list_recipes(connection, int(user_id), owned_only=True)
            several_plates = {
                recipe.id for recipe in recipes if len(list_recipe_plates(connection, int(user_id), recipe.id)) > 1
            }
        return render_fragment(FoodActionsRecipes(kind, entry_id, entry, recipes, several_plates))

    @rt("/food/actions/{entry_type}/{entry_id}/recipes/{recipe_id}/plates")
    def get(request: Request, entry_type: str, entry_id: PathId, recipe_id: PathId):
        """Which plate, for a recipe with several (frontend §9.3.1)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None or kind is FoodEntryType.RECIPE:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        with get_connection() as connection:
            entry = _food_entry_summary(connection, int(user_id), kind, entry_id)
            recipe = _editable_recipe(connection, user_id, recipe_id)
            if entry is None or recipe is None:
                return app_error_response(request, NotFoundError, "Food not found.")
            portions = list_viewable_recipe_portions(connection, int(user_id), recipe_id)
            plates = [
                (
                    plate.id,
                    plate.name or derive_plate_name(
                        [row.source.name for row in portions if row.recipe_plate_id == plate.id]
                    ),
                )
                for plate in list_recipe_plates(connection, int(user_id), recipe_id)
            ]
        return render_fragment(FoodActionsRecipePlates(kind, entry_id, entry, recipe, plates))

    @rt("/food/actions/{entry_type}/{entry_id}/fridge")
    def get(request: Request, entry_type: str, entry_id: PathId):
        """Save a food or a dish into a new container from its row (frontend §9.3.1)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None or kind is FoodEntryType.RECIPE:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        with get_connection() as connection:
            entry = _food_entry_summary(connection, int(user_id), kind, entry_id)
        if entry is None:
            return app_error_response(request, NotFoundError, "Food not found.")
        return render_fragment(FoodActionsStore(kind, entry_id, entry))

    @rt("/food/actions/{entry_type}/{entry_id}/copy")
    def get(request: Request, entry_type: str, entry_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        with get_connection() as connection:
            entry = _food_entry_summary(connection, int(user_id), kind, entry_id)
        if entry is None:
            return app_error_response(request, NotFoundError, "Food not found.")
        return render_fragment(FoodActionsCopyConfirm(kind, entry_id, entry))

    @rt("/food/item/{entry_type}/{entry_id}")
    def get(request: Request, entry_type: str, entry_id: PathId):
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            raise ValidationError(_UNKNOWN_ENTRY_TYPE, fields={"entry_type": "invalid"})
        with get_connection() as connection:
            user_id = get_current_user_id()
            if kind is FoodEntryType.CATALOG:
                item = get_catalog_item(connection, int(user_id), entry_id) if user_id else None
                if item is None:
                    raise NotFoundError("Food not found.")
                summary = _catalog_detail_summary(item)
                tags_block = _entry_tags_block(connection, int(user_id), kind, entry_id) if user_id else ""
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
                        tags_block=tags_block,
                    ),
                    show_cart=False,
                )
            if kind is FoodEntryType.MANUAL_INTAKE:
                # None also for another user's personal dish or a quick add (§5.4, §11.2.3).
                manual_item = get_manual_intake(connection, int(user_id), entry_id) if user_id else None
                if manual_item is None:
                    raise NotFoundError("Dish not found.")
                summary = _manual_intake_detail_summary(manual_item)
                tags_block = _entry_tags_block(connection, int(user_id), kind, entry_id)
                events = list_planned_intake_events(connection, int(user_id))
                plate_options, selected_plate_id = (
                    plate_selector_options(connection, int(user_id), events[0].id) if events else ([], None)
                )
                return render_page(
                    request,
                    lambda _: FoodDetailPage(
                        user_id=user_id,
                        entry_type="manual_intake",
                        entry=manual_intake_entry_view(manual_item),
                        summary=summary,
                        recipe_portions=None,
                        events=events,
                        plate_options=plate_options,
                        selected_plate_id=selected_plate_id,
                        can_edit=manual_item.can_edit,
                        can_archive=manual_item.can_edit,
                        can_publish=manual_item.can_edit,
                        is_published=manual_item.is_published,
                        is_archived=manual_item.is_archived,
                        has_serving=manual_item.default_portion is not None,
                        cooking_factor=None,
                        tags_block=tags_block,
                    ),
                    show_cart=False,
                )
            recipe = get_recipe(connection, int(user_id), entry_id)
            if recipe is None:
                raise NotFoundError("Recipe not found.")
            entry = recipe_entry_view(recipe)
            recipe_portions = list_viewable_recipe_portions(connection, int(user_id), entry_id)
            recipe_plates = list_recipe_plates(connection, int(user_id), entry_id)
            summary = _recipe_summary(entry, recipe_portions)
            tags_block = _entry_tags_block(connection, int(user_id), kind, entry_id)
            can_edit = recipe.can_edit
            can_delete = can_edit
            events = list_planned_intake_events(connection, int(user_id)) if user_id else []
            # The event's plates the selector will show as selected (§7.7):
            # without this the plate selector would be born empty and would
            # only fill in when the meal changed.
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
                recipe_plates=recipe_plates,
                events=events,
                plate_options=plate_options,
                selected_plate_id=selected_plate_id,
                can_edit=can_edit,
                can_delete=can_delete,
                is_archived=False,
                tags_block=tags_block,
            ),
            show_cart=False,
        )

    @rt("/food/recipe/{recipe_id}/ingredients/form")
    def get(request: Request, recipe_id: PathId, recipe_plate_id: str = ""):
        target_plate_id = parse_optional_id(recipe_plate_id, "plate")
        with get_connection() as connection:
            user_id = get_current_user_id()
            recipe = _editable_recipe(connection, user_id, recipe_id)
            if recipe is None:
                raise NotFoundError("Recipe not found.")
            nodes = _recipe_ingredient_nodes(
                connection, int(user_id), recipe, search="", filter_value="food", page=1, recipe_plate_id=target_plate_id
            )
        return render_page(
            request,
            lambda _: RecipeIngredientPickerPage(recipe_entry_view(recipe), nodes, target_plate_id),
            show_cart=False,
        )

    @rt("/food/recipe/{recipe_id}/ingredients/list")
    def get(
        request: Request, recipe_id: PathId, search: str = "", filter: str = "food", recipe_plate_id: str = "", page: int = 1
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        if filter not in ("food", "favs"):
            return app_error_response(request, ValidationError, "Unknown filter.")
        try:
            target_plate_id = parse_optional_id(recipe_plate_id, "plate")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        with get_connection() as connection:
            user_id = get_current_user_id()
            recipe = _editable_recipe(connection, user_id, recipe_id)
            if recipe is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            nodes = _recipe_ingredient_nodes(
                connection,
                int(user_id),
                recipe,
                search=(search or "").strip(),
                filter_value=filter,
                page=max(1, page),
                recipe_plate_id=target_plate_id,
            )
        return render_fragment(tuple(nodes))

    @rt("/food/recipe/{recipe_id}/ingredients/add/{entry_type}/{entry_id}")
    def post(request: Request, recipe_id: PathId, entry_type: str, entry_id: PathId, recipe_plate_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            target_plate_id = parse_optional_id(recipe_plate_id, "plate")
            origin = PortionOrigin(entry_type)
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        except ValueError:
            # Value outside the closed set of the URL: validation_error (7.7).
            return app_error_response(request, ValidationError, "Unknown ingredient type.")

        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")

            item = (
                get_catalog_item(connection, int(user_id), entry_id)
                if origin is PortionOrigin.CATALOG
                else get_manual_intake(connection, int(user_id), entry_id)
            )
            if item is None:
                return app_error_response(request, NotFoundError, "Food not found.")
            try:
                with connection.transaction():
                    _add_ingredient(connection, int(user_id), recipe_id, target_plate_id, origin, item)
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
        recipe_id: PathId,
        portion_id: PathId,
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
        typed_amount = _parse_typed_amount(amount_value)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            portion = _recipe_portion(connection, int(user_id), recipe_id, portion_id)
            if portion is None:
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
            recipe = get_recipe(connection, int(user_id), recipe_id)
            summary = _recipe_summary(
                recipe_entry_view(recipe), list_viewable_recipe_portions(connection, int(user_id), recipe_id)
            )
        return render_fragment((P("Saved", cls="text-green-700"), *RecipeSummaryOob(recipe_id, summary)))

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/advanced")
    def post(
        request: Request,
        recipe_id: PathId,
        portion_id: PathId,
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
            # A control that saves itself has no form to show it in (error_conventions.md §7.1).
            return app_error_response(request, ValidationError, str(error))

        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            portion = _recipe_portion(connection, int(user_id), recipe_id, portion_id)
            if portion is None:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            try:
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
            except ValidationError as error:
                # A merge over the limit (measurement §4.6.4).
                return app_error_response(request, ValidationError, str(error))

            try:
                get_portion_detail(connection, int(user_id), portion_id)
            except NotFoundError:
                # It merged with another row of the plate (measurement §4.6.4): the row
                # on screen no longer exists, so the whole block is repainted.
                response = _recipe_block_response(connection, int(user_id), recipe_id)
                response.headers["HX-Retarget"] = f"#recipe_ingredients_{recipe_id}"
                response.headers["HX-Reswap"] = "outerHTML"
                return response
        return render_fragment(P("Saved", cls="text-green-700"))

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/delete")
    def post(request: Request, recipe_id: PathId, portion_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            portion = _recipe_portion(connection, int(user_id), recipe_id, portion_id)
            if portion is None:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            delete_portion_detail(connection, int(user_id), portion_id)
            return _recipe_block_response(connection, int(user_id), recipe_id)

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/cooked")
    def post(request: Request, recipe_id: PathId, portion_id: PathId, is_cooked_weight: str = ""):
        """`Weighed cooked` of an ingredient. It can make it equal to another row of the
        plate, and then they merge (measurement §4.6.4). `Strictly weighted` is set in the
        cart, not here (§4.7)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            marked = _parse_strict_bool(is_cooked_weight)
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            portion = _recipe_portion(connection, int(user_id), recipe_id, portion_id)
            if portion is None:
                return app_error_response(request, NotFoundError, "Ingredient not found.")
            if marked and (portion.origin is not PortionOrigin.CATALOG or portion.source.cooking_factor is None):
                return app_error_response(
                    request, ValidationError, "This food has no cooking factor, so it cannot be weighed cooked."
                )
            try:
                with connection.transaction():
                    update_portion_flag(connection, int(user_id), portion_id, "is_cooked_weight", marked, commit=False)
            except ValidationError as error:
                # A merge over the limit (measurement §4.6.4).
                return app_error_response(request, ValidationError, str(error))
            return _recipe_block_response(connection, int(user_id), recipe_id)

    @rt("/food/recipe/{recipe_id}/ingredient/{portion_id}/plate")
    def post(request: Request, recipe_id: PathId, portion_id: PathId, recipe_plate_id: str = ""):
        """Move an ingredient to another plate of the recipe; same key -> they merge (§4.7)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            target = parse_optional_id(recipe_plate_id, "plate")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        if target is None:
            return app_error_response(request, ValidationError, "Invalid plate.")
        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            try:
                if _recipe_portion(connection, int(user_id), recipe_id, portion_id) is None:
                    raise NotFoundError("portion_not_found")
                with connection.transaction():
                    move_portion_to_recipe_plate(connection, int(user_id), portion_id, target, commit=False)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Ingredient or plate not found.")
            except ValidationError as error:
                # A merge over the limit (measurement §4.6.4).
                return app_error_response(request, ValidationError, str(error))
            return _recipe_block_response(connection, int(user_id), recipe_id)

    @rt("/food/recipe/{recipe_id}/plate")
    def post(request: Request, recipe_id: PathId):
        """A new empty plate at the end. Repeating it adds another (§9.6)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        with get_connection() as connection:
            user_id = get_current_user_id()
            if _editable_recipe(connection, user_id, recipe_id) is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            with connection.transaction():
                create_recipe_plate(connection, int(user_id), recipe_id, commit=False)
            return _recipe_block_response(connection, int(user_id), recipe_id)

    def _change_recipe_plate(request: Request, plate_id: int, change):
        """Common contract of the actions on a plate: owner only, repaints the block."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                recipe_id = get_recipe_plate(connection, int(user_id), plate_id).recipe_id
                with connection.transaction():
                    change(connection, int(user_id))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Plate not found.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
            return _recipe_block_response(connection, int(user_id), recipe_id)

    @rt("/food/recipe/plate/{plate_id}/name")
    def post(request: Request, plate_id: PathId, name: str = ""):
        """Empty returns the plate to its derived name (measurement §4.6.3)."""
        try:
            parsed = parse_recipe_plate_name(name)
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        return _change_recipe_plate(
            request,
            plate_id,
            lambda connection, user_id: update_recipe_plate_name(connection, user_id, plate_id, parsed, commit=False),
        )

    @rt("/food/recipe/plate/{plate_id}/up")
    def post(request: Request, plate_id: PathId):
        return _change_recipe_plate(
            request,
            plate_id,
            lambda connection, user_id: swap_recipe_plate_position(connection, user_id, plate_id, up=True, commit=False),
        )

    @rt("/food/recipe/plate/{plate_id}/down")
    def post(request: Request, plate_id: PathId):
        return _change_recipe_plate(
            request,
            plate_id,
            lambda connection, user_id: swap_recipe_plate_position(connection, user_id, plate_id, up=False, commit=False),
        )

    @rt("/food/recipe/plate/{plate_id}/delete")
    def post(request: Request, plate_id: PathId):
        """With ingredients it answers 409 (measurement §4.7)."""
        return _change_recipe_plate(
            request,
            plate_id,
            lambda connection, user_id: delete_recipe_plate(connection, user_id, plate_id, commit=False),
        )

    @rt("/food/recipe/{recipe_id}/add/form")
    def get(request: Request, recipe_id: PathId, intake_event_id: str = "", plate_id: str = ""):
        """The step before adding a recipe to a meal (frontend §9.7)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            recipe = get_recipe(connection, int(user_id), recipe_id)
            if recipe is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            groups = recipe_plates_with_portions(connection, int(user_id), recipe_id)
        if not groups:
            return app_error_response(request, ConflictError, _RECIPE_WITHOUT_INGREDIENTS)
        return render_fragment(RecipeAddForm(recipe, groups, intake_event_id, plate_id))

    def _copy_catalog_item(request: Request, user_id: int, catalog_id: int):
        with get_connection() as connection:
            source = get_catalog_item(connection, user_id, catalog_id)
            if source is None:
                return app_error_response(request, NotFoundError, "Food not found.")
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
                            macros_quality=source.macros_quality,
                            default_strictly_weighed=source.default_strictly_weighed,
                            macros_confidence=source.macros_confidence,
                        ),
                        commit=False,
                    )
                    set_user_favorite(connection, user_id, FoodEntryType.CATALOG, int(created_id), True, commit=False)
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
            except ValidationError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/catalog/{created_id}/form"})

    def _copy_manual_intake(request: Request, user_id: int, manual_intake_id: int):
        """Editable copy of a visible dish (H16, §11.2.3): a new personal row in
        the family of the original, with every field copied. The owner can
        copy their own dish too (decision 2026-10-27)."""
        with get_connection() as connection:
            source = get_manual_intake(connection, user_id, manual_intake_id)
            if source is None:
                return app_error_response(request, NotFoundError, "Dish not found.")
            name = next_manual_intake_copy_name(connection, user_id, source.name, source.origin)
            root = source.origin_root_id or source.id
            try:
                with connection.transaction():
                    created_id = create_manual_intake(
                        connection,
                        ManualIntakeCreate(
                            created_by=user_id,
                            origin_root_id=root,
                            name=name,
                            description=source.description,
                            subtype=source.subtype,
                            origin=source.origin,
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
                            glycemic_index=source.glycemic_index,
                            ig_confidence=source.ig_confidence,
                            macros_confidence=source.macros_confidence,
                            macros_quality=source.macros_quality,
                            default_strictly_weighed=source.default_strictly_weighed,
                        ),
                        commit=False,
                    )
                    set_user_favorite(connection, user_id, FoodEntryType.MANUAL_INTAKE, int(created_id), True, commit=False)
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
            except ValidationError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/manual_intake/{created_id}/form"})

    @rt("/food/copy/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        if kind is FoodEntryType.CATALOG:
            return _copy_catalog_item(request, int(user_id), entry_id)
        if kind is FoodEntryType.MANUAL_INTAKE:
            return _copy_manual_intake(request, int(user_id), entry_id)

        with get_connection() as connection:
            try:
                created_id = copy_recipe(connection, int(user_id), entry_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Item not found.")
            except ConflictError as error:
                # uq_recipe_personal_name: only if another request took the copy's
                # name between next_recipe_copy_name and the insert.
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/edit/recipe/{created_id}/form"})

    @rt("/food/edit/{entry_type}/{entry_id}/form")
    def get(request: Request, entry_type: str, entry_id: PathId):
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            raise ValidationError(_UNKNOWN_ENTRY_TYPE, fields={"entry_type": "invalid"})
        with get_connection() as connection:
            user_id = get_current_user_id()
            entry = None
            if kind is FoodEntryType.CATALOG:
                item = get_catalog_item(connection, int(user_id), entry_id) if user_id else None
                if item is None:
                    raise NotFoundError("Food not found.")
                if not item.can_edit:
                    raise AuthorizationError(
                        "Only the owner can edit this food. Create a copy to edit it."
                    )
                brands = get_food_brand_suggestions(connection, search="", limit=500)
                subtypes = get_subtype_suggestions(connection, search="", limit=500)
                return render_page(
                    request,
                    lambda _: EditCatalogPage(
                        entry=catalog_entry_view(item),
                        brand_options=brands,
                        subtype_options=subtypes,
                    ),
                    show_cart=False,
                )
            if kind is FoodEntryType.MANUAL_INTAKE:
                # None also for another user's personal dish or a quick add (§5.4, §11.2.3).
                manual_item = get_manual_intake(connection, int(user_id), entry_id) if user_id else None
                if manual_item is None:
                    raise NotFoundError("Dish not found.")
                if not manual_item.can_edit:
                    raise AuthorizationError(
                        "Only the owner can edit this dish. Create a copy to edit it."
                    )
                subtypes = get_subtype_suggestions(connection, search="", limit=500)
                origins = get_manual_origin_suggestions(connection, int(user_id), limit=500)
                return render_page(
                    request,
                    lambda _: EditManualPage(
                        entry=manual_intake_entry_view(manual_item),
                        subtype_options=subtypes,
                        origin_options=origins,
                    ),
                    show_cart=False,
                )
            recipe = get_recipe(connection, int(user_id), entry_id) if user_id else None
            if recipe is None:
                raise NotFoundError("Recipe not found.")
            if not recipe.can_edit:
                raise AuthorizationError("Only the owner can edit this recipe. Create a copy to edit it.")
            entry = recipe_entry_view(recipe)
            return render_page(
                request,
                lambda _: EditRecipePage(
                    entry=entry,
                ),
                show_cart=False,
            )

    def _archive_catalog_item(request: Request, user_id: int, catalog_id: int):
        with get_connection() as connection:
            try:
                with connection.transaction():
                    # False = already archived: idempotent no-op (§9.6).
                    archive_catalog_item(connection, user_id, catalog_id, commit=False)
                    set_user_favorite(connection, user_id, FoodEntryType.CATALOG, catalog_id, False, commit=False)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Food not found.")
        return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/archive/catalog/{catalog_id}")
    def post(request: Request, catalog_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        return _archive_catalog_item(request, int(user_id), catalog_id)

    @rt("/food/publish/catalog/{catalog_id}")
    def post(request: Request, catalog_id: PathId):
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
    def post(request: Request, catalog_id: PathId):
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

    def _archive_manual_intake(request: Request, user_id: int, manual_intake_id: int):
        """Archive with the catalog contract (§11.2.3): the route owns the
        transaction (§2.3), and the dish leaves the owner's favorites in it."""
        with get_connection() as connection:
            try:
                with connection.transaction():
                    # False = already archived: idempotent no-op (§9.6).
                    archive_manual_intake(connection, user_id, manual_intake_id, commit=False)
                    set_user_favorite(
                        connection, user_id, FoodEntryType.MANUAL_INTAKE, manual_intake_id, False, commit=False
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Dish not found.")
        return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/archive/manual_intake/{manual_intake_id}")
    def post(request: Request, manual_intake_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        return _archive_manual_intake(request, int(user_id), manual_intake_id)

    @rt("/food/publish/manual_intake/{manual_intake_id}")
    def post(request: Request, manual_intake_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                publish_manual_intake(connection, int(user_id), manual_intake_id, commit=True)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Dish not found.")
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/manual_intake/{manual_intake_id}"})

    @rt("/food/unpublish/manual_intake/{manual_intake_id}")
    def post(request: Request, manual_intake_id: PathId):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                unpublish_manual_intake(connection, int(user_id), manual_intake_id, commit=True)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Dish not found.")
            except ConflictError as error:
                return app_error_response(request, ConflictError, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/manual_intake/{manual_intake_id}"})

    @rt("/food/delete/recipe/{recipe_id}")
    def post(request: Request, recipe_id: PathId):
        """Physical delete of a recipe. `catalog` and `manual_intake` are
        archived, never deleted (`/food/archive/...`, §11.2)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")

        with get_connection() as connection:
            current = get_recipe(connection, int(user_id), recipe_id)
            if current is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            if not current.can_edit:
                return app_error_response(request, AuthorizationError, "Only the owner can delete this item.")
            try:
                delete_recipe(connection, int(user_id), recipe_id)
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/log/{entry_type}/{entry_id}")
    def post(
        request: Request,
        entry_type: str,
        entry_id: PathId,
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
        strictly_weighed: str | None = None,
    ):
        """Add a food or a recipe from its page to a planned event.

        The form sends what the user typed, value + unit, and the server
        converts it (measurement_conventions.md 11, decision 2026-09-22):
        `amount_value`/`amount_unit` is the cooked total (`portion`, `g`, `lb`,
        `oz`) and `plate_value`/`plate_unit` the part of it that is plated
        (`%` of the total or `g`). Only the plated amount is persisted; the
        cooked total is used to bound it and is not stored (decision
        2026-09-18). The JavaScript only repaints the numbers.

        `strictly_weighed` is the tri-state control of the page, which starts
        on the food's default (measurement_conventions.md §6.11): what it
        sends is what the portion is born with. Absent (a request without the
        control), the food's default applies as on every other path.
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)

        try:
            cooked_weight = _parse_strict_bool(is_cooked_weight)
        except ValidationError:
            return app_error_response(request, ValidationError, "The 'Cooked weight' checkbox could not be read.")
        try:
            chosen_weighed = _parse_optional_bool(strictly_weighed)
        except ValidationError:
            return app_error_response(request, ValidationError, "The 'Strictly weighted' value could not be read.")
        try:
            unit = AmountInputUnit((amount_unit or "").strip())
            plated_unit = AmountInputUnit((plate_unit or "").strip())
        except ValueError:
            return render_fragment(P("Choose a valid unit.", cls="text-red-700"))
        if unit is AmountInputUnit.PERCENT or plated_unit not in (AmountInputUnit.PERCENT, AmountInputUnit.GRAMS):
            return render_fragment(P("Choose a valid unit.", cls="text-red-700"))
        typed_amount = _parse_typed_amount(amount_value)
        typed_plate = _parse_typed_amount(plate_value)
        if typed_amount is None or typed_plate is None:
            return render_fragment(P("Amount must be a number.", cls="text-red-700"))
        try:
            parsed_cooking = parse_enum(CookingMethod, cooking, field="cooking")
            parsed_final_state = parse_enum(FoodPhysicalState, final_state, field="final_state")
            parsed_conservation = parse_enum(ConservationMethod, conservation, field="conservation")
        except ValidationError as error:
            return render_fragment(P(str(error), cls="text-red-700"))

        if kind is FoodEntryType.RECIPE:
            # A recipe goes through its own step (POST /add_recipe, frontend §9.7).
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                # Defence in depth: the middleware already covers these routes
                # (finding 26 of audit_intake_event).
                return app_error_response(request, AuthenticationError, "Your session has expired.")
            try:
                origin_item = _detail_origin(connection, int(user_id), kind, entry_id, cooked_weight, unit)
            except NotFoundError as error:
                return app_error_response(request, NotFoundError, str(error))
            except ValidationError as error:
                return _error_msg(str(error))
            serving_grams = origin_item.default_portion
            portion_defaults = _portion_defaults(origin_item)
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
                    event_id, _ = _resolve_target_event(connection, int(user_id), intake_event_id)
                    event_data = get_intake_event(connection, int(user_id), event_id)
                    offset_minutes = _event_auto_offset_minutes(event_data)

                    if strictly_weighed is not None:
                        portion_defaults["strictly_weighed"] = chosen_weighed
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
                            is_cooked_weight=(cooked_weight if kind is FoodEntryType.CATALOG else False),
                            **portion_defaults,
                        ),
                        commit=False,
                    )
                    # What was cooked and not plated goes into a new container in the
                    # fridge, as the page says (measurement §4.8.5).
                    leftover_grams = total_grams - plated_grams
                    if leftover_grams > _PLATE_DISPLAY_TOLERANCE_G:
                        create_fridge_container(
                            connection,
                            FridgeStoreCommand(
                                user_id=int(user_id),
                                location=StorageLocation.FRIDGE,
                                contents=(
                                    FridgeContent(
                                        origin=PortionOrigin(entry_type),
                                        origin_id=entry_id,
                                        amount=leftover_grams,
                                        cooking=parsed_cooking,
                                        final_state=parsed_final_state,
                                        strictly_weighed=portion_defaults["strictly_weighed"],
                                        is_cooked_weight=(cooked_weight if kind is FoodEntryType.CATALOG else False),
                                    ),
                                ),
                            ),
                        )
            except NotFoundError:
                # Another user's or an archived intake_event_id: a nonexistent
                # resource (§5.4), not a server failure (finding 23).
                return app_error_response(request, NotFoundError, "That meal no longer exists.")
            except ConflictError:
                # The event is no longer 'planned'.
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError:
                return render_fragment(P("Could not log this food: check the amounts.", cls="text-red-700"))
            return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/fridge/store/{entry_type}/{entry_id}")
    def post(
        request: Request,
        entry_type: str,
        entry_id: PathId,
        location: str = "",
        amount_value: str = "",
        amount_unit: str = AmountInputUnit.PORTION.value,
        cooking: str = "",
        final_state: str = "",
        is_cooked_weight: str = "",
        strictly_weighed: str | None = None,
    ):
        """Save an amount of a food or a dish from its page as a new container in
        the fridge or the freezer (measurement_conventions.md §4.8.5, frontend §9.4).

        Same fields as /food/log without the plate: the whole amount goes into the
        container, and its conservation is the container's place (§4.8.4).
        Repeating it stores a second container (§9.6). Form validation answers
        200 + message (§9.5); on success an empty body and `fridgeStored`, which
        static/js/fridge.js turns into a notice (the page stays where it is).
        Also used by the actions pop-up of a Food row (frontend §9.3.1).
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        kind = _parse_food_entry_type(entry_type)
        if kind is None or kind is FoodEntryType.RECIPE:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        try:
            storage = parse_enum(StorageLocation, location, field="location")
            cooked_weight = _parse_strict_bool(is_cooked_weight)
            chosen_weighed = _parse_optional_bool(strictly_weighed)
            parsed_cooking = parse_enum(CookingMethod, cooking, field="cooking")
            parsed_final_state = parse_enum(FoodPhysicalState, final_state, field="final_state")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        if storage is None:
            return app_error_response(request, ValidationError, "Choose the fridge or the freezer.")
        try:
            unit = AmountInputUnit((amount_unit or "").strip())
        except ValueError:
            return _store_error(request, "Choose a valid unit.")
        if unit is AmountInputUnit.PERCENT:
            return _store_error(request, "Choose a valid unit.")
        typed_amount = _parse_typed_amount(amount_value)
        if typed_amount is None:
            return _store_error(request, "Amount must be a number.")

        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        with get_connection() as connection:
            try:
                origin_item = _detail_origin(connection, int(user_id), kind, entry_id, cooked_weight, unit)
                grams = parse_amount_grams(amount_to_grams(typed_amount, unit, origin_item.default_portion))
            except NotFoundError as error:
                return app_error_response(request, NotFoundError, str(error))
            except ValidationError as error:
                return _store_error(request, str(error))
            weighed = chosen_weighed if strictly_weighed is not None else origin_item.default_strictly_weighed
            try:
                store_in_fridge(
                    connection,
                    FridgeStoreCommand(
                        user_id=int(user_id),
                        location=storage,
                        contents=(
                            FridgeContent(
                                origin=PortionOrigin(kind.value),
                                origin_id=entry_id,
                                amount=grams,
                                cooking=parsed_cooking,
                                final_state=parsed_final_state,
                                strictly_weighed=weighed,
                                is_cooked_weight=cooked_weight,
                            ),
                        ),
                    ),
                )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Item not found.")
            except ValidationError as error:
                return _store_error(request, str(error))
        return HTMLResponse("", headers={"HX-Trigger": json.dumps({"fridgeStored": {"location": storage.value}})})

    @rt("/food/list")
    def get(
        request: Request,
        search: str = "",
        filter: str = "all",
        search_mode: str = "recommended",
        food_mode: str = "catalog",
        favs_mode: str = "catalog",
        recipes_mode: str = "mine",
        meal_type: str = "",
        page: int = 1,
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        try:
            recipe_meal_types = parse_recipe_meal_types(meal_type)
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))

        clean_search = (search or "").strip()
        page = max(1, int(page or 1))
        food_mode_norm = (food_mode or "catalog").strip().lower()
        if food_mode_norm not in ("catalog", "manual"):
            food_mode_norm = "catalog"
        if filter == "fridge":
            # The user's containers, without search or pages: there are never
            # many (frontend_conventions.md §9.8).
            user_id = get_current_user_id()
            if not user_id:
                return app_error_response(request, AuthenticationError, "Your session has expired.")
            with get_connection() as connection:
                items = list_fridge_items(connection, int(user_id))
            return render_fragment(FridgeListContent(items, utc_now()))
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
                entries = _recipes_entries(
                    connection, search=clean_search, recipes_mode=recipes_mode_norm, meal_types=recipe_meal_types
                )
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
            # Only with the first page, after its load-more node: the user's next
            # pages replace that node, so they stay above this section (§12.2).
            off_nodes = []
            user_id = get_current_user_id()
            if (
                page == 1
                and clean_search
                and user_id
                and (filter == "all" or (filter == "food" and food_mode_norm == "catalog"))
            ):
                off_nodes = [
                    *ExternalFoodSection(
                        "From Ciqual",
                        *_external_page(connection, int(user_id), PrefillSource.CIQUAL, clean_search, 1),
                        ciqual_attribution(),
                    ),
                    *ExternalFoodSection(
                        "From Open Food Facts",
                        *_external_page(connection, int(user_id), PrefillSource.OPEN_FOOD_FACTS, clean_search, 1),
                        off_attribution(),
                    ),
                ]

        if not entries and not off_nodes:
            return render_fragment(H2("No items", cls="text-gray-600"))

        page_size = SEARCH_PAGE_SIZE if clean_search else LIST_PAGE_SIZE
        start = (page - 1) * page_size
        end = start + page_size
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
                        meal_type,
                        page + 1,
                    )
                )
            return render_fragment(tuple(nodes + off_nodes))

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
                        meal_type,
                        page + 1,
                    )
                )
            return render_fragment(tuple(nodes + off_nodes))

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
                        meal_type,
                        page + 1,
                    )
                )
            return render_fragment(tuple(nodes + off_nodes))

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
                    meal_type,
                    page + 1,
                )
            )
        return render_fragment(tuple(nodes + off_nodes))

    @rt("/food/list/external")
    def get(
        request: Request, source: str = "", search: str = "", page: int = 1, add_to_recipe: str = "", recipe_plate_id: str = ""
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            prefill_source = PrefillSource(source)
        except ValueError:
            return app_error_response(request, ValidationError, "Unknown food source.")
        with get_connection() as connection:
            try:
                recipe_query = _recipe_query(
                    parse_optional_id(add_to_recipe, "recipe"), parse_optional_id(recipe_plate_id, "plate")
                )
            except ValidationError as error:
                return app_error_response(request, ValidationError, str(error))
            cards, load_more = _external_page(
                connection, int(user_id), prefill_source, (search or "").strip(), max(1, page), recipe_query
            )
        return render_fragment(tuple(cards + ([load_more] if load_more is not None else [])))

    @rt("/add_food/{food_id}")
    def post(request: Request, food_id: PathId, intake_event_id: str = "", plate_id: str = ""):
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
                    event_id, meal_created = _resolve_target_event(connection, int(user_id), intake_event_id)
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
                            **_portion_defaults(catalog_item),  # measurement §6.11
                        ),
                        commit=False,
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal no longer exists.")
            except ConflictError:
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError as error:
                return app_error_response(request, ValidationError, str(error))
            trigger = {"addSuccess": True}
            if meal_created:
                trigger.update(_meal_created_event(connection, int(user_id), event_id))
            return HTMLResponse("", headers={"HX-Trigger": json.dumps(trigger)})

    @rt("/add_manual_intake/{manual_intake_id}")
    def post(request: Request, manual_intake_id: PathId, intake_event_id: str = "", plate_id: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                return app_error_response(request, AuthenticationError, "Your session has expired.")
            manual_intake = get_manual_intake(connection, int(user_id), manual_intake_id)
            if manual_intake is None:
                return app_error_response(request, NotFoundError, "Dish not found.")
            # R3, same as catalog: no serving -> 100 g initial amount for a one-click add.
            portion_amount = (
                manual_intake.default_portion
                if manual_intake.default_portion is not None
                else INITIAL_AMOUNT_WITHOUT_SERVING_G
            )
            try:
                with connection.transaction():
                    event_id, meal_created = _resolve_target_event(connection, int(user_id), intake_event_id)
                    event_data = get_intake_event(connection, int(user_id), event_id)
                    offset_minutes = _event_auto_offset_minutes(event_data)
                    target_plate_id = _resolve_event_plate(
                        connection, int(user_id), event_id, plate_id, offset_minutes
                    )
                    create_portion_detail(
                        connection,
                        int(user_id),
                        PortionDetailCreate(
                            origin=PortionOrigin.MANUAL_INTAKE,
                            origin_id=manual_intake_id,
                            destination=PortionDestination.INTAKE_EVENT,
                            destination_id=event_id,
                            plate_id=target_plate_id,
                            amount=portion_amount,
                            **_portion_defaults(manual_intake),
                        ),
                        commit=False,
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal no longer exists.")
            except ConflictError:
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError as error:
                return app_error_response(request, ValidationError, str(error))
            trigger = {"addSuccess": True}
            if meal_created:
                trigger.update(_meal_created_event(connection, int(user_id), event_id))
            return HTMLResponse("", headers={"HX-Trigger": json.dumps(trigger)})

    @rt("/food/fridge/{fridge_id}/take")
    def post(
        request: Request,
        fridge_id: PathId,
        amount_value: str = "",
        amount_unit: str = AmountInputUnit.PERCENT.value,
        intake_event_id: str = "",
        plate_id: str = "",
    ):
        """Take a part of a container into the meal and plate of the Food header
        (measurement_conventions.md §4.8.3, frontend §9.8). It is discounted now and
        goes back if the planned meal or the ingredient is deleted (§4.8.6).

        Repeating it takes another part, as a second helping would (§9.6). A
        validation error is a message inside the pop-up (200, §9.5); on success the
        message is emptied, the list is swapped out of band and `fridgeChanged` and
        `fridgeTaken` close the pop-up and give the notice.
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            unit = AmountInputUnit((amount_unit or "").strip())
        except ValueError:
            return render_fragment(ModalFormError("Take it in % or in grams."))
        with get_connection() as connection:
            if get_fridge(connection, int(user_id), fridge_id) is None:
                return app_error_response(request, NotFoundError, "That container is no longer in your fridge.")
            try:
                with connection.transaction():
                    event_id, meal_created = _resolve_target_event(connection, int(user_id), intake_event_id)
                    offset_minutes = _event_auto_offset_minutes(get_intake_event(connection, int(user_id), event_id))
                    target_plate_id = _resolve_event_plate(
                        connection, int(user_id), event_id, plate_id, offset_minutes
                    )
                    take_from_fridge(
                        connection, int(user_id), fridge_id, amount_value, unit, event_id, target_plate_id
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal or container is no longer available.")
            except ConflictError:
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError as error:
                return render_fragment(ModalFormError(str(error)))
            items = list_fridge_items(connection, int(user_id))
            trigger = {"fridgeChanged": True, "fridgeTaken": True}
            if meal_created:
                trigger.update(_meal_created_event(connection, int(user_id), event_id))
        response = render_fragment(FridgeListOob(items, utc_now()))
        response.headers["HX-Trigger"] = json.dumps(trigger)
        return response

    @rt("/add_recipe/{recipe_id}")
    async def post(request: Request, recipe_id: PathId):
        """Add a recipe to a meal (frontend §9.7). Repeating it adds it again: another
        serving, not a duplicate (§9.6). Form validation answers 200 + fragment (§9.5)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        form = await request.form()
        with get_connection() as connection:
            recipe = get_recipe(connection, int(user_id), recipe_id)
            if recipe is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            try:
                add_request = _parse_recipe_add_request(form, recipe)
                event_id = add_recipe_to_meal(
                    connection,
                    int(user_id),
                    recipe_id,
                    add_request,
                    default_meal_type=_default_meal_type_now(connection, int(user_id)),
                )
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal or plate no longer exists.")
            except ConflictError as error:
                message = _RECIPE_WITHOUT_INGREDIENTS if str(error) == "recipe_without_ingredients" else _MEAL_CONFIRMED
                return app_error_response(request, ConflictError, message)
            trigger = {"recipeAdded": {"event_id": event_id}}
            if add_request.event_id is None:
                trigger.update(_meal_created_event(connection, int(user_id), event_id))
        return HTMLResponse("", headers={"HX-Trigger": json.dumps(trigger)})

    @rt("/food/fridge/store_recipe/{recipe_id}")
    async def post(request: Request, recipe_id: PathId):
        """Save a recipe into a new container from its step before adding, with its
        servings and preparation (measurement §4.8.5, frontend §9.7). The meal and
        plate of the form do not apply. Repeating it stores another container (§9.6).
        Form validation answers 200 + fragment (§9.5); on success `fridgeStored`."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        form = await request.form()
        try:
            storage = parse_enum(StorageLocation, str(form.get("location") or ""), field="location")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        if storage is None:
            return app_error_response(request, ValidationError, "Choose the fridge or the freezer.")
        with get_connection() as connection:
            recipe = get_recipe(connection, int(user_id), recipe_id)
            if recipe is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            try:
                store_recipe_in_fridge(
                    connection, int(user_id), recipe_id, storage, _parse_recipe_add_request(form, recipe)
                )
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            except ConflictError:
                return app_error_response(request, ConflictError, _RECIPE_WITHOUT_INGREDIENTS)
        return HTMLResponse("", headers={"HX-Trigger": json.dumps({"fridgeStored": {"location": storage.value}})})

    @rt("/food/favorite/{entry_type}/{entry_id}")
    def post(request: Request, entry_type: str, entry_id: PathId, favorite: str = "", confirmed: str = ""):
        """Sets the favorite to what the star asked for (frontend §9.3.2)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        kind = _parse_food_entry_type(entry_type)
        if kind is None:
            return app_error_response(request, ValidationError, _UNKNOWN_ENTRY_TYPE)
        # Required: the strict parser reads an empty value as False, and a request
        # without the field must not remove the favorite (§7.4, §7.6).
        if not favorite.strip():
            return app_error_response(request, ValidationError, "Say whether to add or remove the favorite.")
        try:
            wanted = _parse_strict_bool(favorite)
            removal_confirmed = _parse_strict_bool(confirmed)
        except ValidationError as error:
            return app_error_response(request, error, str(error))

        not_found, not_addable = _FAVORITE_MESSAGES[kind]
        with get_connection() as connection:
            if not wanted and not removal_confirmed:
                access = get_user_favorite_access(connection, int(user_id), kind, entry_id)
                entry = (
                    _food_entry_summary(connection, int(user_id), kind, entry_id)
                    if access is not None and access.is_only_access
                    else None
                )
                if entry is not None:
                    response = render_fragment(FoodActionsFavoriteConfirm(kind, entry_id, entry))
                    response.headers["HX-Retarget"] = f"#{FOOD_ACTIONS_BODY_ID}"
                    response.headers["HX-Reswap"] = "innerHTML"
                    return response
            try:
                set_user_favorite(connection, int(user_id), kind, entry_id, wanted)
            except NotFoundError:
                return app_error_response(request, NotFoundError, not_found)
            except ConflictError:
                return app_error_response(request, ConflictError, not_addable)
            access = get_user_favorite_access(connection, int(user_id), kind, entry_id)

        if access is None:
            # The row was the access to this food: its card has nothing left to show.
            response = HTMLResponse("")
            response.headers["HX-Retarget"] = f"#{food_card_id(kind, entry_id)}"
            response.headers["HX-Reswap"] = "outerHTML"
            return response
        return render_fragment(FavoriteButton(kind, entry_id, access.is_favorite))

    @rt("/food/edit/catalog/{entry_id}")
    def post(
        request: Request,
        entry_id: PathId,
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
        macros_quality: str = "",
        default_strictly_weighed: str = "",
        macros_confidence: str = "",
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
                macros_quality=macros_quality,
                default_strictly_weighed=default_strictly_weighed,
                macros_confidence=macros_confidence,
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
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Food not found or no longer editable.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/catalog/{entry_id}"})

    @rt("/food/edit/manual_intake/{manual_intake_id}")
    def post(
        request: Request,
        manual_intake_id: PathId,
        name: str = "",
        description: str = "",
        subtype: str = "",
        subtype__added: str = "",
        source_origin: str = "",
        default_portion: str = "",
        nutrient_mode: str = "",
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
        macros_confidence: str = "",
        macros_quality: str = "",
        default_strictly_weighed: str = "",
    ):
        """Full replacement of a reusable dish (H1): an empty optional field is
        stored as NULL. Publishing is the detail page's action, not a field here."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_manual_intake_request(
                name=name,
                description=description,
                subtype=subtype,
                subtype__added=subtype__added,
                origin=source_origin,
                default_portion=default_portion,
                nutrient_mode=nutrient_mode,
                glycemic_index=glycemic_index,
                ig_confidence=ig_confidence,
                macros_confidence=macros_confidence,
                macros_quality=macros_quality,
                default_strictly_weighed=default_strictly_weighed,
                calories_100g=calories_100g,
                carbs_100g=carbs_100g,
                sugars_100g=sugars_100g,
                fats_100g=fats_100g,
                saturated_100g=saturated_100g,
                proteins_100g=proteins_100g,
                fiber_100g=fiber_100g,
                caffeine=caffeine,
                alcohol=alcohol,
            )
        except ValidationError as error:
            return _error_msg(str(error))

        with get_connection() as connection:
            try:
                with connection.transaction():
                    subtype_value = _resolve_manual_subtype(connection, req)
                    update_manual_intake(
                        connection,
                        int(user_id),
                        manual_intake_id,
                        _manual_intake_update(req, subtype_value),
                        commit=False,
                    )
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Dish not found or no longer editable.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/manual_intake/{manual_intake_id}"})

    @rt("/food/edit/recipe/{recipe_id}")
    def post(
        request: Request,
        recipe_id: PathId,
        name: str = "",
        meal_type: str = "",
        extra_meal_types: list[str] | None = None,
        notes: str = "",
        servings: str = "",
    ):
        """Full replacement (§3.4): an empty optional field is stored as NULL. There
        is no way to publish from here until phase 2 (§11.4.1)."""
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_recipe_request(
                name=name,
                meal_type=meal_type,
                extra_meal_types=extra_meal_types,
                notes=notes,
                servings=servings,
            )
        except ValidationError as error:
            # Form validation: 200 + fragment inside the form (§9.5).
            return _error_msg(str(error))
        with get_connection() as connection:
            current = get_recipe(connection, int(user_id), recipe_id)
            if current is None:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            if not current.can_edit:
                return app_error_response(request, AuthorizationError, "Only the owner can edit this recipe.")
            try:
                with connection.transaction():
                    update_recipe(
                        connection,
                        int(user_id),
                        recipe_id,
                        RecipeUpdate(
                            name=req.name,
                            meal_type=req.meal_type,
                            extra_meal_types=req.extra_meal_types,
                            notes=req.notes,
                            servings=req.servings,
                        ),
                        commit=False,
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": f"/food/item/recipe/{recipe_id}"})

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
        macros_quality: str = "",
        default_strictly_weighed: str = "",
        macros_confidence: str = "",
        favorite: str = "",
        catalog_smart_macros_raw: str = "",
        prefill_source: str = "",
        prefill_source_id: str = "",
        add_to_recipe: str = "",
        add_to_recipe_plate: str = "",
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
                macros_quality=macros_quality,
                default_strictly_weighed=default_strictly_weighed,
                macros_confidence=macros_confidence,
                favorite=favorite,
                smart_raw=catalog_smart_macros_raw,
                prefill_source=prefill_source,
                prefill_source_id=prefill_source_id,
            )
            target_recipe_id = parse_optional_id(add_to_recipe, "recipe")
            target_plate_id = parse_optional_id(add_to_recipe_plate, "plate")
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
                    # The food is born personal (R5). The favorite is user data.
                    set_user_favorite(
                        connection, int(user_id), FoodEntryType.CATALOG, created_id, bool(req.favorite), commit=False
                    )
                    if target_recipe_id is not None:
                        # Chosen from a recipe's ingredient search (frontend §9.7).
                        if _editable_recipe(connection, user_id, target_recipe_id) is None:
                            raise NotFoundError("Recipe not found.")
                        _add_ingredient(
                            connection,
                            int(user_id),
                            target_recipe_id,
                            target_plate_id,
                            PortionOrigin.CATALOG,
                            get_catalog_item(connection, int(user_id), created_id),
                        )
            except ValidationError as error:
                return _error_msg(str(error))
            except NotFoundError:
                return app_error_response(request, NotFoundError, "Recipe not found.")
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        if target_recipe_id is not None:
            query = f"?recipe_plate_id={target_plate_id}" if target_plate_id else ""
            return HTMLResponse(
                "", headers={"HX-Redirect": f"/food/recipe/{target_recipe_id}/ingredients/form{query}"}
            )
        return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/create/manual_intake")
    def post(
        request: Request,
        name: str = "",
        description: str = "",
        subtype: str = "",
        subtype__added: str = "",
        source_origin: str = "",
        default_portion: str = "",
        nutrient_mode: str = "",
        caffeine: str = "",
        alcohol: str = "",
        glycemic_index: str = "",
        ig_confidence: str = "",
        macros_confidence: str = "",
        macros_quality: str = "",
        default_strictly_weighed: str = "",
        favorite: str = "",
        manual_smart_macros_raw: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            # Server-side smart macros; the hidden fields are ignored (§7.13).
            req = _parse_manual_intake_request(
                name=name,
                description=description,
                subtype=subtype,
                subtype__added=subtype__added,
                origin=source_origin,
                default_portion=default_portion,
                nutrient_mode=nutrient_mode,
                glycemic_index=glycemic_index,
                ig_confidence=ig_confidence,
                macros_confidence=macros_confidence,
                macros_quality=macros_quality,
                default_strictly_weighed=default_strictly_weighed,
                favorite=favorite,
                smart_raw=manual_smart_macros_raw,
                caffeine=caffeine,
                alcohol=alcohol,
            )
        except ValidationError as error:
            return _error_msg(str(error))

        with get_connection() as connection:
            try:
                with connection.transaction():
                    subtype_value = _resolve_manual_subtype(connection, req)
                    created_id = create_manual_intake(
                        connection,
                        _manual_intake_create(req, int(user_id), subtype_value),
                        commit=False,
                    )
                    # The dish is born personal (§11.4.1). The favorite is user data.
                    set_user_favorite(
                        connection, int(user_id), FoodEntryType.MANUAL_INTAKE, created_id, bool(req.favorite), commit=False
                    )
            except ValidationError as error:
                return _error_msg(str(error))
            except ConflictError as error:
                return app_error_response(request, error, str(error))
        return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/quick_add/form")
    def get(request: Request):
        """Quick add (§11.2.3): meal and plate selector on top, then name,
        estimated weight, total smart macros and notes."""
        user_id = get_current_user_id()
        if not user_id:
            raise AuthenticationError("Your session has expired.")
        with get_connection() as connection:
            events = list_planned_intake_events(connection, int(user_id))
            plate_options, selected_plate_id = (
                plate_selector_options(connection, int(user_id), events[0].id) if events else ([], None)
            )
        return render_page(
            request,
            lambda _: QuickAddPage(events, plate_options, selected_plate_id),
            show_cart=False,
        )

    @rt("/food/quick_add")
    def post(
        request: Request,
        name: str = "",
        default_portion: str = "",
        quick_smart_macros_raw: str = "",
        description: str = "",
        intake_event_id: str = "",
        plate_id: str = "",
    ):
        """Create the quick-add row and its portion in one transaction (§11.2.3).

        Repeating the submit creates another quick add and another portion:
        each submit is a new row, never merged with the previous one (§9.6).
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_quick_add_request(
                name=name,
                weight_g=default_portion,
                smart_raw=quick_smart_macros_raw,
                notes=description,
            )
        except ValidationError as error:
            return _error_msg(str(error))

        with get_connection() as connection:
            try:
                with connection.transaction():  # row + portion, all or nothing (§2.3)
                    event_id, _ = _resolve_target_event(connection, int(user_id), intake_event_id)
                    offset_minutes = _event_auto_offset_minutes(
                        get_intake_event(connection, int(user_id), event_id)
                    )
                    target_plate_id = _resolve_event_plate(
                        connection, int(user_id), event_id, plate_id, offset_minutes
                    )
                    payload = _quick_add_create(req, int(user_id))
                    manual_intake_id = create_manual_intake(connection, payload, commit=False)
                    create_portion_detail(
                        connection,
                        int(user_id),
                        PortionDetailCreate(
                            origin=PortionOrigin.MANUAL_INTAKE,
                            origin_id=manual_intake_id,
                            destination=PortionDestination.INTAKE_EVENT,
                            destination_id=event_id,
                            plate_id=target_plate_id,
                            amount=req.weight_g,
                            # The dish default (measurement §6.11): FALSE.
                            strictly_weighed=payload.default_strictly_weighed,
                        ),
                        commit=False,
                    )
            except NotFoundError:
                return app_error_response(request, NotFoundError, "That meal no longer exists.")
            except ConflictError:
                return app_error_response(request, ConflictError, "That meal has already been confirmed.")
            except ValidationError as error:
                return app_error_response(request, ValidationError, str(error))
        # Same pattern as "Log food" (§9.5).
        return HTMLResponse("", headers={"HX-Redirect": "/food"})

    @rt("/food/create/recipe")
    def post(
        request: Request,
        name: str = "",
        meal_type: str = "",
        extra_meal_types: list[str] | None = None,
        notes: str = "",
        servings: str = "",
        favorite: str = "",
    ):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return app_error_response(request, AuthenticationError, "Your session has expired.")
        try:
            req = _parse_recipe_request(
                name=name,
                meal_type=meal_type,
                extra_meal_types=extra_meal_types,
                notes=notes,
                servings=servings,
                favorite=favorite,
            )
        except ValidationError as error:
            return _error_msg(str(error))
        with get_connection() as connection:
            try:
                with connection.transaction():
                    created_id = create_recipe(
                        connection,
                        RecipeCreate(
                            user_id=int(user_id),
                            origin_root_id=None,
                            name=req.name,
                            meal_type=req.meal_type,
                            extra_meal_types=req.extra_meal_types,
                            notes=req.notes,
                            servings=req.servings,
                        ),
                        commit=False,
                    )
                    set_user_favorite(
                        connection, int(user_id), FoodEntryType.RECIPE, created_id, bool(req.favorite), commit=False
                    )
            except ConflictError as error:
                return app_error_response(request, error, str(error))
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
        """Plate selector for the event chosen in the meal selector (§7.7).

        It returns empty only when there is no event to list plates from (none
        selected, `New Meal`, or an event no longer in the cart).
        """
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)
        user_id = get_current_user_id()
        if not user_id:
            return HTMLResponse(status_code=401)
        try:
            chosen_event_id = parse_optional_id(intake_event_id, "meal")
        except ValidationError as error:
            return app_error_response(request, ValidationError, str(error))
        if not chosen_event_id:
            return render_fragment(PlateSelector([]))

        with get_connection() as connection:
            try:
                event_id = get_planned_intake_event(connection, int(user_id), chosen_event_id)
            except (NotFoundError, ConflictError):
                return render_fragment(PlateSelector([]))
            # The last plate something was added to is preselected: when putting
            # together the second dish, several foods are added to it in a row (§7.7).
            options, last_used = plate_selector_options(connection, int(user_id), event_id)
            return render_fragment(PlateSelector(options, selected_id=last_used))

    @rt("/create_named_event")
    def post(request: Request, meal_name: str = ""):
        if request.headers.get("HX-Request") != "true":
            return HTMLResponse(status_code=403)

        clean_name = (meal_name or "").strip()
        if len(clean_name) > INTAKE_EVENT_NAME_MAX_LENGTH:
            # §7.3: never truncate silently; anything beyond the VARCHAR(255)
            # is rejected at the boundary (decision 2026-09-09, finding 24).
            return HTMLResponse(status_code=422)

        with get_connection() as connection:
            user_id = get_current_user_id()
            if not user_id:
                # No session: 401 (error_conventions.md §3.3). Defense in
                # depth; the middleware already covers these routes (finding 26).
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
