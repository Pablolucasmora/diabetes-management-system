"""Use cases of `recipe` that combine several queries (code_conventions.md §1.2).

Each function is the root coordinator of its unit of work (§1.1): it opens the
transaction, so everything is written together or not at all (§2.3).
"""

from DayBetes_food.database.queries import (
    create_intake_event,
    create_intake_plate,
    create_manual_intake,
    create_portion_detail,
    create_recipe,
    create_recipe_plate,
    get_catalog_item,
    get_intake_event,
    get_intake_plate,
    get_manual_intake,
    get_planned_intake_event,
    get_recipe,
    list_intake_plates,
    list_portions_by_event,
    list_recipe_plates,
    list_viewable_recipe_portions,
    next_recipe_copy_name,
    set_user_favorite,
)
from DayBetes_food.domain.assistant import NewDishDraft, RecipeDraft
from DayBetes_food.domain.constants import (
    AmountMethod,
    FoodEntryType,
    IntakeEventState,
    MealType,
    PortionDestination,
    PortionOrigin,
)
from DayBetes_food.domain.intake_event import IntakeEventCreate
from DayBetes_food.domain.intake_plate import IntakePlateCreate, auto_offset_minutes
from DayBetes_food.domain.manual_intake import ManualIntakeCreate
from DayBetes_food.domain.portion_detail import (
    PortionDetailCreate,
    PortionDetailRead,
    check_cooked_weight,
    portion_defaults,
)
from DayBetes_food.domain.recipe import (
    RecipeAddRequest,
    RecipeCreate,
    recipe_meal_type_from_event,
    scaled_recipe_amount,
)
from DayBetes_food.errors import ConflictError, NotFoundError, ValidationError
from DayBetes_food.time_utils import utc_now


def _portions_to_recipe_plate(
    connection, user_id: int, recipe_id: int, recipe_plate_id: int, portions: list[PortionDetailRead]
) -> None:
    """Copy portions into a plate of a recipe, with their amount, preparation,
    amount_method and is_cooked_weight (measurement §6.11)."""
    for portion in portions:
        create_portion_detail(
            connection,
            user_id,
            PortionDetailCreate(
                origin=portion.origin,
                origin_id=portion.origin_id,
                destination=PortionDestination.RECIPE,
                destination_id=recipe_id,
                recipe_plate_id=recipe_plate_id,
                amount=portion.amount,
                cooking=portion.cooking,
                conservation=portion.conservation,
                final_state=portion.final_state,
                amount_method=portion.amount_method,
                is_cooked_weight=portion.is_cooked_weight,
            ),
            commit=False,
        )


def _create_recipe_from_plates(connection, user_id: int, event, name: str, plates: list[tuple]) -> int:
    """A personal recipe in favorites, from `(plate name, portions)` pairs."""
    if any(portion.source.is_quick_add for _, portions in plates for portion in portions):
        raise ConflictError("recipe_has_quick_add")
    try:
        recipe_id = create_recipe(
            connection,
            RecipeCreate(
                user_id=user_id,
                origin_root_id=None,
                name=name,
                meal_type=recipe_meal_type_from_event(event.meal_type),
                notes=None,
                servings=None,
            ),
            commit=False,
        )
    except ConflictError as exc:
        raise ConflictError("recipe_name_taken") from exc
    set_user_favorite(connection, user_id, FoodEntryType.RECIPE, recipe_id, True, commit=False)
    for plate_name, portions in plates:
        recipe_plate_id = create_recipe_plate(connection, user_id, recipe_id, name=plate_name, commit=False)
        _portions_to_recipe_plate(connection, user_id, recipe_id, recipe_plate_id, portions)
    return recipe_id


