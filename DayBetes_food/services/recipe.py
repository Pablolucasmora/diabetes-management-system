"""Use cases of `recipe` that combine several queries (code_conventions.md §1.2)."""

from DayBetes_food.database.queries import (
    add_recipe,
    create_portion_detail,
    get_intake_event,
    get_intake_plate,
    list_portions_by_event,
    set_user_favorite,
)
from DayBetes_food.domain.constants import PortionDestination
from DayBetes_food.domain.food import normalize_food_text
from DayBetes_food.domain.intake_plate import derive_plate_name
from DayBetes_food.domain.portion_detail import PortionDetailCreate
from DayBetes_food.domain.recipe import RECIPE_NAME_MAX_LENGTH
from DayBetes_food.errors import ConflictError, NotFoundError, ValidationError


def save_plate_as_recipe(connection, user_id: int, plate_id: int) -> int:
    """Save a cart plate as a new personal recipe, marked as favorite.

    Provisional until the `recipe` audit (frontend_conventions.md §7.13). It
    is the root coordinator of its unit of work (§1.1): it opens the
    transaction, so the recipe, its favorite and every ingredient are written
    together or not at all (§2.3).

    - The name is the plate's visible one: its own, or the derived one
      (measurement_conventions.md §4.6.3), as the header shows it.
    - The meal type is the event's.
    - The recipe is born personal (§11.4.1) and in the owner's favorites.
    - Each portion is copied with its amount, preparation, strictly_weighed
      and is_cooked_weight, as copying a recipe does. The offset is not
      copied: a recipe portion cannot have one (ck_portion_detail_offset_only_for_event).

    Repeating the request is a conflict, not a second recipe: the name is
    already taken by the first one (uq_recipe_personal_name, §9.6).

    Returns:
        The id of the new recipe.

    Raises:
        NotFoundError: the plate or its event does not exist or is not the user's.
        ConflictError("plate_without_portions"): there is nothing to save.
        ConflictError("plate_has_quick_add"): a quick add cannot go into a
            recipe (code_conventions.md §11.2.3).
        ConflictError("recipe_name_taken"): the user already has a personal
            recipe with that name.
        ValidationError("recipe_name_too_long"): longer than RECIPE_NAME_MAX_LENGTH
            (§7.3, never truncated).
    """
    with connection.transaction():
        plate = get_intake_plate(connection, user_id, plate_id)
        event = get_intake_event(connection, user_id, plate.intake_event_id)
        if event is None:
            raise NotFoundError("intake_event_not_found")

        # Same query and order (insertion, pd.id) the cart renders with, so
        # the derived name is the one the user sees in the header.
        portions = [
            portion
            for portion in list_portions_by_event(connection, user_id, event.id)
            if portion.plate_id == plate.id
        ]
        if not portions:
            raise ConflictError("plate_without_portions")
        if any(portion.source.is_quick_add for portion in portions):
            raise ConflictError("plate_has_quick_add")

        name = normalize_food_text(
            plate.name or derive_plate_name([portion.source.name for portion in portions])
        )
        if len(name) > RECIPE_NAME_MAX_LENGTH:
            raise ValidationError("recipe_name_too_long")

        try:
            recipe_id = add_recipe(
                connection,
                users_id=user_id,
                name=name,
                meal_type=event.meal_type.value if event.meal_type is not None else None,
                commit=False,
            )
        except ConflictError as exc:
            raise ConflictError("recipe_name_taken") from exc

        if not set_user_favorite(connection, user_id, "recipe", recipe_id, True, commit=False):
            # Only possible with an invalid argument: a bug, not a user error.
            raise RuntimeError("recipe_favorite_not_saved")

        for portion in portions:
            create_portion_detail(
                connection,
                user_id,
                PortionDetailCreate(
                    origin=portion.origin,
                    origin_id=portion.origin_id,
                    destination=PortionDestination.RECIPE,
                    destination_id=recipe_id,
                    amount=portion.amount,
                    cooking=portion.cooking,
                    conservation=portion.conservation,
                    final_state=portion.final_state,
                    strictly_weighed=portion.strictly_weighed,
                    is_cooked_weight=portion.is_cooked_weight,
                ),
                commit=False,
            )
    return recipe_id
