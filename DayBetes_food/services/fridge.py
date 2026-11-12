"""Use cases of `fridge` that combine several queries or a domain rule
(code_conventions.md §1.2, §11.2.6; measurement_conventions.md §4.8).

Most functions that write are the root coordinator of their unit of work (§1.1):
they open the transaction, so everything is written together or not at all (§2.3).
`take_from_fridge` and `return_to_fridge` are steps of a meal operation instead:
they run inside the transaction of its coordinator (§1.2).
"""

from collections import defaultdict
from dataclasses import replace

from DayBetes_food.database.queries import (
    close_fridge,
    create_fridge,
    create_portion_detail,
    delete_fridge,
    delete_fridge_portions,
    get_fridge,
    get_recipe,
    list_fridge_moves,
    list_fridges,
    list_portions_by_fridges,
    list_viewable_recipe_portions,
    lock_fridge,
    reopen_fridge,
    scale_fridge_portion_amounts,
    set_fridge_location,
    update_fridge_content_weight,
    update_portion_amount,
)
from DayBetes_food.domain.constants import AmountInputUnit, FridgeCloseReason, PortionDestination, StorageLocation
from DayBetes_food.domain.fridge import (
    FridgeCreate,
    FridgeItem,
    FridgeRead,
    FridgeContent,
    FridgeStoreCommand,
    KeepPart,
    LeftoverPlan,
    conservation_when_taken,
    merge_contents,
    default_expires_at,
    parse_take_fraction,
)
from DayBetes_food.domain.portion_detail import PortionDetailCreate, PortionDetailRead
from DayBetes_food.domain.recipe import RecipeAddRequest, scaled_recipe_amount
from DayBetes_food.errors import ConflictError, NotFoundError, ValidationError
from DayBetes_food.time_utils import utc_now


def _with_contents(connection, user_id: int, fridges: list[FridgeRead]) -> list[FridgeItem]:
    portions = list_portions_by_fridges(connection, user_id, [fridge.id for fridge in fridges])
    by_fridge: dict[int, list] = {}
    for portion in portions:
        by_fridge.setdefault(portion.destination_id, []).append(portion)
    return [FridgeItem(fridge=fridge, portions=tuple(by_fridge.get(fridge.id, ()))) for fridge in fridges]


def list_fridge_items(connection, user_id: int) -> list[FridgeItem]:
    """The user's open containers with their content, the soonest to expire first."""
    return _with_contents(connection, user_id, list_fridges(connection, user_id))


def get_fridge_item(connection, user_id: int, fridge_id: int) -> FridgeItem | None:
    """One open container of the user with its content, or None (§5.4)."""
    fridge = get_fridge(connection, user_id, fridge_id)
    return _with_contents(connection, user_id, [fridge])[0] if fridge else None


def create_fridge_container(connection, command: FridgeStoreCommand) -> int:
    """A new container with its contents, stored now, with the default expiry of its
    place (§4.8.2). Its portions have no conservation of their own: the container
    says where it is (§4.8.4). Runs inside the caller's transaction: /food/log and
    the confirm of a meal store their leftovers in their own (§4.8.5).

    Raises:
        NotFoundError: a food is not visible to the user anymore.
        ValidationError: an amount is outside the limits, or there is nothing to store.
    """
    if not command.contents:
        raise ValidationError("fridge_without_contents")
    stored_at = utc_now()
    fridge_id = create_fridge(
        connection,
        FridgeCreate(
            user_id=command.user_id,
            location=command.location,
            stored_at=stored_at,
            expires_at=default_expires_at(command.location, stored_at),
            name=command.name,
            content_weight=command.content_weight,
        ),
        commit=False,
    )
    for content in command.contents:
        create_portion_detail(
            connection,
            command.user_id,
            PortionDetailCreate(
                origin=content.origin,
                origin_id=content.origin_id,
                destination=PortionDestination.FRIDGE,
                destination_id=fridge_id,
                amount=content.amount,
                cooking=content.cooking,
                final_state=content.final_state,
                amount_method=content.amount_method,
                is_cooked_weight=content.is_cooked_weight,
            ),
            commit=False,
        )
    return fridge_id


def store_in_fridge(connection, command: FridgeStoreCommand) -> int:
    """`create_fridge_container` as its own unit of work. Repeating it stores a second
    container: two tuppers are two rows (§9.6)."""
    with connection.transaction():
        return create_fridge_container(connection, command)


