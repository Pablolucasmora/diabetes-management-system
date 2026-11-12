"""Tools of the assistant for logging meals (code_conventions.md §8.12).

What the model can do is exactly this list: search, add to the planned meal of
its conversation, read that meal, change the fields of that meal the user edits
in its cart card, and prepare a draft of a new food or recipe, which the user
reviews and saves in its create form. There is no tool that
deletes anything, archives or edits a food, dish or recipe, confirms a meal,
touches a consumed meal, its insulin or the fridge, logs insulin or changes
settings: the guarantee is that those tools do not exist, not an instruction
of the prompt.

Each tool calls the same queries and services as the equivalent route, with
the same validation (§7) and the owner in the SQL (§5.3). A wrong input goes
back to the model as a `tool_result` with `is_error`, never as a 500. The
macros of a food in the database are always read from the database: the model
only chooses the food, the amount and how the amount was obtained (U2).
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from DayBetes_food.database.queries import (
    apply_plate_offset_to_portions,
    create_intake_plate,
    create_portion_detail,
    get_catalog_item,
    get_ciqual_food,
    get_intake_event,
    get_manual_intake,
    get_mention_suggestions,
    get_off_product_by_code,
    get_portion_detail,
    get_recipe,
    link_assistant_conversation_event,
    list_intake_plates,
    list_portions_by_event,
    search_ciqual_foods,
    search_off_products,
    update_intake_event,
    update_intake_event_name,
    update_intake_event_notes,
    update_intake_plate_name,
    update_intake_plate_offset,
    update_portion_amount,
    update_portion_detail_fields,
    update_portion_flag,
    update_portion_offset,
)
from DayBetes_food.domain.assistant import (
    ASSISTANT_SEARCH_RESULTS_MAX,
    TOOL_RESULT_ADDED,
    TOOL_RESULT_CHANGED,
    TOOL_RESULT_DRAFT,
    food_draft_extras,
    food_draft_prefill,
    recipe_draft,
    tool_bool,
    tool_id,
    tool_int,
    tool_number,
    tool_text,
)
from DayBetes_food.domain.catalog import parse_barcode
from DayBetes_food.domain.ciqual_food import parse_ciqual_code
from DayBetes_food.domain.constants import (
    AmountMethod,
    AssistantDraftSource,
    ConservationMethod,
    CookingMethod,
    FoodCategory,
    FoodEntryType,
    FoodPhysicalState,
    MacrosSource,
    MealType,
    PortionDestination,
    PortionOrigin,
    Ripeness,
)
from DayBetes_food.domain.intake_event import (
    INTAKE_EVENT_NAME_MAX_LENGTH,
    INTAKE_EVENT_NOTES_MAX_LENGTH,
    IntakeEventUpdate,
)
from DayBetes_food.domain.intake_plate import (
    INTAKE_PLATE_NAME_MAX_LENGTH,
    IntakePlateCreate,
    check_offset_minutes,
)
from DayBetes_food.domain.manual_intake import (
    QuickAddRequest,
    parse_manual_intake_description,
    parse_manual_intake_name,
    parse_quick_add_weight,
    require_carbs,
)
from DayBetes_food.domain.nutrition import nutrients_from_totals
from DayBetes_food.domain.portion_detail import (
    PortionDetailCreate,
    PortionDetailUpdate,
    check_cooked_weight,
    default_final_state,
    parse_amount_grams,
    portion_macro_amount,
    raw_amount,
)
from DayBetes_food.domain.recipe import RecipeAddRequest, parse_recipe_add_servings
from DayBetes_food.errors import ConflictError, NotFoundError, ValidationError
from DayBetes_food.services.intake_event import (
    add_quick_add_to_meal,
    default_meal_type_now,
    new_plate_offset_minutes,
    plate_event_id,
    portion_event_id,
    resolve_event_plate,
    resolve_target_event,
    update_meal_time,
)
from DayBetes_food.services.recipe import add_recipe_to_meal, recipe_draft_foods
from DayBetes_food.time_utils import to_local

_ENTRY_TYPE_NAMES = {
    FoodEntryType.CATALOG: "food",
    FoodEntryType.MANUAL_INTAKE: "dish",
    FoodEntryType.RECIPE: "recipe",
}
_NULLABLE_NUMBER = {"type": ["number", "null"]}
_NULLABLE_INTEGER = {"type": ["integer", "null"]}
_NULLABLE_TEXT = {"type": ["string", "null"]}
_NULLABLE_BOOLEAN = {"type": ["boolean", "null"]}


class _IngredientEntryType(str, Enum):
    """What a recipe draft ingredient can be: a recipe is not an ingredient."""

    CATALOG = FoodEntryType.CATALOG.value
    MANUAL_INTAKE = FoodEntryType.MANUAL_INTAKE.value


def _nullable_enum(enum_cls, description: str | None = None) -> dict:
    schema = {"anyOf": [{"type": "string", "enum": [member.value for member in enum_cls]}, {"type": "null"}]}
    if description:
        schema["description"] = description
    return schema


_PLATE_ID = {
    "type": ["integer", "null"],
    "description": "Plate to add it to (an id from add_plate or the meal), or null for the meal's last plate.",
}
_OFFSET = {
    "type": ["integer", "null"],
    "description": "Minutes from the meal time to when it was eaten (-300 to 300).",
}
# How it was prepared: only what the user said, else null (§8.12, "Preparación").
_PREPARATION = {
    "cooking": _nullable_enum(CookingMethod),
    "final_state": _nullable_enum(FoodPhysicalState, "Physical state when eaten."),
    "conservation": _nullable_enum(ConservationMethod),
    "ripeness": _nullable_enum(Ripeness, "Fruits only."),
    "is_cooked_weight": {
        "type": ["boolean", "null"],
        "description": "True when the grams were weighed after cooking. Give the grams as weighed: "
        "the server converts them to raw with the food's cooking factor.",
    },
}


def _schema(properties: dict) -> dict:
    """Strict input schema: every property required (null when not given)."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _tool(name: str, description: str, properties: dict, *, strict: bool = True) -> dict:
    """`strict` makes the API guarantee the schema. The API caps the nullable
    parameters of strict tools at 16 in all, so the two tools with many optional
    numbers go without it: their handlers check every value anyway (§7)."""
    return {"name": name, "description": description, "input_schema": _schema(properties), "strict": strict}


