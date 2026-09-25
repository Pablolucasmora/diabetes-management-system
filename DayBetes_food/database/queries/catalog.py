"""Queries for the `catalog` table (H2, H4, H5, H7, H10, H11, H20, H21, H24, H25, H26).

Visibility and ownership always travel inside the SQL: there is no prior
Python check that could diverge from the database rule (§11.4). The partial
unique index is the authority on uniqueness (§6.1), and its violation is
translated to `ConflictError` without revealing other users' data (§6.2).
"""

from psycopg import sql
from psycopg.errors import UniqueViolation

from DayBetes_food.database.mappers import catalog_item_read_from_row
from DayBetes_food.database.queries.crud import (
    RawSQL,
    _build_fuzzy_search,
    _build_update_query,
    _catalog_visibility_sql,
    _execute_query,
    _execute_query_many,
)
from DayBetes_food.domain.catalog import (
    CATALOG_NAME_MAX_LENGTH,
    CatalogItemCreate,
    CatalogItemUpdate,
    normalize_catalog_name,
)
from DayBetes_food.errors import ConflictError, NotFoundError

_CATALOG_COLUMNS = """
    entity.id, entity.created_by, entity.origin_root_id, entity.name, entity.brand_id,
    fb.label AS brand, entity.category, entity.subtype, entity.initial_state,
    entity.nutriscore, entity.nova, entity.yuka, entity.default_portion,
    entity.calories_100g, entity.carbs_100g, entity.sugars_100g, entity.fats_100g,
    entity.saturated_100g, entity.proteins_100g, entity.fiber_100g,
    entity.caffeine, entity.alcohol, entity.barcode, entity.cooking_factor,
    entity.is_published, entity.created_at, entity.updated_at, entity.deleted_at,
    EXISTS (SELECT 1 FROM user_favorites uf
            WHERE uf.user_id = %(visibility_user_id)s AND uf.catalog_id = entity.id) AS is_favorite,
    COALESCE(entity.created_by = %(visibility_user_id)s AND entity.deleted_at IS NULL, FALSE) AS can_edit,
    COALESCE(entity.deleted_at IS NULL AND (entity.is_published OR entity.created_by = %(visibility_user_id)s), FALSE) AS is_listable
"""
_CATALOG_FROM = "FROM catalog entity LEFT JOIN food_brands fb ON fb.id = entity.brand_id"

_CATALOG_CREATE_COLUMNS = (
    "created_by",
    "origin_root_id",
    "name",
    "brand_id",
    "category",
    "subtype",
    "initial_state",
    "nutriscore",
    "nova",
    "yuka",
    "default_portion",
    "calories_100g",
    "carbs_100g",
    "sugars_100g",
    "fats_100g",
    "saturated_100g",
    "proteins_100g",
    "fiber_100g",
    "caffeine",
    "alcohol",
    "barcode",
    "cooking_factor",
)

# §6.2: never reveals another user's personal data.
_CATALOG_UNIQUE_MESSAGES = {
    "uq_catalog_personal_name_brand": "You already have a food with that name and brand.",
    "uq_catalog_published_name_brand": "A published food with that name and brand already exists.",
    "uq_catalog_personal_barcode": "You already have a food with that barcode.",
    "uq_catalog_published_barcode": "A published food with that barcode already exists.",
}


def _conflict_from(exc: UniqueViolation) -> ConflictError:
    name = getattr(exc.diag, "constraint_name", None)
    return ConflictError(_CATALOG_UNIQUE_MESSAGES.get(name, "That food already exists."))


def _nutrient_params(nutrients) -> dict:
    return {
        "calories_100g": nutrients.calories_100g,
        "carbs_100g": nutrients.carbs_100g,
        "sugars_100g": nutrients.sugars_100g,
        "fats_100g": nutrients.fats_100g,
        "saturated_100g": nutrients.saturated_100g,
        "proteins_100g": nutrients.proteins_100g,
        "fiber_100g": nutrients.fiber_100g,
        "caffeine": nutrients.caffeine,
        "alcohol": nutrients.alcohol,
    }


def _create_params(payload: CatalogItemCreate) -> dict:
    return {
        "created_by": payload.created_by,
        "origin_root_id": payload.origin_root_id,
        "name": payload.name,
        "brand_id": payload.brand_id,
        "category": payload.category.value,
        "subtype": payload.subtype,
        "initial_state": payload.initial_state.value if payload.initial_state else None,
        "nutriscore": payload.nutriscore.value if payload.nutriscore else None,
        "nova": payload.nova,
        "yuka": payload.yuka,
        "default_portion": payload.default_portion,
        "barcode": payload.barcode,
        "cooking_factor": payload.cooking_factor,
        **_nutrient_params(payload.nutrients),
    }