def store_recipe_in_fridge(
    connection, user_id: int, recipe_id: int, location: StorageLocation, request: RecipeAddRequest
) -> int:
    """A recipe into a new container, as its step before adding asked: the servings
    scale it and the preparation can change, as when it goes into a meal (§4.7). Its
    plates are joined: a container has none. Repeating it stores another container.

    Raises:
        NotFoundError: the recipe is not visible to the user.
        ConflictError: "recipe_without_ingredients".
        ValidationError: an ingredient is not of this recipe, or an amount leaves the limits.
    """
    with connection.transaction():
        recipe = get_recipe(connection, user_id, recipe_id)
        if recipe is None:
            raise NotFoundError("Recipe not found.")
        portions = list_viewable_recipe_portions(connection, user_id, recipe_id)
        if not portions:
            raise ConflictError("recipe_without_ingredients")
        if not set(request.preparations) <= {portion.id for portion in portions}:
            raise ValidationError("An ingredient is not part of this recipe.")
        contents = []
        for portion in portions:
            preparation = request.preparations.get(portion.id)
            contents.append(
                FridgeContent(
                    origin=portion.origin,
                    origin_id=portion.origin_id,
                    amount=scaled_recipe_amount(portion.amount, request.servings, recipe.servings),
                    cooking=preparation.cooking if preparation else portion.cooking,
                    final_state=preparation.final_state if preparation else portion.final_state,
                    amount_method=portion.amount_method,
                    is_cooked_weight=portion.is_cooked_weight,
                )
            )
        return create_fridge_container(
            connection,
            FridgeStoreCommand(
                user_id=user_id, location=location, contents=merge_contents(contents), name=recipe.name
            ),
        )


def keep_part_in_fridge(
    connection,
    user_id: int,
    portion: PortionDetailRead,
    keep: KeepPart,
    location: StorageLocation,
    containers: int,
) -> None:
    """After cooking, before eating: `keep.fraction` of an ingredient of a planned
    meal stays on its plate and the rest goes into `containers` equal new containers
    (measurement §4.8.5). With a weighed split each one gets its share of the real
    weight. Deleting the meal later does not undo it: the food is in the fridge.
    Runs inside the caller's transaction, which already checked the meal is planned.

    Raises:
        NotFoundError: the ingredient or a food is not visible anymore.
        ValidationError: an amount leaves the limits.
    """
    share = (1.0 - keep.fraction) / containers
    contents = (
        FridgeContent(
            origin=portion.origin,
            origin_id=portion.origin_id,
            amount=portion.amount * share,
            cooking=portion.cooking,
            final_state=portion.final_state,
            amount_method=portion.amount_method,
            is_cooked_weight=portion.is_cooked_weight,
        ),
    )
    weight = keep.rest_weight / containers if keep.rest_weight is not None else None
    for _ in range(containers):
        create_fridge_container(
            connection,
            FridgeStoreCommand(user_id=user_id, location=location, contents=contents, content_weight=weight),
        )
    update_portion_amount(connection, user_id, portion.id, portion.amount * keep.fraction, commit=False)


def store_plate_leftovers(
    connection, user_id: int, plate_portions: list[PortionDetailRead], fraction: float, plan: LeftoverPlan
) -> None:
    """What was not eaten of a plate, `1 - fraction` of each ingredient, into
    `plan.containers` equal new containers (§4.8.5). Called by the confirm of the
    meal before its portions are scaled, inside its transaction."""
    if plan.location is None:
        return
    share = (1.0 - fraction) / plan.containers
    contents = merge_contents(
        FridgeContent(
            origin=portion.origin,
            origin_id=portion.origin_id,
            amount=portion.amount * share,
            cooking=portion.cooking,
            final_state=portion.final_state,
            amount_method=portion.amount_method,
            is_cooked_weight=portion.is_cooked_weight,
        )
        for portion in plate_portions
    )
    for _ in range(plan.containers):
        create_fridge_container(
            connection,
            FridgeStoreCommand(user_id=user_id, location=plan.location, contents=contents, name=plan.name),
        )


def move_fridge(connection, user_id: int, fridge_id: int, location: StorageLocation) -> bool:
    """Move a container and restart its expiry from now with the shelf life of its
    new place (§4.8.2). True when it moved; False when it was already there (no-op).

    Raises:
        NotFoundError: the container is not open or not the user's.
    """
    moved_at = utc_now()
    return set_fridge_location(
        connection, user_id, fridge_id, location, moved_at, default_expires_at(location, moved_at)
    )


def discard_fridge(connection, user_id: int, fridge_id: int) -> None:
    """Throw a container away (§11.2.6): deleted with its content when nothing eaten
    references it; closed otherwise, because those portions are clinical history.

    Repeating it is a 404: the container is no longer open.

    Raises:
        NotFoundError: the container is not open or not the user's.
    """
    with connection.transaction():
        # Locked first, in its own statement (§6.8): a take that commits while
        # this waits is then seen by delete_fridge, which closes the container
        # instead of deleting a row that an eaten portion now references.
        fridge = lock_fridge(connection, user_id, fridge_id)
        if fridge is None or fridge.closed_at is not None:
            raise NotFoundError("Container not found.")
        if not delete_fridge(connection, user_id, fridge_id, commit=False):
            close_fridge(connection, user_id, fridge_id, FridgeCloseReason.DISCARDED, commit=False)