# Fixed list, in a fixed order: it is part of the cached prefix (§8.12, cost).
TOOL_DEFINITIONS = [
    _tool(
        "search_my_foods",
        "Search the user's own foods, dishes and recipes (what they see in DayBetes). "
        "Favorites and the most eaten come first. Returns at most 5 rows: id, type, name, "
        "brand or origin, carbs per 100 g and serving in grams. Always try this first.",
        {"query": {"type": "string", "description": "A few words of the food name, in the user's language."}},
    ),
    _tool(
        "search_reference_foods",
        "Search a reference database the user has not added to their foods yet: Ciqual "
        "(generic foods, French food composition table) or Open Food Facts (packaged "
        "products by brand, or a barcode). A result cannot be added directly: use "
        "draft_new_food so the user saves it first.",
        {
            "query": {"type": "string"},
            "source": {"type": "string", "enum": ["ciqual", "open_food_facts"]},
        },
    ),
    _tool(
        "add_food",
        "Add one of the user's foods or dishes to the meal of this conversation. Give the "
        "amount either in grams or in servings (servings only if the food has a serving), "
        "and how the amount was obtained, following the rules of the system prompt. The "
        "server computes the macros from the database. Fill in how it was prepared only "
        "with what the user said; null the rest.",
        {
            "entry_type": {"type": "string", "enum": ["catalog", "manual_intake"]},
            "entry_id": {"type": "integer"},
            "grams": _NULLABLE_NUMBER,
            "servings": _NULLABLE_NUMBER,
            "amount_method": {"type": "string", "enum": [method.value for method in AmountMethod]},
            "plate_id": _PLATE_ID,
            **_PREPARATION,
        },
    ),
    _tool(
        "add_recipe",
        "Add one of the user's recipes to the meal of this conversation, in its own plate. "
        "Servings: how many were eaten (decimals allowed), or null for a recipe without "
        "servings, which is added whole.",
        {"recipe_id": {"type": "integer"}, "servings": _NULLABLE_NUMBER},
    ),
    _tool(
        "add_estimate",
        "Last resort, when the food is in none of the databases: add your own estimate as a "
        "quick add. Weight and carbs are required. Every macro is the total of what was "
        "eaten, not per 100 g. Leave a macro null when you cannot estimate it; never write "
        "0 for an unknown value.",
        {
            "name": {"type": "string"},
            "weight_g": {"type": "number"},
            "carbs_g": {"type": "number"},
            "sugars_g": _NULLABLE_NUMBER,
            "fats_g": _NULLABLE_NUMBER,
            "saturated_g": _NULLABLE_NUMBER,
            "proteins_g": _NULLABLE_NUMBER,
            "fiber_g": _NULLABLE_NUMBER,
            "calories_kcal": _NULLABLE_NUMBER,
            "note": {"type": ["string", "null"], "description": "How you estimated it, in a few words."},
            "plate_id": _PLATE_ID,
        },
        strict=False,
    ),
    _tool(
        "show_meal",
        "Read the meal of this conversation as it is now: its time, type, name and notes, "
        "and its plates with their foods, with the ids that add_food, update_plate and "
        "update_food take. The context block already has a summary: use this only when "
        "you need more.",
        {},
    ),
    _tool(
        "draft_new_food",
        "Prepare a new catalog food for the user to review and save; you never create foods. "
        "source ciqual or open_food_facts: give the code from search_reference_foods; the "
        "form takes the macros from there, so null them. source label: transcribe a "
        "nutrition label from a photo, per 100 g as printed. source estimate: your own "
        "estimate, only when the user asks for it. With label and estimate, name and "
        "carbs_100g are required and an unknown nutrient is null, never 0. With any "
        "source, also fill category, subtype, initial_state and, for foods weighed raw "
        "that change weight when cooked (rice, pasta, legumes, grains), cooking_factor "
        "(cooked/raw weight); serving_g only if the label prints it or the user says it, "
        "and barcode if you can read it. The user sees a button that opens the form.",
        {
            "source": {"type": "string", "enum": [source.value for source in AssistantDraftSource]},
            "code": _NULLABLE_TEXT,
            "name": _NULLABLE_TEXT,
            "brand": _NULLABLE_TEXT,
            "category": _nullable_enum(FoodCategory),
            "subtype": {"type": ["string", "null"], "description": "Specific kind, e.g. oats, yogurt, pasta."},
            "initial_state": _nullable_enum(FoodPhysicalState, "Physical state before preparation."),
            "cooking_factor": _NULLABLE_NUMBER,
            "serving_g": _NULLABLE_NUMBER,
            "barcode": _NULLABLE_TEXT,
            "calories_100g": _NULLABLE_NUMBER,
            "carbs_100g": _NULLABLE_NUMBER,
            "sugars_100g": _NULLABLE_NUMBER,
            "fats_100g": _NULLABLE_NUMBER,
            "saturated_100g": _NULLABLE_NUMBER,
            "proteins_100g": _NULLABLE_NUMBER,
            "fiber_100g": _NULLABLE_NUMBER,
            "caffeine_mg_100g": _NULLABLE_NUMBER,
            "alcohol_g_100g": _NULLABLE_NUMBER,
        },
        strict=False,
    ),
    _tool(
        "add_plate",
        "Add an empty plate to the meal of this conversation, only when the user splits "
        "the meal into courses eaten at different times (\"de primero\", \"de postre a los 20 "
        "minutos\"). Then add its foods with its plate_id. The name is optional: without "
        "one it takes the names of its foods.",
        {"name": _NULLABLE_TEXT, "offset_minutes": _OFFSET},
    ),
    _tool(
        "update_meal",
        "Change the meal of this conversation, only when the user says so: the local date "
        "(YYYY-MM-DD) and time (HH:MM) it was eaten, its type, its name or its notes. "
        "Omit or null what does not change.",
        {
            "date": _NULLABLE_TEXT,
            "time": _NULLABLE_TEXT,
            "meal_type": _nullable_enum(MealType),
            "name": _NULLABLE_TEXT,
            "notes": _NULLABLE_TEXT,
        },
        strict=False,
    ),
    _tool(
        "update_plate",
        "Change a plate of the meal of this conversation: its name or its offset. With "
        "apply_to_foods true, the offset is also written on every food already in it; "
        "otherwise only the foods added later take it. Omit or null what does not change.",
        {
            "plate_id": {"type": "integer"},
            "name": _NULLABLE_TEXT,
            "offset_minutes": _OFFSET,
            "apply_to_foods": _NULLABLE_BOOLEAN,
        },
        strict=False,
    ),
    _tool(
        "update_food",
        "Correct a food already in the meal of this conversation (food_id from the context "
        "or show_meal): its grams, how the amount was obtained, its offset or how it was "
        "prepared. Omit or null what does not change.",
        {
            "food_id": {"type": "integer"},
            "grams": _NULLABLE_NUMBER,
            "amount_method": _nullable_enum(AmountMethod),
            "offset_minutes": _OFFSET,
            **_PREPARATION,
        },
        strict=False,
    ),
    _tool(
        "draft_recipe",
        "Prepare a new recipe the user described, for them to review and save; you never "
        "create recipes. notes: the procedure, in the user's words, tidied into steps. "
        "One plate unless the user splits it into courses. Each ingredient is either one "
        "of the user's foods or dishes (entry_type and entry_id from search_my_foods or a "
        "\"/\" mention) or, only when the user calls it \"manual\" or \"quick add\", a "
        "new_dish with your estimated totals for its grams. Before this, a missing "
        "generic or packaged food must be saved with draft_new_food. Preparation as in "
        "add_food: only what the user said, null the rest.",
        {
            "name": {"type": "string"},
            "meal_type": _nullable_enum(MealType, "Main meal type it is usually eaten at."),
            "extra_meal_types": {
                "type": ["array", "null"],
                "items": {"type": "string", "enum": [meal_type.value for meal_type in MealType]},
            },
            "servings": _NULLABLE_INTEGER,
            "notes": _NULLABLE_TEXT,
            "plates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": _NULLABLE_TEXT,
                        "ingredients": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "entry_type": _nullable_enum(_IngredientEntryType),
                                    "entry_id": _NULLABLE_INTEGER,
                                    "new_dish": {
                                        "anyOf": [
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "name": {"type": "string"},
                                                    "carbs_g": {"type": "number"},
                                                    "sugars_g": _NULLABLE_NUMBER,
                                                    "fats_g": _NULLABLE_NUMBER,
                                                    "saturated_g": _NULLABLE_NUMBER,
                                                    "proteins_g": _NULLABLE_NUMBER,
                                                    "fiber_g": _NULLABLE_NUMBER,
                                                    "calories_kcal": _NULLABLE_NUMBER,
                                                    "macros_source": {
                                                        "type": "string",
                                                        "enum": ["ai_estimate", "own_estimate"],
                                                        "description": "own_estimate when the user gave the values.",
                                                    },
                                                },
                                                "required": ["name", "carbs_g"],
                                            },
                                            {"type": "null"},
                                        ]
                                    },
                                    "grams": {"type": "number"},
                                    "cooking": _PREPARATION["cooking"],
                                    "final_state": _PREPARATION["final_state"],
                                    "conservation": _PREPARATION["conservation"],
                                    "is_cooked_weight": _PREPARATION["is_cooked_weight"],
                                },
                                "required": ["grams"],
                            },
                        },
                    },
                    "required": ["ingredients"],
                },
            },
        },
        strict=False,
    ),
]


