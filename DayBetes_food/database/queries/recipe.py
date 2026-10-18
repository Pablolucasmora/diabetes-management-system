"""Queries for the `recipe` table."""

from typing import Optional

from psycopg.errors import UniqueViolation

from DayBetes_food.database.queries.crud import (
    _add_entity_filters,
    _add_fuzzy_name_condition,
    _build_update_query,
    _execute_query,
    _execute_query_many,
    _favorite_filter_sql,
)
from DayBetes_food.errors import ConflictError

# Public message per unique index (§6.2). Only the personal one exists so far:
# it was brought forward from the recipe audit for saving a cart plate as a
# recipe (frontend_conventions.md §7.13); the published one is still pending.
_RECIPE_UNIQUE_MESSAGES = {
    "uq_recipe_personal_name": "You already have a recipe with that name.",
}


def _conflict_from(exc: UniqueViolation) -> ConflictError:
    name = getattr(exc.diag, "constraint_name", None)
    return ConflictError(_RECIPE_UNIQUE_MESSAGES.get(name, "That recipe already exists."))


def add_recipe(
    connection,
    users_id: int,
    name: str,
    meal_type: str = None,
    notes: str = None,
    origin_root_id: int = None,
    commit: bool = True,
) -> Optional[int]:
    """Creates a new recipe. Personal by default (no is_published, R5).

    A personal name the owner already uses -> UniqueViolation on
    uq_recipe_personal_name -> ConflictError (§6.2).
    """
    query = """
        INSERT INTO recipe (users_id, origin_root_id, meal_type, name, notes)
        VALUES (%(users_id)s, %(origin_root_id)s, %(meal_type)s, %(name)s, %(notes)s)
        RETURNING id;
    """
    try:
        result = _execute_query(connection, query, {
            "users_id": users_id,
            "origin_root_id": origin_root_id,
            "meal_type": meal_type,
            "name": name,
            "notes": notes,
        }, commit=commit)
    except UniqueViolation as exc:
        raise _conflict_from(exc) from exc
    return result["id"] if result else None


def get_recipe(connection, recipe_id: int, viewer_user_id: int = None) -> Optional[dict]:
    """Gets a recipe by ID."""
    query = """
        SELECT entity.*,
               EXISTS (
                   SELECT 1 FROM user_favorites uf
                   WHERE uf.user_id = %(viewer_user_id)s
                     AND uf.recipe_id = entity.id
               ) AS favorite
        FROM recipe entity
        WHERE entity.id = %(id)s;
    """
    return _execute_query(
        connection,
        query,
        {"id": recipe_id, "viewer_user_id": viewer_user_id},
        commit=False,
    )


def get_all_recipes(
    connection,
    users_id: int = None,
    meal_type: str = None,
    favorite: bool = None,
    search: str = None,
    viewer_user_id: int = None,
) -> list:
    """Gets all recipes with optional filters."""
    conditions = []
    params = {}
    
    if meal_type:
        conditions.append("meal_type = %(meal_type)s")
        params["meal_type"] = meal_type
    _add_fuzzy_name_condition(connection, conditions, params, "name", search)
    _add_entity_filters(
        conditions,
        params,
        owner_column="users_id",
        users_id=users_id,
        favorite_condition=(
            _favorite_filter_sql("recipe_id", favorite, params, viewer_user_id)
            if favorite is not None
            else None
        ),
        viewer_user_id=viewer_user_id,
    )
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params["favorite_viewer_id"] = viewer_user_id
    query = f"SELECT entity.*, EXISTS (SELECT 1 FROM user_favorites uf WHERE uf.user_id = %(favorite_viewer_id)s AND uf.recipe_id = entity.id) AS favorite FROM recipe entity {where_clause} ORDER BY entity.name;"
    
    return _execute_query_many(connection, query, params, commit=False)


def update_recipe(
    connection,
    recipe_id: int,
    name: str = None,
    meal_type: str = None,
    notes: str = None,
    favorite: bool = None,
    is_published: bool = None,
    commit: bool = True,
) -> bool:
    """Updates a recipe.

    Renaming or unpublishing onto a personal name the owner already uses ->
    UniqueViolation on uq_recipe_personal_name -> ConflictError (§6.2).
    """
    params = {
        "id": recipe_id, 
        "name": name, 
        "meal_type": meal_type, 
        "notes": notes, 
        "is_published": is_published,
    }
    
    query = _build_update_query("recipe", params)
    
    if not query:
        return False
        
    try:
        result = _execute_query(connection, query, params, commit=commit)
    except UniqueViolation as exc:
        raise _conflict_from(exc) from exc
    return result is not None


def delete_recipe(connection, recipe_id: int, commit: bool = True) -> bool:
    """Deletes a recipe by ID."""
    query = "DELETE FROM recipe WHERE id = %(id)s RETURNING id;"
    result = _execute_query(
        connection, query, {"id": recipe_id}, commit=commit
    )
    return result is not None
