"""Bootstrap of the dishes read from restaurant menus (code_conventions.md §11.2.12)."""


from DayBetes_food.database.bootstrap.helpers import _create_unique_index_once


def _ensure_menu_schema(cursor):
    """One row per owner, place and dish, ignoring case: saving a menu again
    updates its dishes instead of duplicating them. It also serves the list of
    places and the dishes of one place, which read by (users_id, lower(place))."""
    _create_unique_index_once(
        cursor,
        "uq_menu_item_users_id_place_name",
        "ON menu_item (users_id, lower(place), lower(name))",
    )