class ToolInputError(Exception):
    """An input the model can fix: it goes back as a tool error with this text."""


@dataclass
class ToolContext:
    """What the tools of one message share: the user, the conversation and its
    meal, which the first add creates when the conversation has none."""

    connection: object
    user_id: int
    conversation_id: int | None  # None until the first answer is stored
    event_id: int | None
    meal_created: bool = field(default=False)

    def target_event(self) -> int:
        """The planned meal to write to, created and linked on the first add.

        Raises:
            ConflictError: the meal was confirmed meanwhile.
            NotFoundError: the meal was deleted meanwhile.
        """
        event_id, created = resolve_target_event(self.connection, self.user_id, self.event_id)
        if created:
            self._link(event_id)
        return event_id

    def _link(self, event_id: int) -> None:
        link_assistant_conversation_event(self.connection, self.user_id, self.conversation_id, event_id, commit=False)
        self.event_id = event_id
        self.meal_created = True


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def _compact(row: dict) -> dict:
    """Leave out what is unknown: fewer tokens, and no null the model could read as 0."""
    return {key: value for key, value in row.items() if value not in (None, "")}


def _search_my_foods(ctx: ToolContext, tool_input: dict) -> dict:
    query = tool_text(tool_input.get("query"), "query", max_length=100, required=True)
    rows = get_mention_suggestions(ctx.connection, ctx.user_id, query, limit=ASSISTANT_SEARCH_RESULTS_MAX)
    return {
        "results": [
            _compact(
                {
                    "entry_type": row.entry_type.value,
                    "id": row.entry_id,
                    "kind": _ENTRY_TYPE_NAMES[row.entry_type],
                    "name": row.name,
                    "brand_or_origin": row.subtitle,
                    "carbs_100g": _round(row.carbs_100g),
                    "serving_g": _round(row.serving_g),
                    "favorite": row.is_favorite or None,
                }
            )
            for row in rows
        ]
    }