def save_plate_as_recipe(connection, user_id: int, plate_id: int, name: str) -> int:
    """Save a plate of a planned meal as a new recipe with one plate
    (frontend_conventions.md §7.13). `name` is already parsed. The offset is not
    copied: a recipe portion cannot have one.

    Repeating it is a conflict, not a second recipe: the name is already taken (§9.6).

    Raises:
        NotFoundError: the plate or its event does not exist or is not the user's.
        ConflictError: "recipe_without_portions", "recipe_has_quick_add",
            "recipe_name_taken" or "event_not_planned".
    """
    with connection.transaction():
        plate = get_intake_plate(connection, user_id, plate_id)
        event = _planned_event(connection, user_id, plate.intake_event_id)
        portions = [
            portion
            for portion in list_portions_by_event(connection, user_id, event.id)
            if portion.plate_id == plate.id
        ]
        if not portions:
            raise ConflictError("recipe_without_portions")
        # The recipe has a single plate, so its name would repeat the recipe's.
        return _create_recipe_from_plates(connection, user_id, event, name, [(None, portions)])


def save_event_as_recipe(connection, user_id: int, event_id: int, name: str) -> int:
    """Save a whole planned meal as a new recipe: one plate per plate with
    ingredients, in the order of the meal (measurement §4.6.1, §4.7). Empty plates are
    left out, and so is every offset.

    Raises:
        NotFoundError: the event does not exist or is not the user's.
        ConflictError: as `save_plate_as_recipe`.
    """
    with connection.transaction():
        event = _planned_event(connection, user_id, event_id)
        portions = list_portions_by_event(connection, user_id, event.id)
        plates = [
            (plate.name, [portion for portion in portions if portion.plate_id == plate.id])
            for plate in list_intake_plates(connection, event.id)
        ]
        plates = [(name_, rows) for name_, rows in plates if rows]
        if not plates:
            raise ConflictError("recipe_without_portions")
        return _create_recipe_from_plates(connection, user_id, event, name, plates)


def _planned_event(connection, user_id: int, event_id: int):
    try:
        get_planned_intake_event(connection, user_id, event_id)
    except ConflictError as exc:
        raise ConflictError("event_not_planned") from exc
    event = get_intake_event(connection, user_id, event_id)
    if event is None:
        raise NotFoundError("intake_event_not_found")
    return event


def copy_recipe(connection, user_id: int, recipe_id: int) -> int:
    """Copy a recipe the viewer may see as their own personal, editable recipe, in
    their favorites (code_conventions.md §11.2.2).

    It copies the notes, the servings, the plates with ingredients and each ingredient.
    The tags are not copied, as in the other food tables. Repeating it makes another
    copy, also as in the other food tables.

    Raises:
        NotFoundError: the recipe does not exist or the viewer cannot see it.
        ConflictError: another request took the copy's name.
    """
    with connection.transaction():
        source = get_recipe(connection, user_id, recipe_id)
        if source is None:
            raise NotFoundError("Recipe not found.")
        copy_id = create_recipe(
            connection,
            RecipeCreate(
                user_id=user_id,
                origin_root_id=source.origin_root_id or source.id,
                name=next_recipe_copy_name(connection, user_id, source.name),
                meal_type=source.meal_type,
                extra_meal_types=source.extra_meal_types,
                notes=source.notes,
                servings=source.servings,
            ),
            commit=False,
        )
        set_user_favorite(connection, user_id, FoodEntryType.RECIPE, copy_id, True, commit=False)
        for plate, portions in recipe_plates_with_portions(connection, user_id, source.id):
            recipe_plate_id = create_recipe_plate(connection, user_id, copy_id, name=plate.name, commit=False)
            _portions_to_recipe_plate(connection, user_id, copy_id, recipe_plate_id, portions)
    return copy_id


def recipe_plates_with_portions(connection, user_id: int, recipe_id: int) -> list[tuple]:
    """`(plate, portions)` of a recipe the viewer may see, in order, without empty plates."""
    portions = list_viewable_recipe_portions(connection, user_id, recipe_id)
    groups = [
        (plate, [portion for portion in portions if portion.recipe_plate_id == plate.id])
        for plate in list_recipe_plates(connection, user_id, recipe_id)
    ]
    return [(plate, rows) for plate, rows in groups if rows]


