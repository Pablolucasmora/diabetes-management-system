"""CRUD of `menu_item`: dishes read from restaurant menus (code_conventions.md
§8.12, "Cartas"; §11.2.10). Private: every statement filters by its owner."""

from DayBetes_food.database.queries.crud import _escape_like, _execute_query, _execute_query_many
from DayBetes_food.domain.constants import MenuSection
from DayBetes_food.domain.menu import MenuItemCreate, MenuItemRead, MenuPlace
from DayBetes_food.domain.search_text import normalize_search_text, search_text_sql


def _item(row) -> MenuItemRead:
    return MenuItemRead(
        id=int(row["id"]),
        place=row["place"],
        name=row["name"],
        description=row["description"],
        section=MenuSection(row["section"]),
        price=float(row["price"]) if row["price"] is not None else None,
        updated_at=row["updated_at"],
    )


def save_menu_items(connection, user_id: int, place: str, items: list[MenuItemCreate]) -> int:
    """Create or update the dishes of one place, inside the caller's transaction. A
    dish already saved (same place and name, ignoring case) takes the new
    description, section and price (§6.3). Returns how many were saved."""
    for item in items:
        _execute_query(
            connection,
            """
            INSERT INTO menu_item (users_id, place, name, description, section, price)
            VALUES (%(user_id)s, %(place)s, %(name)s, %(description)s, %(section)s, %(price)s)
            ON CONFLICT (users_id, lower(place), lower(name)) DO UPDATE
            SET description = EXCLUDED.description,
                section = EXCLUDED.section,
                price = EXCLUDED.price,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id;
            """,
            {
                "user_id": user_id,
                "place": place,
                "name": item.name,
                "description": item.description,
                "section": item.section.value,
                "price": item.price,
            },
            commit=False,
        )
    return len(items)


def search_menu_items(
    connection, user_id: int, query: str, place: str | None, limit: int
) -> list[MenuItemRead]:
    """The user's saved dishes whose name, description or place has every word of
    `query`, ignoring case and accents; only those of `place` when it is given.
    Names that start with the query first."""
    words = normalize_search_text(query).split()
    if not words:
        return []
    haystack = search_text_sql("(name || ' ' || coalesce(description, '') || ' ' || place)")
    conditions = [f"{haystack} LIKE %(w{i})s" for i in range(len(words))]
    params = {f"w{i}": f"%{_escape_like(word)}%" for i, word in enumerate(words)}
    if place:
        conditions.append(f"{search_text_sql('place')} LIKE %(place)s")
        params["place"] = f"%{_escape_like(normalize_search_text(place))}%"
    rows = _execute_query_many(
        connection,
        f"""
        SELECT id, place, name, description, section, price, updated_at
        FROM menu_item
        WHERE users_id = %(user_id)s AND {' AND '.join(conditions)}
        ORDER BY ({search_text_sql('name')} LIKE %(prefix)s) DESC, updated_at DESC, id
        LIMIT %(limit)s;
        """,
        {**params, "user_id": user_id, "prefix": f"{_escape_like(words[0])}%", "limit": int(limit)},
        commit=False,
    )
    return [_item(row) for row in rows]


def list_menu_places(connection, user_id: int) -> list[MenuPlace]:
    """The user's places with a saved menu, the latest saved first."""
    rows = _execute_query_many(
        connection,
        """
        SELECT min(place) AS place, count(*) AS item_count, max(updated_at) AS updated_at
        FROM menu_item
        WHERE users_id = %(user_id)s
        GROUP BY lower(place)
        ORDER BY max(updated_at) DESC;
        """,
        {"user_id": user_id},
        commit=False,
    )
    return [MenuPlace(row["place"], int(row["item_count"]), row["updated_at"]) for row in rows]


def list_menu_items(connection, user_id: int, place: str) -> list[MenuItemRead]:
    """The dishes of one place of the user, by name; empty if it has none."""
    rows = _execute_query_many(
        connection,
        """
        SELECT id, place, name, description, section, price, updated_at
        FROM menu_item
        WHERE users_id = %(user_id)s AND lower(place) = lower(%(place)s)
        ORDER BY lower(name), id;
        """,
        {"user_id": user_id, "place": place},
        commit=False,
    )
    return [_item(row) for row in rows]


def delete_menu_item(connection, user_id: int, item_id: int) -> str | None:
    """Delete one dish of the user; returns its place, or None if it is not theirs."""
    row = _execute_query(
        connection,
        "DELETE FROM menu_item WHERE id = %(item_id)s AND users_id = %(user_id)s RETURNING place;",
        {"item_id": item_id, "user_id": user_id},
        commit=False,
    )
    return row["place"] if row else None


def delete_menu_place(connection, user_id: int, place: str) -> int:
    """Delete every dish of one place of the user; returns how many."""
    rows = _execute_query_many(
        connection,
        "DELETE FROM menu_item WHERE users_id = %(user_id)s AND lower(place) = lower(%(place)s) RETURNING id;",
        {"user_id": user_id, "place": place},
        commit=False,
    )
    return len(rows)