def _search_reference_foods(ctx: ToolContext, tool_input: dict) -> dict:
    query = tool_text(tool_input.get("query"), "query", max_length=100, required=True)
    source = AssistantDraftSource(tool_input.get("source"))
    if source is AssistantDraftSource.CIQUAL:
        foods = search_ciqual_foods(ctx.connection, ctx.user_id, query, limit=ASSISTANT_SEARCH_RESULTS_MAX)
        results = [
            _compact({"code": str(food.code), "name": food.name_es, "carbs_100g": _round(food.carbs_100g)})
            for food in foods
        ]
    else:
        products = search_off_products(ctx.connection, ctx.user_id, query, limit=ASSISTANT_SEARCH_RESULTS_MAX)
        results = [
            _compact(
                {
                    "code": product.code,
                    "name": product.name,
                    "brand": product.brand,
                    "carbs_100g": _round(product.carbs_100g),
                    "serving_g": _round(product.default_portion),
                }
            )
            for product in products
        ]
    return {"source": source.value, "results": results}


def _read_food(ctx: ToolContext, entry_type: FoodEntryType, entry_id: int):
    if entry_type is FoodEntryType.CATALOG:
        return get_catalog_item(ctx.connection, ctx.user_id, entry_id)
    return get_manual_intake(ctx.connection, ctx.user_id, entry_id)


def _add_food(ctx: ToolContext, tool_input: dict) -> dict:
    entry_type = FoodEntryType(tool_input.get("entry_type"))
    entry_id = tool_input.get("entry_id")
    if not isinstance(entry_id, int) or isinstance(entry_id, bool) or entry_id <= 0:
        raise ToolInputError("entry_id must be a positive integer.")
    item = _read_food(ctx, entry_type, entry_id)
    if item is None:
        raise ToolInputError(f"There is no {_ENTRY_TYPE_NAMES[entry_type]} with id {entry_id} for this user.")
    grams = tool_number(tool_input.get("grams"), "grams")
    servings = tool_number(tool_input.get("servings"), "servings")
    if (grams is None) == (servings is None):
        raise ToolInputError("Give either grams or servings, not both and not neither.")
    if servings is not None:
        if item.default_portion is None:
            raise ToolInputError(f"{item.name} has no serving: give grams.")
        grams = servings * item.default_portion
    try:
        grams = parse_amount_grams(grams)
    except ValidationError as error:
        raise ToolInputError("The amount must be greater than 0 g and at most 100000 g.") from error
    # The rules of U2 decide it, whatever the food's default (§8.12, study §6.3).
    amount_method = AmountMethod(tool_input.get("amount_method"))
    preparation = _preparation(tool_input)
    if "final_state" not in preparation and default_final_state(item) is not None:
        # Not said: the food's initial state, like every new portion (measurement §6.11).
        preparation["final_state"] = default_final_state(item)
    origin = PortionOrigin(entry_type.value)
    is_cooked_weight = bool(tool_bool(tool_input.get("is_cooked_weight"), "is_cooked_weight"))
    check_cooked_weight(origin, getattr(item, "cooking_factor", None), is_cooked_weight)

    event_id = ctx.target_event()
    plate_id = _target_plate(ctx, event_id, tool_input.get("plate_id"))
    create_portion_detail(
        ctx.connection,
        ctx.user_id,
        PortionDetailCreate(
            origin=origin,
            origin_id=entry_id,
            destination=PortionDestination.INTAKE_EVENT,
            destination_id=event_id,
            plate_id=plate_id,
            amount=grams,
            amount_method=amount_method,
            is_cooked_weight=is_cooked_weight,
            **preparation,
        ),
        commit=False,
    )
    # The same rule as the cart: weighed cooked counts the raw equivalent (§5.2).
    macro_grams = raw_amount(grams, origin, is_cooked_weight, getattr(item, "cooking_factor", None))
    carbs = item.carbs_100g * macro_grams / 100 if item.carbs_100g is not None else None
    return {
        TOOL_RESULT_ADDED: _compact(
            {
                "name": item.name,
                "grams": _round(grams),
                "carbs_g": _round(carbs),
                "amount_method": amount_method.value,
                "preparation": _preparation_text(preparation, is_cooked_weight) or None,
            }
        )
    }