def _update_fields(payload: CatalogItemUpdate) -> tuple[dict, set]:
    fields = {
        "name": payload.name,
        "brand_id": payload.brand_id,
        "category": payload.category.value,
        "subtype": payload.subtype,
        "initial_state": payload.initial_state.value if payload.initial_state else None,
        "nutriscore": payload.nutriscore.value if payload.nutriscore else None,
        "nova": payload.nova,
        "yuka": payload.yuka,
        "default_portion": payload.default_portion,
        "barcode": payload.barcode,
        "cooking_factor": payload.cooking_factor,
        **_nutrient_params(payload.nutrients),
    }
    null_fields = {field for field, value in fields.items() if value is None}
    return fields, null_fields


def create_catalog_item(connection, payload: CatalogItemCreate, commit: bool = True) -> int:
    """Insert a new catalog item, personal by default (no is_published, R5).

    Repeating the same insert -> UniqueViolation -> 409 (§9.6).
    """
    query = (
        "INSERT INTO catalog ("
        + ", ".join(_CATALOG_CREATE_COLUMNS)
        + ") VALUES ("
        + ", ".join(f"%({column})s" for column in _CATALOG_CREATE_COLUMNS)
        + ") RETURNING id;"
    )
    try:
        result = _execute_query(connection, query, _create_params(payload), commit=commit)
    except UniqueViolation as exc:
        raise _conflict_from(exc) from exc
    return result["id"] if result else None


def get_catalog_item(connection, user_id: int, catalog_id: int):
    """Get one visible catalog item, or None (does not exist or is not visible, §5.4)."""
    params = {"catalog_id": catalog_id, "visibility_user_id": user_id}
    query = f"""
        SELECT {_CATALOG_COLUMNS}
        {_CATALOG_FROM}
        WHERE entity.id = %(catalog_id)s
          AND {_catalog_visibility_sql("entity", include_retained=True)};
    """
    row = _execute_query(connection, query, params, commit=False)
    return catalog_item_read_from_row(row) if row else None


def get_catalog_item_by_barcode(connection, user_id: int, barcode: str):
    """Resolve a barcode to the item the viewer may see (feedback 26 order):
    own active first (original before copies, then most recent), then published;
    never another user's personal food."""
    params = {"barcode": barcode, "visibility_user_id": user_id}
    query = f"""
        SELECT {_CATALOG_COLUMNS}
        {_CATALOG_FROM}
        WHERE entity.deleted_at IS NULL
          AND entity.barcode = %(barcode)s
          AND (entity.created_by = %(visibility_user_id)s OR entity.is_published)
        ORDER BY COALESCE(entity.created_by = %(visibility_user_id)s, FALSE) DESC,
                 (entity.origin_root_id IS NULL) DESC,
                 entity.created_at DESC,
                 entity.id DESC
        LIMIT 1;
    """
    row = _execute_query(connection, query, params, commit=False)
    return catalog_item_read_from_row(row) if row else None


