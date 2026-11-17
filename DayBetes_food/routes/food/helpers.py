"""Helpers shared by the Food routes (routes/food/): parsing of their forms,
reads that prepare a view and the responses several routes return."""

from fasthtml.common import *
from dataclasses import dataclass
from datetime import datetime
import difflib
import logging
import re
import unicodedata
from urllib.parse import urlencode
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.ui import render_fragment
from DayBetes_food.domain.assistant import (
    DRAFT_MACROS_SOURCE,
    FoodDraftExtras,
    RecipeDraft,
    draft_tool_input,
    food_draft_extras,
    food_draft_prefill,
    manual_intake_draft,
    parse_tool_use_id,
    recipe_draft,
)
from DayBetes_food.database.queries import (
    get_assistant_message,
    list_catalog_items,
    search_off_products,
    search_ciqual_foods,
    list_manual_intakes,
    list_recipes,
    create_portion_detail,
    get_catalog_item,
    get_manual_intake,
    get_recipe,
    get_portion_detail,
    ensure_default_recipe_plate,
    list_recipe_plates,
    list_viewable_recipe_portions,
    create_food_brand,
    get_food_brand_id_by_label,
    get_subtype_label,
    get_consumed_food_usage_rankings,
    list_tags,
    get_system_tag,
    get_tag_by_name,
    create_tag,
    list_entry_tags,
    get_intake_event,
)
from DayBetes_food.domain.constants import (
    PREFILL_MACROS_SOURCE,
    NOVA_MAX,
    NOVA_MIN,
    YUKA_MAX,
    YUKA_MIN,
    AmountInputUnit,
    AmountMethod,
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodPhysicalState,
    GlycemicIndex,
    MacrosSource,
    Nutriscore,
    NutrientEntryMode,
    PortionDestination,
    PrefillSource,
    FoodEntryType,
    PortionOrigin,
    parse_enum,
    parse_optional_id,
)
from DayBetes_food.domain.nutrition import (
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
    FoodPrefill,
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
    default_final_state,
    portion_defaults,
    ripeness_applies,
)
from DayBetes_food.components.data_sources import ciqual_attribution, off_attribution
from DayBetes_food.components.food.food_list import (
    FoodCard,
    meal_option_label,
)
from DayBetes_food.components.food.food_actions import FOOD_ACTIONS_STORE_MESSAGE_ID
from DayBetes_food.components.modal import ModalFormError
from DayBetes_food.components.food.tags import EntryTags, system_tag_for_label
from DayBetes_food.components.food.food_list import (
    FOOD_FAVS_TABS,
    FOOD_FILTERS,
    FOOD_FOOD_TABS,
    FOOD_RECIPES_TABS,
    FOOD_SEARCH_TABS,
    FoodView,
)
from DayBetes_food.components.food.entry_views import (
    catalog_entry_view,
    manual_intake_entry_view,
    recipe_entry_view,
)
from DayBetes_food.components.food.food_widgets import (
    CONFIDENCE_LABELS,
    GLYCEMIC_INDEX_LABELS,
)
from DayBetes_food.components.food.food_shared import AMOUNT_METHOD_LABELS, MACROS_SOURCE_LABELS
from DayBetes_food.components.food.food_list import (
    ExternalFoodSection,
    ciqual_food_cards,
    off_product_cards,
)
from DayBetes_food.components.food.food_forms import (
    RecipeDraftForm,
    RecipeDraftLine,
)
from DayBetes_food.components.food.food_detail import (
    RecipeIngredientPickerCard,
    RecipeIngredientsBlock,
    RecipeSummaryOob,
)
from DayBetes_food.database.connection import get_connection
from DayBetes_food.domain.constants import AssistantDraftSource
from DayBetes_food.domain.tag import TagCreate, tag_color_from_name
from DayBetes_food.domain.recipe import (
    PortionPreparation,
    RecipeAddRequest,
    RecipeRead,
    RecipeRequest,
    parse_recipe_add_servings,
    parse_recipe_meal_type,
    parse_recipe_extra_meal_types,
    parse_recipe_meal_types,
    parse_recipe_name,
    parse_recipe_notes,
    parse_recipe_servings,
)
from DayBetes_food.services.recipe import recipe_draft_foods
from DayBetes_food.domain.portion_detail import portion_macro_amount
from DayBetes_food.components.stats.stats_shared import MEAL_TYPE_LABELS
from DayBetes_food.errors import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)


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
    macros_source,
    default_amount_method,
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
    parsed_macros_source = parse_enum(MacrosSource, macros_source, field="macros_source")
    parsed_default_amount_method = parse_enum(AmountMethod, default_amount_method, field="default_amount_method")
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
        macros_source=parsed_macros_source,
        default_amount_method=parsed_default_amount_method,
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
        macros_source=req.macros_source,
        default_amount_method=req.default_amount_method,
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
        macros_source=req.macros_source,
        default_amount_method=req.default_amount_method,
        macros_confidence=req.macros_confidence,
    )


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
    macros_source,
    default_amount_method,
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
        macros_source=parse_enum(MacrosSource, macros_source, field="macros_source"),
        default_amount_method=parse_enum(AmountMethod, default_amount_method, field="default_amount_method"),
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
        macros_source=req.macros_source,
        default_amount_method=req.default_amount_method,
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
        macros_source=req.macros_source,
        default_amount_method=req.default_amount_method,
    )