_PREPARATION_ENUMS = {
    "cooking": CookingMethod,
    "final_state": FoodPhysicalState,
    "conservation": ConservationMethod,
    "ripeness": Ripeness,
}


def _preparation(tool_input: dict) -> dict:
    """The preparation fields the model gave; null ones are left out."""
    return {
        name: enum_cls(tool_input[name])
        for name, enum_cls in _PREPARATION_ENUMS.items()
        if tool_input.get(name) is not None
    }


def _preparation_text(preparation: dict, is_cooked_weight: bool) -> str:
    parts = [value.value for value in preparation.values()]
    if is_cooked_weight:
        parts.append("weighed cooked")
    return ", ".join(parts)


def _target_plate(ctx: ToolContext, event_id: int, raw_plate_id) -> int:
    """The plate an add goes to: the one given, of this meal, or the meal's last one
    (§8.12, "Platos"). New plates come only from add_plate."""
    if raw_plate_id is None:
        offset_minutes = new_plate_offset_minutes(get_intake_event(ctx.connection, ctx.user_id, event_id))
        return resolve_event_plate(ctx.connection, ctx.user_id, event_id, None, offset_minutes)
    plate_id = tool_id(raw_plate_id, "plate_id")
    try:
        return resolve_event_plate(ctx.connection, ctx.user_id, event_id, plate_id, None)
    except NotFoundError as error:
        raise ToolInputError(f"There is no plate {plate_id} in this meal.") from error


def _add_recipe(ctx: ToolContext, tool_input: dict) -> dict:
    recipe_id = tool_input.get("recipe_id")
    if not isinstance(recipe_id, int) or isinstance(recipe_id, bool) or recipe_id <= 0:
        raise ToolInputError("recipe_id must be a positive integer.")
    recipe = get_recipe(ctx.connection, ctx.user_id, recipe_id)
    if recipe is None:
        raise ToolInputError(f"There is no recipe with id {recipe_id} for this user.")
    raw_servings = tool_number(tool_input.get("servings"), "servings")
    if recipe.servings is None:
        servings = None
    elif raw_servings is None:
        raise ToolInputError(f"{recipe.name} has {recipe.servings} servings: say how many were eaten.")
    else:
        try:
            servings = parse_recipe_add_servings(raw_servings)
        except ValidationError as error:
            raise ToolInputError(str(error)) from error
    if ctx.event_id is not None:
        # Fails here, not halfway, if the meal was confirmed or deleted meanwhile.
        ctx.target_event()
    event_id = add_recipe_to_meal(
        ctx.connection,
        ctx.user_id,
        recipe_id,
        RecipeAddRequest(event_id=ctx.event_id, plate_id=None, servings=servings, preparations={}),
        default_meal_type=default_meal_type_now(ctx.connection, ctx.user_id),
    )
    if ctx.event_id is None:
        ctx._link(event_id)
    return {TOOL_RESULT_ADDED: _compact({"name": recipe.name, "servings": servings, "kind": "recipe"})}


_ESTIMATE_TOTALS = {
    "calories_100g": "calories_kcal",
    "carbs_100g": "carbs_g",
    "sugars_100g": "sugars_g",
    "fats_100g": "fats_g",
    "saturated_100g": "saturated_g",
    "proteins_100g": "proteins_g",
    "fiber_100g": "fiber_g",
}