def list_catalog_items(
    connection,
    user_id: int,
    *,
    search: str | None = None,
    owned_only: bool = False,
    favorites_only: bool = False,
    include_retained: bool = False,
) -> list:
    """List the catalog items the viewer may see.

    `include_retained=True` explicitly includes archived or unpublished items
    the viewer keeps in favorites or in one of their recipes (§11.3).
    """
    conditions = [_catalog_visibility_sql("entity", include_retained=include_retained)]
    params = {"visibility_user_id": user_id}
    normalized = (search or "").strip()
    if normalized:
        name_condition, name_params, _ = _build_fuzzy_search(
            connection, "entity.name", normalized, param_prefix="catalog_name"
        )
        brand_condition, brand_params, _ = _build_fuzzy_search(
            connection, "COALESCE(fb.label, '')", normalized, param_prefix="catalog_brand"
        )
        conditions.append(f"({name_condition} OR {brand_condition})")
        params.update(name_params)
        params.update(brand_params)
    if favorites_only:
        conditions.append(
            "EXISTS (SELECT 1 FROM user_favorites uf "
            "WHERE uf.user_id = %(visibility_user_id)s AND uf.catalog_id = entity.id)"
        )
    if owned_only:
        conditions.append("entity.created_by = %(visibility_user_id)s")
    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT {_CATALOG_COLUMNS}
        {_CATALOG_FROM}
        WHERE {where_clause}
        ORDER BY entity.name, entity.id;
    """
    rows = _execute_query_many(connection, query, params, commit=False)
    return [catalog_item_read_from_row(row) for row in rows]


def update_catalog_item(
    connection, user_id: int, catalog_id: int, payload: CatalogItemUpdate, commit: bool = True
) -> bool:
    """Full replacement of the editable fields.

    Last write wins: the edit replaces every editable field; two tabs editing the
    same food keep the last save (§6.7 monousuario, §6.10 documented exception for
    reference data; feedback 24). Repeating it -> same final state.
    No row -> NotFoundError (does not exist, is not yours, belongs to the general
    library or is archived: the same external result, §3.4 and §5.4).
    """
    set_fields, null_fields = _update_fields(payload)
    build_params = {**set_fields, "id": catalog_id}
    query = _build_update_query(
        "catalog",
        build_params,
        raw_fields={"updated_at": RawSQL.NOW},
        null_fields=null_fields,
        extra_where=sql.SQL("catalog.created_by = %(user_id)s AND catalog.deleted_at IS NULL"),
    )
    if not query:
        raise NotFoundError("Food not found or no longer editable.")
    try:
        result = _execute_query(
            connection,
            query,
            {**set_fields, "id": catalog_id, "user_id": user_id},
            commit=commit,
        )
    except UniqueViolation as exc:
        raise _conflict_from(exc) from exc
    if result is None:
        raise NotFoundError("Food not found or no longer editable.")
    return True


def archive_catalog_item(connection, user_id: int, catalog_id: int, commit: bool = True) -> bool:
    """Archive (irreversible, decision 2026-09-23).

    Returns True when it archived now, False when it was already archived (no-op,
    §9.6), NotFoundError otherwise (not yours / does not exist / general library).
    """
    query = """
        UPDATE catalog
        SET deleted_at = NOW(), updated_at = NOW()
        WHERE catalog.id = %(catalog_id)s
          AND catalog.created_by = %(user_id)s
          AND catalog.deleted_at IS NULL
        RETURNING catalog.id;
    """
    result = _execute_query(
        connection, query, {"catalog_id": catalog_id, "user_id": user_id}, commit=commit
    )
    if result is not None:
        return True
    exists = _execute_query(
        connection,
        "SELECT 1 FROM catalog entity "
        "WHERE entity.id = %(catalog_id)s AND entity.created_by = %(user_id)s;",
        {"catalog_id": catalog_id, "user_id": user_id},
        commit=False,
    )
    if exists is not None:
        return False
    raise NotFoundError("Food not found.")


def _set_catalog_published(
    connection, user_id: int, catalog_id: int, published: bool, commit: bool
) -> bool:
    query = """
        UPDATE catalog
        SET is_published = %(published)s, updated_at = NOW()
        WHERE catalog.id = %(catalog_id)s
          AND catalog.created_by = %(user_id)s
          AND catalog.deleted_at IS NULL
          AND catalog.is_published = %(current)s
        RETURNING catalog.id;
    """
    params = {
        "published": published,
        "current": not published,
        "catalog_id": catalog_id,
        "user_id": user_id,
    }
    try:
        result = _execute_query(connection, query, params, commit=commit)
    except UniqueViolation as exc:
        raise _conflict_from(exc) from exc
    if result is not None:
        return True
    exists = _execute_query(
        connection,
        "SELECT 1 FROM catalog entity "
        "WHERE entity.id = %(catalog_id)s AND entity.created_by = %(user_id)s "
        "AND entity.deleted_at IS NULL;",
        {"catalog_id": catalog_id, "user_id": user_id},
        commit=False,
    )
    if exists is not None:
        return False
    raise NotFoundError("Food not found.")


def publish_catalog_item(connection, user_id: int, catalog_id: int, commit: bool = True) -> bool:
    """Publish an owned, active, still-personal food.

    Repeating it -> False (already published, idempotent, feedback 24).
    Publishing a duplicate of a published food -> ConflictError (409).
    """
    return _set_catalog_published(connection, user_id, catalog_id, True, commit)


def unpublish_catalog_item(connection, user_id: int, catalog_id: int, commit: bool = True) -> bool:
    """Unpublish an owned, active, still-published food.

    Repeating it -> False (already personal, idempotent, feedback 24).
    Unpublishing a duplicate of one of the owner's personal foods -> ConflictError.
    """
    return _set_catalog_published(connection, user_id, catalog_id, False, commit)


def _fit_copy_name(base: str, suffix: str) -> str:
    max_base = CATALOG_NAME_MAX_LENGTH - len(suffix)
    return base[:max_base].rstrip() + suffix


def _catalog_name_taken(connection, user_id: int, name: str, brand_id: int | None) -> bool:
    row = _execute_query(
        connection,
        """
        SELECT 1 FROM catalog entity
        WHERE entity.created_by = %(user_id)s
          AND entity.deleted_at IS NULL
          AND lower(entity.name) = lower(%(name)s)
          AND COALESCE(entity.brand_id, 0) = COALESCE(%(brand_id)s, 0)
        LIMIT 1;
        """,
        {"user_id": user_id, "name": name, "brand_id": brand_id},
        commit=False,
    )
    return row is not None


def next_catalog_copy_name(connection, user_id: int, base_name: str, brand_id: int | None) -> str:
    """Suggest a free "<base> (copy)" name for the owner (H21, §1.1).

    Only a better error message: if two simultaneous copies compute the same
    name, the partial unique index returns 409. The base is normalized with the
    single normalization of `catalog` (H2).
    """
    base = normalize_catalog_name(base_name) or "Food"
    candidate = _fit_copy_name(base, " (copy)")
    if not _catalog_name_taken(connection, user_id, candidate, brand_id):
        return candidate
    index = 2
    while True:
        candidate = _fit_copy_name(base, f" (copy {index})")
        if not _catalog_name_taken(connection, user_id, candidate, brand_id):
            return candidate
        index += 1