def _parse_quick_add_request(*, name, weight_g, smart_raw, notes, macros_source="", amount_method="") -> QuickAddRequest:
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
        macros_source=parse_enum(MacrosSource, macros_source, field="macros_source"),
        amount_method=parse_enum(AmountMethod, amount_method, field="amount_method"),
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


def _is_fruit(item: CatalogItemRead | ManualIntakeRead) -> bool:
    """Whether a meal portion of this food can carry a ripeness (study §6.3).
    A dish (`manual_intake`) has no category, so never."""
    category = getattr(item, "category", None)
    return ripeness_applies(PortionDestination.INTAKE_EVENT, category.value if category is not None else None)


def _rescue_error(message: str):
    """Validation error of the rescue pop-up: 200 + message inside the form (§9.5)."""
    return render_fragment(ModalFormError(message))


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


def _assistant_draft_input(connection, user_id: int, message_id: int, tool_use_id: str, tool_name: str) -> dict:
    """The input of a draft the assistant wrote (§8.12): read from its stored tool
    call, of one of the user's conversations, never from the browser (§7.13).

    Raises:
        NotFoundError: no such draft for this user.
    """
    try:
        tool_id = parse_tool_use_id(tool_use_id)
    except ValidationError as error:
        raise NotFoundError("Draft not found.") from error
    message = get_assistant_message(connection, user_id, message_id) if user_id else None
    tool_input = draft_tool_input(message, tool_id, tool_name) if message else None
    if tool_input is None:
        raise NotFoundError("Draft not found.")
    return tool_input


@dataclass(frozen=True)
class _FoodDraft:
    """A food draft of the assistant, validated again for the create form."""

    source: AssistantDraftSource
    code: str
    prefill: FoodPrefill | None  # label and estimate; Ciqual and OFF use their own
    extras: FoodDraftExtras


def _assistant_food_draft(user_id: int, message_id: int, tool_use_id: str) -> _FoodDraft:
    """Raises NotFoundError: no such draft, or no longer valid."""
    with get_connection() as connection:
        tool_input = _assistant_draft_input(connection, user_id, message_id, tool_use_id, "draft_new_food")
    try:
        source = AssistantDraftSource(tool_input.get("source"))
        extras = food_draft_extras(tool_input)
        prefill = food_draft_prefill(tool_input) if source in DRAFT_MACROS_SOURCE else None
    except (ValueError, ValidationError) as error:
        raise NotFoundError("Draft not found.") from error
    return _FoodDraft(source, str(tool_input.get("code") or ""), prefill, extras)