def _add_estimate(ctx: ToolContext, tool_input: dict) -> dict:
    weight = tool_number(tool_input.get("weight_g"), "weight_g", required=True)
    totals = {}
    for field_100g, input_name in _ESTIMATE_TOTALS.items():
        value = tool_number(tool_input.get(input_name), input_name, required=(input_name == "carbs_g"))
        if value is not None and value < 0:
            raise ToolInputError(f"{input_name} cannot be negative.")
        totals[field_100g] = value
    try:
        weight_g = parse_quick_add_weight(weight)
        nutrients = nutrients_from_totals(totals, weight_g)
        require_carbs(nutrients)
        request = QuickAddRequest(
            name=parse_manual_intake_name(tool_input.get("name")),
            weight_g=weight_g,
            nutrients=nutrients,
            description=parse_manual_intake_description(tool_input.get("note")),
            # Both are the assistant's estimate (§8.12, study §6.3).
            macros_source=MacrosSource.AI_ESTIMATE,
            amount_method=AmountMethod.AI_ESTIMATE,
        )
    except ValidationError as error:
        raise ToolInputError(str(error)) from error
    event_id = ctx.target_event()
    plate_id = _target_plate(ctx, event_id, tool_input.get("plate_id"))
    add_quick_add_to_meal(ctx.connection, ctx.user_id, request, event_id, plate_id)
    return {
        TOOL_RESULT_ADDED: _compact(
            {
                "name": request.name,
                "grams": _round(weight_g),
                "carbs_g": _round(totals["carbs_100g"]),
                "amount_method": AmountMethod.AI_ESTIMATE.value,
                "kind": "estimate",
            }
        )
    }


def _show_meal(ctx: ToolContext, tool_input: dict) -> dict:
    if ctx.event_id is None:
        return {"plates": [], "note": "The meal is empty: nothing has been added yet."}
    event = get_intake_event(ctx.connection, ctx.user_id, ctx.event_id)
    if event is None:
        raise NotFoundError("intake_event_not_found")
    when = to_local(event.meal_time) if event.meal_time else None
    portions = list_portions_by_event(ctx.connection, ctx.user_id, ctx.event_id)
    plates = []
    for plate in list_intake_plates(ctx.connection, ctx.event_id):
        foods = []
        for portion in (p for p in portions if p.plate_id == plate.id):
            carbs_100g = portion.source.carbs_100g
            carbs = carbs_100g * portion_macro_amount(portion) / 100 if carbs_100g is not None else None
            foods.append(
                _compact(
                    {
                        "food_id": portion.id,
                        "name": portion.source.name,
                        "grams": _round(portion.amount),
                        "carbs_g": _round(carbs),
                        "amount_method": portion.amount_method.value if portion.amount_method else None,
                        "offset_minutes": portion.offset_minutes,
                        "cooking": portion.cooking.value if portion.cooking else None,
                        "final_state": portion.final_state.value if portion.final_state else None,
                        "conservation": portion.conservation.value if portion.conservation else None,
                        "ripeness": portion.ripeness.value if portion.ripeness else None,
                        "is_cooked_weight": portion.is_cooked_weight or None,
                    }
                )
            )
        plates.append(
            _compact(
                {"plate_id": plate.id, "name": plate.name, "offset_minutes": plate.offset_minutes, "foods": foods}
            )
        )
    return {
        "meal": _compact(
            {
                "date": f"{when:%Y-%m-%d}" if when else None,
                "time": f"{when:%H:%M}" if when else None,
                "meal_type": event.meal_type.value if event.meal_type else None,
                "name": event.name,
                "notes": event.notes,
            }
        ),
        "plates": plates,
    }


def _offset_text(minutes: int) -> str:
    return f"{minutes:+d} min"


def _meal_event(ctx: ToolContext) -> int:
    """The meal the edits act on: the conversation's, which must exist."""
    if ctx.event_id is None:
        raise ToolInputError("The meal is empty: there is nothing to change yet.")
    return ctx.event_id


def _add_plate(ctx: ToolContext, tool_input: dict) -> dict:
    name = tool_text(tool_input.get("name"), "name", max_length=INTAKE_PLATE_NAME_MAX_LENGTH)
    offset_minutes = check_offset_minutes(tool_int(tool_input.get("offset_minutes"), "offset_minutes"))
    event_id = ctx.target_event()
    plate_id = create_intake_plate(
        ctx.connection,
        IntakePlateCreate(intake_event_id=event_id, name=name, offset_minutes=offset_minutes),
        commit=False,
    )
    detail = ", ".join(part for part in (name, _offset_text(offset_minutes) if offset_minutes is not None else None) if part)
    return {"plate_id": plate_id, TOOL_RESULT_CHANGED: ["New plate" + (f": {detail}" if detail else "")]}


