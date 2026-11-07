"""Use cases of `fridge` that combine several queries or a domain rule
(code_conventions.md §1.2, §11.2.6; measurement_conventions.md §4.8).

The functions that write are the root coordinator of their unit of work (§1.1):
they open the transaction, so everything is written together or not at all (§2.3).
"""

from DayBetes_food.database.queries import (
    close_fridge,
    create_fridge,
    create_portion_detail,
    delete_fridge,
    get_fridge,
    list_fridges,
    list_portions_by_fridges,
    set_fridge_location,
)
from DayBetes_food.domain.constants import PortionDestination, StorageLocation
from DayBetes_food.domain.fridge import (
    FridgeCreate,
    FridgeItem,
    FridgeRead,
    FridgeStoreCommand,
    default_expires_at,
)
from DayBetes_food.domain.portion_detail import PortionDetailCreate
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


def store_in_fridge(connection, command: FridgeStoreCommand) -> int:
    """A new container with one food, stored now, with the default expiry of its place
    (§4.8.2). A fridge portion has no conservation of its own: the container says
    where it is (§4.8.4).

    Repeating it stores a second container: two tuppers are two rows (§9.6).

    Raises:
        NotFoundError: the food is not visible to the user anymore.
        ValidationError: the amount is outside the limits.
    """
    stored_at = utc_now()
    with connection.transaction():
        fridge_id = create_fridge(
            connection,
            FridgeCreate(
                user_id=command.user_id,
                location=command.location,
                stored_at=stored_at,
                expires_at=default_expires_at(command.location, stored_at),
            ),
            commit=False,
        )
        create_portion_detail(
            connection,
            command.user_id,
            PortionDetailCreate(
                origin=command.origin,
                origin_id=command.origin_id,
                destination=PortionDestination.FRIDGE,
                destination_id=fridge_id,
                amount=command.amount,
                cooking=command.cooking,
                final_state=command.final_state,
                strictly_weighed=command.strictly_weighed,
                is_cooked_weight=command.is_cooked_weight,
            ),
            commit=False,
        )
    return fridge_id


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
        if not delete_fridge(connection, user_id, fridge_id, commit=False):
            close_fridge(connection, user_id, fridge_id, commit=False)
