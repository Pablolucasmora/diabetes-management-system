"""Tools of the assistant for logging meals (code_conventions.md §8.12).

What the model can do is exactly this list: search, add to the planned meal of
its conversation, read that meal and prepare a draft of a new food. There is
no tool that deletes, archives or edits a food, dish or recipe, confirms a
meal, touches a consumed meal, logs insulin or changes settings: the guarantee
is that those tools do not exist, not an instruction of the prompt.

Each tool calls the same queries and services as the equivalent route, with
the same validation (§7) and the owner in the SQL (§5.3). A wrong input goes
back to the model as a `tool_result` with `is_error`, never as a 500. The
macros of a food in the database are always read from the database: the model
only chooses the food, the amount and how the amount was obtained (U2).
"""

import json
from dataclasses import dataclass, field

from DayBetes_food.database.queries import (
    create_portion_detail,
    get_catalog_item,
    get_ciqual_food,
    get_intake_event,
    get_manual_intake,
    get_mention_suggestions,
    get_off_product_by_code,
    get_recipe,
    link_assistant_conversation_event,
    list_portions_by_event,
    search_ciqual_foods,
    search_off_products,
)
from DayBetes_food.domain.assistant import (
    ASSISTANT_SEARCH_RESULTS_MAX,
    TOOL_RESULT_ADDED,
    TOOL_RESULT_DRAFT,
    label_draft_prefill,
    tool_number,
    tool_text,
)
from DayBetes_food.domain.catalog import parse_barcode
from DayBetes_food.domain.ciqual_food import parse_ciqual_code
from DayBetes_food.domain.constants import (
    AmountMethod,
    AssistantDraftSource,
    FoodEntryType,
    MacrosSource,
    PortionDestination,
    PortionOrigin,
)
from DayBetes_food.domain.manual_intake import (
    QuickAddRequest,
    parse_manual_intake_description,
    parse_manual_intake_name,
    parse_quick_add_weight,
    require_carbs,
)
from DayBetes_food.domain.nutrition import nutrients_from_totals
from DayBetes_food.domain.portion_detail import PortionDetailCreate, parse_amount_grams, portion_macro_amount
from DayBetes_food.domain.recipe import RecipeAddRequest, parse_recipe_add_servings
from DayBetes_food.errors import ConflictError, NotFoundError, ValidationError
from DayBetes_food.services.intake_event import (
    add_quick_add_to_meal,
    default_meal_type_now,
    new_plate_offset_minutes,
    resolve_event_plate,
    resolve_target_event,
)
from DayBetes_food.services.recipe import add_recipe_to_meal

_ENTRY_TYPE_NAMES = {
    FoodEntryType.CATALOG: "food",
    FoodEntryType.MANUAL_INTAKE: "dish",
    FoodEntryType.RECIPE: "recipe",
}
_NULLABLE_NUMBER = {"type": ["number", "null"]}
_NULLABLE_TEXT = {"type": ["string", "null"]}


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
        "server computes the macros from the database.",
        {
            "entry_type": {"type": "string", "enum": ["catalog", "manual_intake"]},
            "entry_id": {"type": "integer"},
            "grams": _NULLABLE_NUMBER,
            "servings": _NULLABLE_NUMBER,
            "amount_method": {"type": "string", "enum": [method.value for method in AmountMethod]},
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
        },
        strict=False,
    ),
    _tool(
        "show_meal",
        "List what is already in the meal of this conversation: name, grams and carbs of "
        "each item. Use it only when the user refers to what is already there.",
        {},
    ),
    _tool(
        "draft_new_food",
        "Prepare a new food for the user to review and save; you never create foods. "
        "source ciqual or open_food_facts: give the code from search_reference_foods and "
        "leave the rest null. source label: transcribe a nutrition label from a photo, per "
        "100 g as printed; name and carbs_100g are required, null what the label does not "
        "show. The user sees a button that opens the prefilled form.",
        {
            "source": {"type": "string", "enum": [source.value for source in AssistantDraftSource]},
            "code": _NULLABLE_TEXT,
            "name": _NULLABLE_TEXT,
            "brand": _NULLABLE_TEXT,
            "serving_g": _NULLABLE_NUMBER,
            "calories_100g": _NULLABLE_NUMBER,
            "carbs_100g": _NULLABLE_NUMBER,
            "sugars_100g": _NULLABLE_NUMBER,
            "fats_100g": _NULLABLE_NUMBER,
            "saturated_100g": _NULLABLE_NUMBER,
            "proteins_100g": _NULLABLE_NUMBER,
            "fiber_100g": _NULLABLE_NUMBER,
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

    event_id = ctx.target_event()
    offset_minutes = new_plate_offset_minutes(get_intake_event(ctx.connection, ctx.user_id, event_id))
    plate_id = resolve_event_plate(ctx.connection, ctx.user_id, event_id, None, offset_minutes)
    create_portion_detail(
        ctx.connection,
        ctx.user_id,
        PortionDetailCreate(
            origin=PortionOrigin(entry_type.value),
            origin_id=entry_id,
            destination=PortionDestination.INTAKE_EVENT,
            destination_id=event_id,
            plate_id=plate_id,
            amount=grams,
            amount_method=amount_method,
        ),
        commit=False,
    )
    carbs = item.carbs_100g * grams / 100 if item.carbs_100g is not None else None
    return {
        TOOL_RESULT_ADDED: _compact(
            {
                "name": item.name,
                "grams": _round(grams),
                "carbs_g": _round(carbs),
                "amount_method": amount_method.value,
            }
        )
    }


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
    add_quick_add_to_meal(ctx.connection, ctx.user_id, request, event_id, None)
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
        return {"items": [], "note": "The meal is empty: nothing has been added yet."}
    items = []
    for portion in list_portions_by_event(ctx.connection, ctx.user_id, ctx.event_id):
        carbs_100g = portion.source.carbs_100g
        carbs = carbs_100g * portion_macro_amount(portion) / 100 if carbs_100g is not None else None
        items.append(
            _compact({"name": portion.source.name, "grams": _round(portion.amount), "carbs_g": _round(carbs)})
        )
    return {"items": items}


def _draft_new_food(ctx: ToolContext, tool_input: dict) -> dict:
    source = AssistantDraftSource(tool_input.get("source"))
    try:
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
            # Checked now so the model can fix it; the form reads it again (§7.13).
            prefill = label_draft_prefill(tool_input)
            draft = {"source": source.value, "name": prefill.name}
    except ValidationError as error:
        raise ToolInputError(str(error)) from error
    return {TOOL_RESULT_DRAFT: draft, "note": "The user will review and save it, then come back."}


_HANDLERS = {
    "search_my_foods": _search_my_foods,
    "search_reference_foods": _search_reference_foods,
    "add_food": _add_food,
    "add_recipe": _add_recipe,
    "add_estimate": _add_estimate,
    "show_meal": _show_meal,
    "draft_new_food": _draft_new_food,
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