def _update_meal(ctx: ToolContext, tool_input: dict) -> dict:
    event_id = _meal_event(ctx)
    raw_date, raw_time = tool_input.get("date"), tool_input.get("time")
    meal_type = MealType(tool_input["meal_type"]) if tool_input.get("meal_type") is not None else None
    name = tool_text(tool_input.get("name"), "name", max_length=INTAKE_EVENT_NAME_MAX_LENGTH)
    notes = tool_input.get("notes")
    if notes is not None:
        if not isinstance(notes, str):
            raise ToolInputError("notes must be text.")
        # Kept as typed, like the cart (§7.3): only the ends are trimmed.
        notes = notes.strip() or None
        if notes and len(notes) > INTAKE_EVENT_NOTES_MAX_LENGTH:
            raise ToolInputError(f"notes can have at most {INTAKE_EVENT_NOTES_MAX_LENGTH} characters.")
    changed = []
    if raw_date is not None or raw_time is not None:
        try:
            local_date = datetime.strptime(str(raw_date), "%Y-%m-%d").date() if raw_date is not None else None
            local_time = datetime.strptime(str(raw_time), "%H:%M").time() if raw_time is not None else None
        except ValueError as error:
            raise ToolInputError("date must be YYYY-MM-DD and time HH:MM.") from error
        if local_time is None:
            event = get_intake_event(ctx.connection, ctx.user_id, event_id)
            if event is None or event.meal_time is None:
                raise NotFoundError("intake_event_not_found")
            local_time = to_local(event.meal_time).time()
        update_meal_time(ctx.connection, ctx.user_id, event_id, local_time, local_date, commit=False)
        changed.append(
            "Meal time: " + (f"{local_date:%Y-%m-%d} " if local_date else "") + f"{local_time:%H:%M}"
        )
    if meal_type is not None:
        update_intake_event(
            ctx.connection, user_id=ctx.user_id, event_id=event_id, data=IntakeEventUpdate(meal_type=meal_type), commit=False
        )
        changed.append(f"Meal type: {meal_type.value.replace('_', ' ')}")
    if name is not None:
        update_intake_event_name(ctx.connection, ctx.user_id, event_id, name, commit=False)
        changed.append(f"Meal name: {name}")
    if notes is not None:
        update_intake_event_notes(ctx.connection, ctx.user_id, event_id, notes, commit=False)
        changed.append("Meal notes")
    if not changed:
        raise ToolInputError("Nothing to change: give at least one field.")
    return {TOOL_RESULT_CHANGED: changed}


def _update_plate(ctx: ToolContext, tool_input: dict) -> dict:
    event_id = _meal_event(ctx)
    plate_id = tool_id(tool_input.get("plate_id"), "plate_id")
    try:
        if plate_event_id(ctx.connection, ctx.user_id, plate_id) != event_id:
            raise NotFoundError("plate_not_in_meal")
    except NotFoundError as error:
        raise ToolInputError(f"There is no plate {plate_id} in this meal.") from error
    name = tool_text(tool_input.get("name"), "name", max_length=INTAKE_PLATE_NAME_MAX_LENGTH)
    offset_minutes = check_offset_minutes(tool_int(tool_input.get("offset_minutes"), "offset_minutes"))
    apply_to_foods = bool(tool_bool(tool_input.get("apply_to_foods"), "apply_to_foods"))
    changed = []
    if name is not None:
        update_intake_plate_name(ctx.connection, plate_id, name, commit=False)
        changed.append(f"Plate name: {name}")
    if offset_minutes is not None:
        if apply_to_foods:
            if not apply_plate_offset_to_portions(ctx.connection, plate_id, offset_minutes, commit=False):
                raise NotFoundError("intake_plate_not_found")
            changed.append(f"Plate offset: {_offset_text(offset_minutes)}, applied to its foods")
        else:
            update_intake_plate_offset(ctx.connection, plate_id, offset_minutes, commit=False)
            changed.append(f"Plate offset: {_offset_text(offset_minutes)}, for the foods added next")
    if not changed:
        raise ToolInputError("Nothing to change: give a name or an offset.")
    return {TOOL_RESULT_CHANGED: changed}


def _update_food(ctx: ToolContext, tool_input: dict) -> dict:
    event_id = _meal_event(ctx)
    portion_id = tool_id(tool_input.get("food_id"), "food_id")
    try:
        portion = get_portion_detail(ctx.connection, ctx.user_id, portion_id)
        if portion_event_id(ctx.connection, ctx.user_id, portion) != event_id:
            raise NotFoundError("portion_not_in_meal")
    except NotFoundError as error:
        raise ToolInputError(f"There is no food {portion_id} in this meal: call show_meal.") from error
    grams = tool_number(tool_input.get("grams"), "grams")
    amount_method = (
        AmountMethod(tool_input["amount_method"]) if tool_input.get("amount_method") is not None else None
    )
    offset_minutes = check_offset_minutes(tool_int(tool_input.get("offset_minutes"), "offset_minutes"))
    is_cooked_weight = tool_bool(tool_input.get("is_cooked_weight"), "is_cooked_weight")
    preparation = _preparation(tool_input)
    if is_cooked_weight is not None:
        check_cooked_weight(
            portion.origin, portion.source.cooking_factor, is_cooked_weight, current=portion.is_cooked_weight
        )

    changed = []
    if grams is not None:
        update_portion_amount(ctx.connection, ctx.user_id, portion_id, grams, commit=False)
        changed.append(f"{_round(grams):g} g")
    if amount_method is not None:
        update_portion_flag(ctx.connection, ctx.user_id, portion_id, "amount_method", amount_method.value, commit=False)
        changed.append(f"amount from {amount_method.value.replace('_', ' ')}")
    if offset_minutes is not None:
        update_portion_offset(ctx.connection, ctx.user_id, portion_id, offset_minutes, commit=False)
        changed.append(f"offset {_offset_text(offset_minutes)}")
    # Last: these two are part of the row's key and can merge it into an equal row
    # of the same plate (measurement_conventions.md §4.6.4).
    if is_cooked_weight is not None and is_cooked_weight != portion.is_cooked_weight:
        update_portion_flag(ctx.connection, ctx.user_id, portion_id, "is_cooked_weight", is_cooked_weight, commit=False)
        changed.append("weighed cooked" if is_cooked_weight else "weighed raw")
    if preparation:
        try:
            get_portion_detail(ctx.connection, ctx.user_id, portion_id)
        except NotFoundError as error:
            raise ToolInputError(
                "The food was merged with an equal one of its plate before its preparation could change: call show_meal."
            ) from error
        update_portion_detail_fields(
            ctx.connection, ctx.user_id, portion_id, PortionDetailUpdate(**preparation), commit=False
        )
        changed.append(_preparation_text(preparation, False))
    if not changed:
        raise ToolInputError("Nothing to change: give at least one field.")
    result = {TOOL_RESULT_CHANGED: [f"{portion.source.name}: " + ", ".join(changed)]}
    try:
        updated = get_portion_detail(ctx.connection, ctx.user_id, portion_id)
    except NotFoundError:
        result["note"] = "It was merged with an equal food of its plate: call show_meal to see it."
    else:
        if updated.source.carbs_100g is not None:
            result["carbs_g"] = _round(updated.source.carbs_100g * portion_macro_amount(updated) / 100)
    return result


