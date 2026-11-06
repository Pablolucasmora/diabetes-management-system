"""Queries for the `recipe` table (code_conventions.md §11.2.4).

Visibility and ownership always travel inside the SQL: there is no prior Python
check that could diverge from the database rule (§5.3, §11.4). The partial unique
indexes are the authority on uniqueness (§6.1), and their violation is translated
to `ConflictError` (§6.2).
"""

from psycopg import sql
from psycopg.errors import UniqueViolation

from DayBetes_food.database.mappers import recipe_read_from_row
from DayBetes_food.database.queries.crud import (
    RawSQL,
    _build_fuzzy_search,
    _build_update_query,
    _execute_query,
    _execute_query_many,
)
from DayBetes_food.domain.constants import MealType
from DayBetes_food.domain.food import normalize_food_text
from DayBetes_food.domain.recipe import (
    RECIPE_NAME_MAX_LENGTH,
    RecipeCreate,
    RecipeRead,
    RecipeUpdate,
)
from DayBetes_food.domain.search_text import normalize_search_text
from DayBetes_food.errors import ConflictError, NotFoundError

_RECIPE_COLUMNS = """
    entity.id, entity.users_id, entity.origin_root_id, entity.name, entity.meal_type,
    entity.notes, entity.servings, entity.is_published, entity.created_at, entity.updated_at,
    EXISTS (SELECT 1 FROM user_favorites uf
            WHERE uf.user_id = %(visibility_user_id)s AND uf.recipe_id = entity.id) AS is_favorite,
    (entity.users_id = %(visibility_user_id)s) AS can_edit
"""
_RECIPE_VISIBLE = "(entity.is_published OR entity.users_id = %(visibility_user_id)s)"
_OWNER_WRITABLE = "recipe.users_id = %(user_id)s"

_RECIPE_UNIQUE_MESSAGES = {
    "uq_recipe_personal_name": "You already have a recipe with that name.",
    "uq_recipe_published_name": "A published recipe already has that name.",
}


def _conflict_from(exc: UniqueViolation) -> ConflictError:
    name = getattr(exc.diag, "constraint_name", None)
    return ConflictError(_RECIPE_UNIQUE_MESSAGES.get(name, "That recipe already exists."))


def create_recipe(connection, payload: RecipeCreate, commit: bool = True) -> int:
    """Create a personal recipe (no is_published, §11.4.1).

    A personal name the owner already uses -> ConflictError (§6.2).
    """
    query = """
        INSERT INTO recipe (users_id, origin_root_id, meal_type, name, notes, servings)
        VALUES (%(user_id)s, %(origin_root_id)s, %(meal_type)s, %(name)s, %(notes)s, %(servings)s)
        RETURNING id;
    """
    try:
        row = _execute_query(
            connection,
            query,
            {
                "user_id": payload.user_id,
                "origin_root_id": payload.origin_root_id,
                "meal_type": payload.meal_type.value if payload.meal_type else None,
                "name": payload.name,
                "notes": payload.notes,
                "servings": payload.servings,
            },
            commit=commit,
        )
    except UniqueViolation as exc:
        raise _conflict_from(exc) from exc
    return int(row["id"])


def get_recipe(connection, user_id: int, recipe_id: int) -> RecipeRead | None:
    """A recipe the viewer may see, or None: does not exist or is someone else's
    personal one, the same external result (§5.4)."""
    query = f"""
        SELECT {_RECIPE_COLUMNS}
        FROM recipe entity
        WHERE entity.id = %(id)s AND {_RECIPE_VISIBLE};
    """
    row = _execute_query(connection, query, {"id": recipe_id, "visibility_user_id": user_id}, commit=False)
    return recipe_read_from_row(row) if row else None


