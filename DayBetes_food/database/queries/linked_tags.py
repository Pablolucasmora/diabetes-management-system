"""Queries for the `linked_tags` bridge table (code_conventions.md §11.2.8).

A link is private: one user put one of their tags (or a system tag) on one
food, dish or recipe they can see. Every query carries the user in the SQL
(§5.3); nobody reads another user's links.
"""

from psycopg import sql
from psycopg.errors import ForeignKeyViolation

from DayBetes_food.database.mappers import tag_read_from_row
from DayBetes_food.database.queries.crud import (
    _RECIPE_VISIBLE,
    _execute_query,
    _execute_query_many,
    _food_visibility_sql,
)
from DayBetes_food.domain.constants import FoodEntryType, PortionOrigin
from DayBetes_food.domain.tag import TagRead
from DayBetes_food.errors import NotFoundError

_ENTRY_COLUMNS = {  # technical whitelist (§4.6); each table is named after its entry type
    FoodEntryType.CATALOG: "catalog_id",
    FoodEntryType.MANUAL_INTAKE: "manual_intake_id",
    FoodEntryType.RECIPE: "recipe_id",
}


def _visible_sql(entry_type: FoodEntryType) -> str:
    """What the user can see, retained foods included: what they can use, they can tag."""
    if entry_type is FoodEntryType.RECIPE:
        return _RECIPE_VISIBLE
    return _food_visibility_sql(PortionOrigin(entry_type.value), "entity", include_retained=True)


def list_entry_tags(connection, user_id: int, entry_type: FoodEntryType, entry_id: int) -> list[TagRead]:
    """The tags this user put on the entry: system ones first, then by name."""
    query = sql.SQL(
        """
        SELECT t.id, t.users_id, t.system_key, t.name, t.color
        FROM linked_tags lt
        INNER JOIN tags t ON t.id = lt.tag_id
        WHERE lt.users_id = %(user_id)s AND lt.{column} = %(entry_id)s
        ORDER BY (t.system_key IS NULL), lower(t.name), t.id;
        """
    ).format(column=sql.Identifier(_ENTRY_COLUMNS[entry_type]))
    rows = _execute_query_many(connection, query, {"user_id": user_id, "entry_id": entry_id}, commit=False)
    return [tag_read_from_row(row) for row in rows]


def set_entry_tag(
    connection,
    user_id: int,
    entry_type: FoodEntryType,
    entry_id: int,
    tag_id: int,
    linked: bool,
    commit: bool = True,
) -> None:
    """Leaves the tag on the entry as the caller asked, so repeating it is a no-op (§6.3).

    Linking needs an entry the user can see and a tag they can use (system or
    their own), both checked in the INSERT; otherwise NotFoundError (§5.4).
    Unlinking needs nothing: the final state is always "not linked".
    """
    column = sql.Identifier(_ENTRY_COLUMNS[entry_type])
    params = {"user_id": user_id, "visibility_user_id": user_id, "entry_id": entry_id, "tag_id": tag_id}
    if not linked:
        _execute_query(
            connection,
            sql.SQL(
                "DELETE FROM linked_tags WHERE users_id = %(user_id)s AND tag_id = %(tag_id)s "
                "AND {column} = %(entry_id)s RETURNING id;"
            ).format(column=column),
            params,
            commit=commit,
        )
        return
    query = sql.SQL(
        """
        INSERT INTO linked_tags (users_id, tag_id, {column})
        SELECT %(user_id)s, t.id, entity.id
        FROM tags t, {table} entity
        WHERE t.id = %(tag_id)s AND (t.users_id IS NULL OR t.users_id = %(user_id)s)
          AND entity.id = %(entry_id)s AND {visible}
        ON CONFLICT DO NOTHING
        RETURNING id;
        """
    ).format(
        column=column,
        table=sql.Identifier(entry_type.value),
        visible=sql.SQL(_visible_sql(entry_type)),
    )
    try:
        row = _execute_query(connection, query, params, commit=commit)
    except ForeignKeyViolation as exc:
        # The entry or the tag was deleted between the SELECT and the foreign key check.
        raise NotFoundError("Not found.") from exc
    if row is not None:
        return
    # Nothing inserted: already linked, or the entry or the tag is not available.
    exists = _execute_query(
        connection,
        sql.SQL(
            "SELECT 1 AS ok FROM linked_tags WHERE users_id = %(user_id)s AND tag_id = %(tag_id)s "
            "AND {column} = %(entry_id)s;"
        ).format(column=column),
        params,
        commit=False,
    )
    if exists is None:
        raise NotFoundError("Not found.")