def _draft_new_food(ctx: ToolContext, tool_input: dict) -> dict:
    source = AssistantDraftSource(tool_input.get("source"))
    try:
        # Checked now so the model can fix it; the form reads it again (§7.13).
        food_draft_extras(tool_input)
        if source is AssistantDraftSource.CIQUAL:
            code = parse_ciqual_code(tool_input.get("code"))
            food = get_ciqual_food(ctx.connection, code) if code is not None else None
            if food is None:
                raise ToolInputError("Give the code of a Ciqual food from search_reference_foods.")
            draft = {"source": source.value, "code": str(food.code), "name": food.name_es}
        elif source is AssistantDraftSource.OPEN_FOOD_FACTS:
            code = parse_barcode(tool_input.get("code") or "")
            product = get_off_product_by_code(ctx.connection, code) if code else None
            if product is None:
                raise ToolInputError("Give the code of an Open Food Facts product from search_reference_foods.")
            draft = {"source": source.value, "code": product.code, "name": product.name}
        else:
            prefill = food_draft_prefill(tool_input)
            draft = {"source": source.value, "name": prefill.name}
    except ValidationError as error:
        raise ToolInputError(str(error)) from error
    return {TOOL_RESULT_DRAFT: draft, "note": "The user will review and save it, then come back."}


def _draft_recipe(ctx: ToolContext, tool_input: dict) -> dict:
    try:
        # Checked now so the model can fix it; the form reads it again (§7.13).
        draft = recipe_draft(tool_input)
        recipe_draft_foods(ctx.connection, ctx.user_id, draft)
    except NotFoundError as error:
        raise ToolInputError("An ingredient is not one of the user's foods or dishes: check its id.") from error
    except ValidationError as error:
        raise ToolInputError(str(error)) from error
    return {
        TOOL_RESULT_DRAFT: {"source": "recipe", "name": draft.name, "ingredients": draft.ingredient_count},
        "note": "The user will review and save it in the recipe form.",
    }


_HANDLERS = {
    "search_my_foods": _search_my_foods,
    "search_reference_foods": _search_reference_foods,
    "add_food": _add_food,
    "add_recipe": _add_recipe,
    "add_estimate": _add_estimate,
    "show_meal": _show_meal,
    "draft_new_food": _draft_new_food,
    "add_plate": _add_plate,
    "update_meal": _update_meal,
    "update_plate": _update_plate,
    "update_food": _update_food,
    "draft_recipe": _draft_recipe,
}


def run_tool(ctx: ToolContext, name: str, tool_input) -> tuple[str, bool]:
    """Run one tool call inside its own savepoint and return `(content, is_error)`.

    A tool that fails leaves nothing behind (§2.3) and its error goes back to the
    model, which can correct the call. What the user cannot fix through the model
    (a database failure) propagates.
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Unknown tool {name!r}.", True
    if not isinstance(tool_input, dict):
        return "The input must be an object.", True
    event_before, created_before = ctx.event_id, ctx.meal_created
    try:
        with ctx.connection.transaction():
            result = handler(ctx, tool_input)
    except ToolInputError as error:
        message, failed = str(error), True
    except (ValueError, ValidationError) as error:
        # ValueError: a value outside an enum the strict schema should have caught.
        message, failed = f"Invalid input: {error}", True
    except ConflictError:
        message, failed = "The meal of this conversation was already confirmed. Tell the user to choose another meal.", True
    except NotFoundError:
        message, failed = "The meal of this conversation no longer exists. Tell the user to choose another meal.", True
    else:
        return json.dumps(result, ensure_ascii=False, separators=(",", ":")), False
    # The savepoint was rolled back: a meal created by this call no longer exists.
    ctx.event_id, ctx.meal_created = event_before, created_before
    return message, failed