def _apply_draft_extras(prefill_view: dict, extras: FoodDraftExtras) -> None:
    """What the assistant adds to a prefill: only what it does not bring (§8.12)."""
    values = {
        "category": extras.category.value if extras.category else None,
        "subtype": extras.subtype,
        "initial_state": extras.initial_state.value if extras.initial_state else None,
        "cooking_factor": extras.cooking_factor,
        "barcode": extras.barcode,
        "nutriscore": extras.nutriscore.value if extras.nutriscore else None,
        "nova": extras.nova,
        "yuka": extras.yuka,
        "macros_confidence": extras.macros_confidence,
        "default_amount_method": extras.default_amount_method.value if extras.default_amount_method else None,
    }
    for key, value in values.items():
        if value is not None and not str(prefill_view.get(key) or "").strip():
            prefill_view[key] = value
    if extras.favorite is not None:
        prefill_view["favorite"] = extras.favorite


def _assistant_recipe_draft(connection, user_id: int, message_id: int, tool_use_id: str) -> RecipeDraft:
    """A recipe draft of the assistant, validated again (§8.12, "Recetas").

    Raises:
        NotFoundError: no such draft, or no longer valid.
    """
    tool_input = _assistant_draft_input(connection, user_id, message_id, tool_use_id, "draft_recipe")
    try:
        return recipe_draft(tool_input)
    except ValidationError as error:
        raise NotFoundError("Draft not found.") from error


def _recipe_draft_form(connection, user_id: int, message_id: int, tool_use_id: str) -> RecipeDraftForm:
    """What the recipe create form shows of a draft: its fields and its ingredients
    with their names, read with their visibility rule.

    Raises:
        NotFoundError: no such draft, or one of its foods is no longer visible.
    """
    draft = _assistant_recipe_draft(connection, user_id, message_id, tool_use_id)
    try:
        foods = recipe_draft_foods(connection, user_id, draft)
    except ValidationError as error:
        raise NotFoundError("Draft not found.") from error
    plates = []
    for plate in draft.plates:
        lines = []
        for ingredient in plate.ingredients:
            if ingredient.new_dish is not None:
                dish = ingredient.new_dish
                name, final_state = dish.name, ingredient.final_state
                carbs = round(dish.nutrients.carbs_100g * ingredient.grams / 100, 1)
            else:
                item = foods[(ingredient.entry_type, ingredient.entry_id)]
                # What it is saved with (measurement §6.11).
                name, final_state, carbs = item.name, ingredient.final_state or default_final_state(item), None
            parts = [value.value for value in (ingredient.cooking, final_state, ingredient.conservation) if value]
            if ingredient.is_cooked_weight:
                parts.append("weighed cooked")
            lines.append(RecipeDraftLine(name, ingredient.grams, " · ".join(parts), carbs))
        plates.append((plate.name, tuple(lines)))
    return RecipeDraftForm(
        message_id=message_id,
        tool_use_id=tool_use_id,
        name=draft.name,
        meal_type=draft.meal_type.value if draft.meal_type else "",
        extra_meal_types=tuple(meal_type.value for meal_type in draft.extra_meal_types),
        servings="" if draft.servings is None else str(draft.servings),
        notes=draft.notes or "",
        plates=tuple(plates),
        favorite=draft.favorite is not False,
    )


def _manual_draft_prefill(connection, user_id: int, message_id: int, tool_use_id: str) -> dict:
    """What the dish create form shows of a dish draft (§8.12, "Platos manuales").

    Raises:
        NotFoundError: no such draft, or no longer valid.
    """
    tool_input = _assistant_draft_input(connection, user_id, message_id, tool_use_id, "draft_manual_intake")
    try:
        draft = manual_intake_draft(tool_input)
    except ValidationError as error:
        raise NotFoundError("Draft not found.") from error
    nutrients = draft.nutrients

    def text(value):
        return "" if value is None else value

    return {
        "name": draft.name,
        "description": draft.description or "",
        "subtype": draft.subtype or "",
        "origin": draft.origin or "",
        "default_portion": text(draft.default_portion),
        "calories_100g": text(nutrients.calories_100g),
        "carbs_100g": text(nutrients.carbs_100g),
        "sugars_100g": text(nutrients.sugars_100g),
        "fats_100g": text(nutrients.fats_100g),
        "saturated_100g": text(nutrients.saturated_100g),
        "proteins_100g": text(nutrients.proteins_100g),
        "fiber_100g": text(nutrients.fiber_100g),
        "caffeine": text(nutrients.caffeine),
        "alcohol": text(nutrients.alcohol),
        "glycemic_index": draft.glycemic_index.value if draft.glycemic_index else "",
        "ig_confidence": draft.ig_confidence,
        "macros_confidence": draft.macros_confidence,
        "macros_source": draft.macros_source.value,
        "default_amount_method": draft.default_amount_method.value if draft.default_amount_method else "",
        "favorite": draft.favorite is not False,
        "assistant_note": _MANUAL_DRAFT_NOTES.get(draft.macros_source, _MANUAL_DRAFT_NOTES[MacrosSource.AI_ESTIMATE]),
    }