def take_from_fridge(
    connection,
    user_id: int,
    fridge_id: int,
    raw_amount,
    unit: AmountInputUnit,
    event_id: int,
    plate_id: int,
) -> None:
    """Take a part of a container into a plate of a planned meal (measurement §4.8.3,
    §4.8.4). It is discounted now: the content left is scaled by `1 - fraction`, and
    taking all of it empties the container, which keeps its content as it was so
    that it can come back (§4.8.6). Runs inside the caller's transaction.

    The amount arrives as typed and becomes a fraction here, with the real weight
    of the locked container (§6.8): read before the lock, a take in grams that
    runs at the same time would be converted with a weight that no longer holds.

    Raises:
        NotFoundError: the container is not open or not the user's.
        ValidationError: the amount is not valid for this container, or an amount
            leaves the limits.
    """
    fridge = lock_fridge(connection, user_id, fridge_id)
    if fridge is None or fridge.closed_at is not None:
        raise NotFoundError("Container not found.")
    fraction = parse_take_fraction(raw_amount, unit, fridge.content_weight)
    conservation = conservation_when_taken(fridge, list_fridge_moves(connection, user_id, fridge_id), utc_now())
    for portion in list_portions_by_fridges(connection, user_id, [fridge_id]):
        create_portion_detail(
            connection,
            user_id,
            PortionDetailCreate(
                origin=portion.origin,
                origin_id=portion.origin_id,
                destination=PortionDestination.INTAKE_EVENT,
                destination_id=event_id,
                plate_id=plate_id,
                amount=portion.amount * fraction,
                cooking=portion.cooking,
                conservation=conservation,
                final_state=portion.final_state,
                amount_method=portion.amount_method,
                is_cooked_weight=portion.is_cooked_weight,
                source_fridge_id=fridge_id,
            ),
            commit=False,
        )
    if fraction >= 1.0:
        close_fridge(connection, user_id, fridge_id, FridgeCloseReason.EMPTIED, commit=False)
        return
    remaining = 1.0 - fraction
    scale_fridge_portion_amounts(connection, user_id, fridge_id, remaining, commit=False)
    if fridge.content_weight is not None:
        update_fridge_content_weight(connection, user_id, fridge_id, fridge.content_weight * remaining, commit=False)


def _preparation_key(portion: PortionDetailRead) -> tuple:
    """What makes two portions the same ingredient inside a container."""
    return (portion.origin, portion.origin_id, portion.cooking, portion.final_state, portion.is_cooked_weight)


def return_to_fridge(connection, user_id: int, portions: list[PortionDetailRead]) -> None:
    """Give back to their containers the portions of a planned meal taken from one,
    before they are deleted (measurement §4.8.6). An emptied container reopens with
    them; a discarded one takes nothing back. The real weight follows the same
    weight per gram as the content it had. Runs inside the caller's transaction.
    """
    taken_by_fridge: dict[int, list[PortionDetailRead]] = defaultdict(list)
    for portion in portions:
        if portion.source_fridge_id is not None:
            taken_by_fridge[portion.source_fridge_id].append(portion)
    # Always in the same order, so two requests lock the containers alike (§6.8).
    for fridge_id in sorted(taken_by_fridge):
        taken = taken_by_fridge[fridge_id]
        fridge = lock_fridge(connection, user_id, fridge_id)
        if fridge is None or fridge.closed_reason is FridgeCloseReason.DISCARDED:
            continue
        content = list_portions_by_fridges(connection, user_id, [fridge_id])
        content_total = sum(portion.amount for portion in content)
        weight_per_gram = (
            fridge.content_weight / content_total if fridge.content_weight is not None and content_total > 0 else None
        )
        returned_weight = (
            sum(portion.amount for portion in taken) * weight_per_gram if weight_per_gram is not None else None
        )
        if fridge.closed_at is not None:
            # What an emptied container kept was its content before the last take.
            delete_fridge_portions(connection, user_id, fridge_id, commit=False)
            content = []
            reopen_fridge(connection, user_id, fridge_id, returned_weight, commit=False)
        elif returned_weight is not None:
            update_fridge_content_weight(
                connection, user_id, fridge_id, fridge.content_weight + returned_weight, commit=False
            )
        _add_to_fridge_content(connection, user_id, fridge_id, content, taken)


def _add_to_fridge_content(
    connection, user_id: int, fridge_id: int, content: list[PortionDetailRead], returned: list[PortionDetailRead]
) -> None:
    """Sum each returned portion into the same ingredient of the container, or add it."""
    by_key = {_preparation_key(portion): portion for portion in content}
    for portion in returned:
        key = _preparation_key(portion)
        if key in by_key:
            existing = by_key[key]
            new_amount = existing.amount + portion.amount
            update_portion_amount(connection, user_id, existing.id, new_amount, commit=False)
            by_key[key] = replace(existing, amount=new_amount)
            continue
        portion_id = create_portion_detail(
            connection,
            user_id,
            PortionDetailCreate(
                origin=portion.origin,
                origin_id=portion.origin_id,
                destination=PortionDestination.FRIDGE,
                destination_id=fridge_id,
                amount=portion.amount,
                cooking=portion.cooking,
                final_state=portion.final_state,
                amount_method=portion.amount_method,
                is_cooked_weight=portion.is_cooked_weight,
            ),
            commit=False,
        )
        by_key[key] = replace(portion, id=portion_id)