def list_recipes(
    connection,
    user_id: int,
    *,
    search: str | None = None,
    meal_types: tuple[MealType, ...] = (),
    owned_only: bool = False,
    others_only: bool = False,
    favorites_only: bool = False,
) -> list[RecipeRead]:
    """List the recipes the viewer may see.

    The search matches the recipe's name or the name of an ingredient (§11.7). It
    only filters recipes that are already visible, so it reveals nothing new.
    """
    conditions = [_RECIPE_VISIBLE]
    params = {"visibility_user_id": user_id}
    normalized = (search or "").strip()
    if normalized:
        plain = normalize_search_text(normalized)
        name_condition, name_params, _ = _build_fuzzy_search(
            connection, "entity.search_name", plain, param_prefix="recipe_name"
        )
        catalog_condition, catalog_params, _ = _build_fuzzy_search(
            connection, "ingredient_catalog.search_name", plain, param_prefix="recipe_catalog"
        )
        manual_condition, manual_params, _ = _build_fuzzy_search(
            connection, "ingredient_manual.name", normalized, param_prefix="recipe_manual"
        )
        # `= ANY(ARRAY(...))` and not `IN (...)`: only the array form lets the OR
        # combine with the name indexes (§11.7).
        conditions.append(
            f"({name_condition}"
            " OR entity.id = ANY(ARRAY("
            "SELECT pd.recipe_id FROM portion_detail pd "
            "JOIN catalog ingredient_catalog ON ingredient_catalog.id = pd.catalog_id "
            f"WHERE pd.recipe_id IS NOT NULL AND {catalog_condition}))"
            " OR entity.id = ANY(ARRAY("
            "SELECT pd.recipe_id FROM portion_detail pd "
            "JOIN manual_intake ingredient_manual ON ingredient_manual.id = pd.manual_intake_id "
            f"WHERE pd.recipe_id IS NOT NULL AND {manual_condition})))"
        )
        params.update(name_params)
        params.update(catalog_params)
        params.update(manual_params)
    if meal_types:
        conditions.append("entity.meal_type = ANY(%(meal_types)s)")
        params["meal_types"] = [meal_type.value for meal_type in meal_types]
    if owned_only:
        conditions.append("entity.users_id = %(visibility_user_id)s")
    if others_only:
        conditions.append("entity.users_id <> %(visibility_user_id)s")
    if favorites_only:
        conditions.append(
            "EXISTS (SELECT 1 FROM user_favorites uf "
            "WHERE uf.user_id = %(visibility_user_id)s AND uf.recipe_id = entity.id)"
        )
    query = f"""
        SELECT {_RECIPE_COLUMNS}
        FROM recipe entity
        WHERE {" AND ".join(conditions)}
        ORDER BY entity.name, entity.id;
    """
    rows = _execute_query_many(connection, query, params, commit=False)
    return [recipe_read_from_row(row) for row in rows]


def update_recipe(connection, user_id: int, recipe_id: int, payload: RecipeUpdate, commit: bool = True) -> None:
    """Full replacement of the editable fields: every None is written as NULL (§3.4).

    Last write wins: two tabs editing the same recipe keep the last save (§6.7
    single user, §6.10 documented exception for reference data). Repeating it ->
    same final state. No row -> NotFoundError (does not exist or is not yours, the
    same external result, §5.4).
    """
    fields = {
        "name": payload.name,
        "meal_type": payload.meal_type.value if payload.meal_type else None,
        "notes": payload.notes,
        "servings": payload.servings,
    }
    query = _build_update_query(
        "recipe",
        {**fields, "id": recipe_id},
        raw_fields={"updated_at": RawSQL.NOW},
        null_fields={field for field, value in fields.items() if value is None},
        extra_where=sql.SQL(_OWNER_WRITABLE),
    )
    try:
        row = _execute_query(connection, query, {**fields, "id": recipe_id, "user_id": user_id}, commit=commit)
    except UniqueViolation as exc:
        raise _conflict_from(exc) from exc
    if row is None:
        raise NotFoundError("Recipe not found.")


def delete_recipe(connection, user_id: int, recipe_id: int, commit: bool = True) -> None:
    """Physical delete by its owner: nothing eaten references a recipe (§11.2.4).

    Repeating it -> NotFoundError.
    """
    row = _execute_query(
        connection,
        "DELETE FROM recipe WHERE id = %(id)s AND users_id = %(user_id)s RETURNING id;",
        {"id": recipe_id, "user_id": user_id},
        commit=commit,
    )
    if row is None:
        raise NotFoundError("Recipe not found.")


def _recipe_name_taken(connection, user_id: int, name: str) -> bool:
    row = _execute_query(
        connection,
        "SELECT 1 AS found FROM recipe entity "
        "WHERE entity.users_id = %(user_id)s AND NOT entity.is_published AND lower(entity.name) = lower(%(name)s);",
        {"user_id": user_id, "name": name},
        commit=False,
    )
    return row is not None


def next_recipe_copy_name(connection, user_id: int, base_name: str) -> str:
    """Suggest a free "<base> (copy)" name for the owner (§1.1).

    Only a better error message: if two simultaneous copies compute the same name,
    the partial unique index returns 409. The name is cut to fit, never rejected.
    """
    base = normalize_food_text(base_name) or "Recipe"

    def fit(suffix: str) -> str:
        return normalize_food_text(base[: RECIPE_NAME_MAX_LENGTH - len(suffix)]) + suffix

    candidate = fit(" (copy)")
    index = 2
    while _recipe_name_taken(connection, user_id, candidate):
        candidate = fit(f" (copy {index})")
        index += 1
    return candidate