def add_recipe_to_meal(
    connection, user_id: int, recipe_id: int, request: RecipeAddRequest, *, default_meal_type: MealType
) -> int:
    """Add a recipe to a meal, as the frontend's previous step asked (§4.6.5, §4.7).

    - A new meal takes the recipe's meal type and name; without a meal type,
      `default_meal_type`.
    - A recipe with one plate goes into the chosen plate or, without one, into a new
      plate named after the recipe. One with several plates always creates its own,
      with their names, and ignores the chosen plate.
    - Amounts scale with the chosen servings. The preparation can be changed for this
      meal, and it is not written to the recipe; amount_method and is_cooked_weight
      are copied (measurement §6.11).
    - Same key in the plate -> the amounts add up (§4.6.4).

    Repeating it adds the recipe again: it is a new serving, not a duplicate (§9.6).

    Returns:
        The id of the meal.

    Raises:
        NotFoundError: the recipe, meal or plate does not exist or is not visible.
        ConflictError: "recipe_without_ingredients", or the meal is no longer planned.
        ValidationError: an ingredient is not of this recipe, or an amount leaves the limits.
    """
    with connection.transaction():
        recipe = get_recipe(connection, user_id, recipe_id)
        if recipe is None:
            raise NotFoundError("Recipe not found.")
        groups = recipe_plates_with_portions(connection, user_id, recipe_id)
        if not groups:
            raise ConflictError("recipe_without_ingredients")
        known_ids = {portion.id for _, portions in groups for portion in portions}
        if not set(request.preparations) <= known_ids:
            raise ValidationError("An ingredient is not part of this recipe.")

        if request.event_id is not None:
            event_id = get_planned_intake_event(connection, user_id, request.event_id)
        else:
            event_id = create_intake_event(
                connection,
                IntakeEventCreate(
                    user_id=user_id,
                    state=IntakeEventState.PLANNED,
                    meal_type=recipe.meal_type or default_meal_type,
                    name=recipe.name,
                ),
                commit=False,
            )
        event = get_intake_event(connection, user_id, event_id)
        offset = auto_offset_minutes(event.meal_time if event else None, utc_now())

        single_plate = len(groups) == 1
        for plate, portions in groups:
            if single_plate and request.plate_id is not None:
                target = get_intake_plate(connection, user_id, request.plate_id)
                if target.intake_event_id != event_id:
                    raise NotFoundError(f"Intake plate {request.plate_id} does not belong to event {event_id}")
                target_plate_id = target.id
            else:
                target_plate_id = create_intake_plate(
                    connection,
                    IntakePlateCreate(
                        intake_event_id=event_id,
                        name=recipe.name if single_plate else plate.name,
                        offset_minutes=offset,
                    ),
                    commit=False,
                )
            for portion in portions:
                preparation = request.preparations.get(portion.id)
                create_portion_detail(
                    connection,
                    user_id,
                    PortionDetailCreate(
                        origin=portion.origin,
                        origin_id=portion.origin_id,
                        destination=PortionDestination.INTAKE_EVENT,
                        destination_id=event_id,
                        plate_id=target_plate_id,
                        amount=scaled_recipe_amount(portion.amount, request.servings, recipe.servings),
                        cooking=preparation.cooking if preparation else portion.cooking,
                        conservation=preparation.conservation if preparation else portion.conservation,
                        final_state=preparation.final_state if preparation else portion.final_state,
                        amount_method=portion.amount_method,
                        is_cooked_weight=portion.is_cooked_weight,
                    ),
                    commit=False,
                )
    return event_id