_MANUAL_DRAFT_NOTES = {
    MacrosSource.AI_ESTIMATE: "Estimated by the assistant. Check every value before saving.",
    MacrosSource.OWN_ESTIMATE: "Written by the assistant from what you said. Check every value before saving.",
    MacrosSource.OFFICIAL: "Taken by the assistant from the place's information. Check every value before saving.",
    MacrosSource.LABEL: "Read by the assistant from the label. Check every value before saving.",
}


_ASSISTANT_DRAFT_NOTES = {
    AssistantDraftSource.LABEL: "Read by the assistant from the label. Check every value before saving.",
    AssistantDraftSource.ESTIMATE: "Estimated by the assistant. Check every value before saving.",
}


def _meal_created_event(connection, user_id: int, event_id: int) -> dict:
    """`mealCreated` (HX-Trigger, frontend §7.7): the page adds the new meal to its
    meal selector and leaves it chosen, so the next add goes to the same meal
    instead of creating another one."""
    event = get_intake_event(connection, user_id, event_id)
    return {"mealCreated": {"id": event_id, "label": meal_option_label(event)}}


def _prefill_view(
    prefill,
    barcode: str,
    source_id: str,
    source: PrefillSource | None = PrefillSource.OPEN_FOOD_FACTS,
    macros_source: MacrosSource | None = None,
) -> dict:
    """FoodPrefill -> presentation dict of the create form. `source` None is a
    prefill that is not a copy of an external record (a label read by the
    assistant, §8.12): no prefill_source, and its U1 is given apart."""
    nutrients = prefill.nutrients

    def text_or_empty(value):
        return "" if value is None else value

    return {
        "barcode": barcode,
        "prefill_source": source.value if source else "",
        "prefill_source_id": source_id if source else "",
        # U1 of the prefilled values (study §6.3); the user can change it.
        "macros_source": (macros_source or PREFILL_MACROS_SOURCE[source]).value,
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
        ("Macros from", MACROS_SOURCE_LABELS.get(item.macros_source)),
        ("Amount usually from", AMOUNT_METHOD_LABELS.get(item.default_amount_method)),
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
        ("Macros from", MACROS_SOURCE_LABELS.get(item.macros_source)),
        ("Amount usually from", AMOUNT_METHOD_LABELS.get(item.default_amount_method)),
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
            **portion_defaults(item),
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


def _view_value(field: str, value: str, allowed: tuple[tuple[str, str], ...]) -> str:
    """One value of the Food view: empty is the default (the first), unknown a 422."""
    clean = (value or "").strip() or allowed[0][1]
    if clean not in {option for _, option in allowed}:
        raise ValidationError("Unknown Food list.", fields={field: "invalid"})
    return clean


def _food_view(filter, search_mode, food_mode, favs_mode, recipes_mode, meal_type) -> FoodView:
    """The view of /food from its URL (frontend_conventions.md §5)."""
    meal_types = parse_recipe_meal_types(meal_type)
    return FoodView(
        filter=_view_value("filter", filter, FOOD_FILTERS),
        search_mode=_view_value("search_mode", search_mode, FOOD_SEARCH_TABS),
        food_mode=_view_value("food_mode", food_mode, FOOD_FOOD_TABS),
        favs_mode=_view_value("favs_mode", favs_mode, FOOD_FAVS_TABS),
        recipes_mode=_view_value("recipes_mode", recipes_mode, FOOD_RECIPES_TABS),
        meal_type=",".join(meal.value for meal in meal_types),
    )
