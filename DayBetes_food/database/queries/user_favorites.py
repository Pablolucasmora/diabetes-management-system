"""Queries for the `user_favorites` bridge table (code_conventions.md §11.2.5).

A row also grants visibility over a retained food (§11.2.2), so adding one is an
authorization decision and its condition lives in the SQL (§5.3).
"""

from psycopg import sql
from psycopg.errors import ForeignKeyViolation

from DayBetes_food.database.mappers import user_favorite_access_from_row
from DayBetes_food.database.queries.crud import (
    _RECIPE_VISIBLE,
    _execute_query,
    _food_in_own_recipe_sql,
    _food_visibility_sql,
)
from DayBetes_food.domain.constants import CreationResult, FoodEntryType, PortionOrigin
from DayBetes_food.domain.user_favorite import UserFavoriteAccess
from DayBetes_food.errors import ConflictError, NotFoundError

_FAVORITE_COLUMNS = {  # technical whitelist (§4.6); each table is named after its entry type
    FoodEntryType.CATALOG: "catalog_id",
    FoodEntryType.MANUAL_INTAKE: "manual_intake_id",
    FoodEntryType.RECIPE: "recipe_id",
}


def _visible_sql(entry_type: FoodEntryType, *, include_retained: bool) -> str:
    """A recipe has no retention: its rule is the same with or without it."""
    if entry_type is FoodEntryType.RECIPE:
        return _RECIPE_VISIBLE
    origin = PortionOrigin(entry_type.value)
    return _food_visibility_sql(origin, "entity", include_retained=include_retained)


def _only_access_sql(entry_type: FoodEntryType) -> str:
    """Among the rows that are visible, those that only the favorite keeps visible."""
    if entry_type is FoodEntryType.RECIPE:
        return "FALSE"
    listable = _visible_sql(entry_type, include_retained=False)
    in_own_recipe = _food_in_own_recipe_sql(PortionOrigin(entry_type.value), "entity")
    return f"NOT COALESCE({listable}, FALSE) AND NOT {in_own_recipe}"


def get_user_favorite_access(
    connection, user_id: int, entry_type: FoodEntryType, entry_id: int
) -> UserFavoriteAccess | None:
    """The viewer's favorite state on a food they can see, or None when they
    cannot see it: it does not exist or is not available to them (§5.4)."""
    query = sql.SQL(
        """
        SELECT
            EXISTS (SELECT 1 FROM user_favorites uf
                    WHERE uf.user_id = %(visibility_user_id)s AND uf.{column} = entity.id) AS is_favorite,
            {only_access} AS is_only_access
        FROM {table} entity
        WHERE entity.id = %(entry_id)s AND {visible};
        """
    ).format(
        column=sql.Identifier(_FAVORITE_COLUMNS[entry_type]),
        only_access=sql.SQL(_only_access_sql(entry_type)),
        table=sql.Identifier(entry_type.value),
        visible=sql.SQL(_visible_sql(entry_type, include_retained=True)),
    )
    row = _execute_query(
        connection, query, {"visibility_user_id": user_id, "entry_id": entry_id}, commit=False
    )
    return user_favorite_access_from_row(row) if row else None


def _add_user_favorite(
    connection, user_id: int, entry_type: FoodEntryType, entry_id: int, commit: bool
) -> CreationResult:
    # Only what the viewer can list can be added: a retained food can be removed
    # but not added (§11.2.2).
    query = sql.SQL(
        """
        INSERT INTO user_favorites (user_id, {column})
        SELECT %(visibility_user_id)s, entity.id
        FROM {table} entity
        WHERE entity.id = %(entry_id)s AND {listable}
        ON CONFLICT DO NOTHING
        RETURNING id;
        """
    ).format(
        column=sql.Identifier(_FAVORITE_COLUMNS[entry_type]),
        table=sql.Identifier(entry_type.value),
        listable=sql.SQL(_visible_sql(entry_type, include_retained=False)),
    )
    try:
        row = _execute_query(
            connection, query, {"visibility_user_id": user_id, "entry_id": entry_id}, commit=commit
        )
    except ForeignKeyViolation as exc:
        # Deleted between the SELECT and the foreign key check of this statement.
        raise NotFoundError("Food not found.") from exc
    if row is not None:
        return CreationResult.CREATED
    access = get_user_favorite_access(connection, user_id, entry_type, entry_id)
    if access is None:
        raise NotFoundError("Food not found.")
    if access.is_favorite:
        return CreationResult.ALREADY_EXISTED
    raise ConflictError("This food cannot be added to favorites.")


def set_user_favorite(
    connection,
    user_id: int,
    entry_type: FoodEntryType,
    entry_id: int,
    favorite: bool,
    commit: bool = True,
) -> CreationResult | None:
    """Leaves the food as the caller asked, so repeating it is a no-op (§6.3, §9.6).

    Adding returns whether it created the row or found it. It raises
    NotFoundError when the viewer cannot see the food, and ConflictError when
    they see it but cannot add it (retained). Removing returns None: the final
    state is always "not a favorite", it needs no visibility, and a row that is
    not there is not an error.
    """
    if favorite:
        return _add_user_favorite(connection, user_id, entry_type, entry_id, commit)
    query = sql.SQL(
        """
        DELETE FROM user_favorites uf
        WHERE uf.user_id = %(user_id)s AND uf.{column} = %(entry_id)s
        RETURNING uf.id;
        """
    ).format(column=sql.Identifier(_FAVORITE_COLUMNS[entry_type]))
    _execute_query(connection, query, {"user_id": user_id, "entry_id": entry_id}, commit=commit)
    return None