def recipe_draft_foods(connection, user_id: int, draft: RecipeDraft) -> dict:
    """The user's foods and dishes a recipe draft uses, read again with their
    visibility rule (§8.12, "Recetas"), by `(entry_type, entry_id)`.

    Raises:
        NotFoundError: one of them no longer exists or is not visible to the user.
        ValidationError: a cooked weight on a food without a cooking factor.
    """
    foods = {}
    for plate in draft.plates:
        for ingredient in plate.ingredients:
            if ingredient.entry_type is None:
                continue
            key = (ingredient.entry_type, ingredient.entry_id)
            if key not in foods:
                if ingredient.entry_type is FoodEntryType.CATALOG:
                    item = get_catalog_item(connection, user_id, ingredient.entry_id)
                else:
                    item = get_manual_intake(connection, user_id, ingredient.entry_id)
                if item is None or getattr(item, "is_quick_add", False):
                    raise NotFoundError("recipe_draft_food_not_found")
                foods[key] = item
            origin = PortionOrigin(ingredient.entry_type.value)
            check_cooked_weight(origin, getattr(foods[key], "cooking_factor", None), ingredient.is_cooked_weight)
    return foods


def create_recipe_from_draft(
    connection, user_id: int, draft: RecipeDraft, header: RecipeCreate, favorite: bool
) -> int:
    """Save a recipe draft of the assistant (§8.12, "Recetas"): the recipe with the
    header the user reviewed in the form, its plates, the new dishes and the
    ingredients, all or nothing. An ingredient without a final state takes its
    food's initial state (measurement §6.11).

    Raises:
        NotFoundError: an ingredient no longer exists or is not visible to the user.
        ValidationError: a cooked weight on a food without a cooking factor.
        ConflictError: the recipe name, or a new dish's name, is already taken.
    """
    with connection.transaction():
        foods = recipe_draft_foods(connection, user_id, draft)
        recipe_id = create_recipe(connection, header, commit=False)
        set_user_favorite(connection, user_id, FoodEntryType.RECIPE, recipe_id, favorite, commit=False)
        for plate in draft.plates:
            recipe_plate_id = create_recipe_plate(connection, user_id, recipe_id, name=plate.name, commit=False)
            for ingredient in plate.ingredients:
                if ingredient.new_dish is not None:
                    origin = PortionOrigin.MANUAL_INTAKE
                    origin_id = create_manual_intake(connection, _new_dish(user_id, ingredient.new_dish), commit=False)
                    defaults = {"amount_method": AmountMethod.AI_ESTIMATE, "final_state": None}
                else:
                    item = foods[(ingredient.entry_type, ingredient.entry_id)]
                    origin, origin_id = PortionOrigin(ingredient.entry_type.value), item.id
                    defaults = portion_defaults(item)
                create_portion_detail(
                    connection,
                    user_id,
                    PortionDetailCreate(
                        origin=origin,
                        origin_id=origin_id,
                        destination=PortionDestination.RECIPE,
                        destination_id=recipe_id,
                        recipe_plate_id=recipe_plate_id,
                        amount=ingredient.grams,
                        cooking=ingredient.cooking,
                        conservation=ingredient.conservation,
                        final_state=ingredient.final_state or defaults["final_state"],
                        amount_method=defaults["amount_method"],
                        is_cooked_weight=ingredient.is_cooked_weight,
                    ),
                    commit=False,
                )
        return recipe_id


def _new_dish(user_id: int, dish: NewDishDraft) -> ManualIntakeCreate:
    """A reusable dish with the assistant's estimate (§8.12): never a quick add,
    which cannot be an ingredient (§11.2.3)."""
    return ManualIntakeCreate(
        created_by=user_id,
        origin_root_id=None,
        name=dish.name,
        description=None,
        subtype=None,
        origin=None,
        default_portion=None,
        nutrients=dish.nutrients,
        glycemic_index=None,
        ig_confidence=None,
        macros_confidence=None,
        macros_source=dish.macros_source,
        default_amount_method=None,
    )
