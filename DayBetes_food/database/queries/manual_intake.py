"""Queries for the `manual_intake` table (H1, H3, H4, H5, H7, H11, H16 of
audit/audits/audit_manual_intake.md).

Visibility and ownership always travel inside the SQL: there is no prior
Python check that could diverge from the database rule (§11.4). The partial
unique indexes are the authority on uniqueness (§6.1), and their violation is
translated to `ConflictError` without revealing other users' data (§6.2).
A quick add (is_quick_add) only exists through its portion: no function here
returns, edits, archives or publishes it (code_conventions.md §11.2.3).
"""

from psycopg import sql
from psycopg.errors import UniqueViolation

from DayBetes_food.database.mappers import manual_intake_read_from_row
from DayBetes_food.database.queries.crud import (
    RawSQL,
    _build_fuzzy_search,
    _build_update_query,
    _execute_query,
    _execute_query_many,
    _food_visibility_sql,
)
from DayBetes_food.domain.constants import PortionOrigin
from DayBetes_food.domain.food import normalize_food_text
from DayBetes_food.domain.manual_intake import (
    MANUAL_INTAKE_NAME_MAX_LENGTH,
    ManualIntakeCreate,
    ManualIntakeRead,
    ManualIntakeUpdate,
)
from DayBetes_food.errors import ConflictError, NotFoundError

_MANUAL_INTAKE_COLUMNS = """
    entity.id, entity.created_by, entity.origin_root_id, entity.name, entity.description,
    entity.subtype, entity.origin, entity.default_portion,
    entity.calories_100g, entity.carbs_100g, entity.sugars_100g, entity.fats_100g,
    entity.saturated_100g, entity.proteins_100g, entity.fiber_100g,
    entity.caffeine, entity.alcohol, entity.glycemic_index, entity.ig_confidence,
    entity.macros_confidence, entity.default_macros_quality, entity.default_strictly_weighed,
    entity.is_quick_add, entity.is_published, entity.created_at, entity.updated_at, entity.deleted_at,
    EXISTS (SELECT 1 FROM user_favorites uf
            WHERE uf.user_id = %(visibility_user_id)s AND uf.manual_intake_id = entity.id) AS is_favorite,
    (entity.created_by = %(visibility_user_id)s AND entity.deleted_at IS NULL) AS can_edit,
    (entity.deleted_at IS NULL AND (entity.is_published OR entity.created_by = %(visibility_user_id)s)) AS is_listable
"""
_MANUAL_INTAKE_FROM = "FROM manual_intake entity"

_MANUAL_INTAKE_CREATE_COLUMNS = (
    "created_by",
    "origin_root_id",
    "name",
    "description",
    "subtype",
    "origin",
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
    "glycemic_index",
    "ig_confidence",
    "macros_confidence",
    "default_macros_quality",
    "default_strictly_weighed",
    "is_quick_add",
)

# §6.2: never reveals another user's personal data.
_MANUAL_INTAKE_UNIQUE_MESSAGES = {
    "uq_manual_intake_personal_name_origin": "You already have a dish with that name and origin.",
    "uq_manual_intake_published_name_origin": "A published dish with that name and origin already exists.",
}

# A quick add is never editable, archivable or publishable (§11.2.3).
_OWNER_WRITABLE = (
    "manual_intake.created_by = %(user_id)s "
    "AND manual_intake.deleted_at IS NULL "
    "AND NOT manual_intake.is_quick_add"
)


def _conflict_from(exc: UniqueViolation) -> ConflictError:
    name = getattr(exc.diag, "constraint_name", None)
    return ConflictError(_MANUAL_INTAKE_UNIQUE_MESSAGES.get(name, "That dish already exists."))


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


def _editable_fields(payload: ManualIntakeCreate | ManualIntakeUpdate) -> dict:
    return {
        "name": payload.name,
        "description": payload.description,
        "subtype": payload.subtype,
        "origin": payload.origin,
        "default_portion": payload.default_portion,
        "glycemic_index": payload.glycemic_index.value if payload.glycemic_index else None,
        "ig_confidence": payload.ig_confidence,
        "macros_confidence": payload.macros_confidence,
        "default_macros_quality": payload.default_macros_quality,
        "default_strictly_weighed": payload.default_strictly_weighed,
        **_nutrient_params(payload.nutrients),
    }


def create_manual_intake(connection, payload: ManualIntakeCreate, commit: bool = True) -> int:
    """Insert a new dish, personal by default (no is_published, §11.4.1).

    Repeating the same insert of a reusable dish -> UniqueViolation -> 409
    (§9.6). A quick add never collides: it is outside the unique indexes.
    """
    params = {
        "created_by": payload.created_by,
        "origin_root_id": payload.origin_root_id,
        "is_quick_add": payload.is_quick_add,
        **_editable_fields(payload),
    }
    query = (
        "INSERT INTO manual_intake ("
        + ", ".join(_MANUAL_INTAKE_CREATE_COLUMNS)
        + ") VALUES ("
        + ", ".join(f"%({column})s" for column in _MANUAL_INTAKE_CREATE_COLUMNS)
        + ") RETURNING id;"
    )
    try:
        result = _execute_query(connection, query, params, commit=commit)
    except UniqueViolation as exc:
        raise _conflict_from(exc) from exc
    return result["id"]


def get_manual_intake(connection, user_id: int, manual_intake_id: int) -> ManualIntakeRead | None:
    """Get one visible dish, or None: it does not exist, is not visible or is a
    quick add (§3.3, §5.4). Includes what the viewer retains (archived or
    unpublished but kept in favorites or in one of their recipes)."""
    params = {"manual_intake_id": manual_intake_id, "visibility_user_id": user_id}
    query = f"""
        SELECT {_MANUAL_INTAKE_COLUMNS}
        {_MANUAL_INTAKE_FROM}
        WHERE entity.id = %(manual_intake_id)s
          AND {_food_visibility_sql(PortionOrigin.MANUAL_INTAKE, "entity", include_retained=True)};
    """
    row = _execute_query(connection, query, params, commit=False)
    return manual_intake_read_from_row(row) if row else None


def list_manual_intakes(
    connection,
    user_id: int,
    *,
    search: str | None = None,
    owned_only: bool = False,
    favorites_only: bool = False,
    include_retained: bool = False,
) -> list[ManualIntakeRead]:
    """List the dishes the viewer may see, never quick adds.

    The search matches the name or the origin (decision 2026-10-09).
    `include_retained=True` explicitly includes archived or unpublished dishes
    the viewer keeps in favorites or in one of their recipes (§11.3).
    """
    conditions = [
        _food_visibility_sql(PortionOrigin.MANUAL_INTAKE, "entity", include_retained=include_retained)
    ]
    params = {"visibility_user_id": user_id}
    normalized = (search or "").strip()
    if normalized:
        name_condition, name_params, _ = _build_fuzzy_search(
            connection, "entity.name", normalized, param_prefix="manual_name"
        )
        origin_condition, origin_params, _ = _build_fuzzy_search(
            connection, "COALESCE(entity.origin, '')", normalized, param_prefix="manual_origin"
        )
        conditions.append(f"({name_condition} OR {origin_condition})")
        params.update(name_params)
        params.update(origin_params)
    if favorites_only:
        conditions.append(
            "EXISTS (SELECT 1 FROM user_favorites uf "
            "WHERE uf.user_id = %(visibility_user_id)s AND uf.manual_intake_id = entity.id)"
        )
    if owned_only:
        conditions.append("entity.created_by = %(visibility_user_id)s")
    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT {_MANUAL_INTAKE_COLUMNS}
        {_MANUAL_INTAKE_FROM}
        WHERE {where_clause}
        ORDER BY entity.name, entity.id;
    """
    rows = _execute_query_many(connection, query, params, commit=False)
    return [manual_intake_read_from_row(row) for row in rows]


def update_manual_intake(
    connection, user_id: int, manual_intake_id: int, payload: ManualIntakeUpdate, commit: bool = True
) -> bool:
    """Full replacement of the editable fields of a reusable dish (H1): every
    field that is None is written as NULL.

    Last write wins: the edit replaces every editable field; two tabs editing
    the same dish keep the last save (§6.7 single user, §6.10 documented
    exception for reference data, code_conventions.md §11.2.3). No version
    column. Repeating it -> same final state.
    No row -> NotFoundError (does not exist, is not yours, is archived or is a
    quick add: the same external result, §3.4 and §5.4).
    """
    set_fields = _editable_fields(payload)
    null_fields = {field for field, value in set_fields.items() if value is None}
    query = _build_update_query(
        "manual_intake",
        {**set_fields, "id": manual_intake_id},
        raw_fields={"updated_at": RawSQL.NOW},
        null_fields=null_fields,
        extra_where=sql.SQL(_OWNER_WRITABLE),
    )
    try:
        result = _execute_query(
            connection,
            query,
            {**set_fields, "id": manual_intake_id, "user_id": user_id},
            commit=commit,
        )
    except UniqueViolation as exc:
        raise _conflict_from(exc) from exc
    if result is None:
        raise NotFoundError("Dish not found or no longer editable.")
    return True


def _owned_reusable_exists(connection, user_id: int, manual_intake_id: int, *, active_only: bool) -> bool:
    active = " AND entity.deleted_at IS NULL" if active_only else ""
    row = _execute_query(
        connection,
        "SELECT 1 FROM manual_intake entity "
        "WHERE entity.id = %(manual_intake_id)s AND entity.created_by = %(user_id)s "
        "AND NOT entity.is_quick_add" + active + ";",
        {"manual_intake_id": manual_intake_id, "user_id": user_id},
        commit=False,
    )
    return row is not None


def archive_manual_intake(connection, user_id: int, manual_intake_id: int, commit: bool = True) -> bool:
    """Archive (irreversible, no restore_, §11.2.3).

    Returns True when it archived now, False when it was already archived
    (no-op, §9.6), NotFoundError otherwise (not yours, does not exist or is a
    quick add). Removing it from the owner's favorites is the caller's job, in
    the same transaction.
    """
    query = f"""
        UPDATE manual_intake
        SET deleted_at = NOW(), updated_at = NOW()
        WHERE manual_intake.id = %(manual_intake_id)s
          AND {_OWNER_WRITABLE}
        RETURNING manual_intake.id;
    """
    result = _execute_query(
        connection, query, {"manual_intake_id": manual_intake_id, "user_id": user_id}, commit=commit
    )
    if result is not None:
        return True
    if _owned_reusable_exists(connection, user_id, manual_intake_id, active_only=False):
        return False
    raise NotFoundError("Dish not found.")


def _set_manual_intake_published(
    connection, user_id: int, manual_intake_id: int, published: bool, commit: bool
) -> bool:
    query = f"""
        UPDATE manual_intake
        SET is_published = %(published)s, updated_at = NOW()
        WHERE manual_intake.id = %(manual_intake_id)s
          AND {_OWNER_WRITABLE}
          AND manual_intake.is_published = %(current)s
        RETURNING manual_intake.id;
    """
    params = {
        "published": published,
        "current": not published,
        "manual_intake_id": manual_intake_id,
        "user_id": user_id,
    }
    try:
        result = _execute_query(connection, query, params, commit=commit)
    except UniqueViolation as exc:
        raise _conflict_from(exc) from exc
    if result is not None:
        return True
    if _owned_reusable_exists(connection, user_id, manual_intake_id, active_only=True):
        return False
    raise NotFoundError("Dish not found.")


def publish_manual_intake(connection, user_id: int, manual_intake_id: int, commit: bool = True) -> bool:
    """Publish an owned, active, still-personal reusable dish.

    Repeating it -> False (already published, idempotent).
    Publishing a duplicate of a published dish -> ConflictError (409).
    """
    return _set_manual_intake_published(connection, user_id, manual_intake_id, True, commit)


def unpublish_manual_intake(connection, user_id: int, manual_intake_id: int, commit: bool = True) -> bool:
    """Unpublish an owned, active, still-published dish.

    Repeating it -> False (already personal, idempotent).
    Unpublishing a duplicate of one of the owner's personal dishes -> ConflictError.
    """
    return _set_manual_intake_published(connection, user_id, manual_intake_id, False, commit)


def _fit_copy_name(base: str, suffix: str) -> str:
    max_base = MANUAL_INTAKE_NAME_MAX_LENGTH - len(suffix)
    return base[:max_base].rstrip() + suffix


def _manual_intake_name_taken(connection, user_id: int, name: str, origin: str | None) -> bool:
    """Same key as uq_manual_intake_personal_name_origin."""
    row = _execute_query(
        connection,
        """
        SELECT 1 FROM manual_intake entity
        WHERE entity.created_by = %(user_id)s
          AND entity.deleted_at IS NULL
          AND NOT entity.is_quick_add
          AND lower(entity.name) = lower(%(name)s)
          AND lower(COALESCE(entity.origin, '')) = lower(COALESCE(%(origin)s, ''))
        LIMIT 1;
        """,
        {"user_id": user_id, "name": name, "origin": origin},
        commit=False,
    )
    return row is not None


def next_manual_intake_copy_name(connection, user_id: int, base_name: str, origin: str | None) -> str:
    """Suggest a free "<base> (copy)" name for the owner (H16, §1.1).

    Only a better error message: if two simultaneous copies compute the same
    name, the partial unique index returns 409. The base is normalized with the
    single normalization of food names (domain/food.py).
    """
    base = normalize_food_text(base_name) or "Dish"
    candidate = _fit_copy_name(base, " (copy)")
    if not _manual_intake_name_taken(connection, user_id, candidate, origin):
        return candidate
    index = 2
    while True:
        candidate = _fit_copy_name(base, f" (copy {index})")
        if not _manual_intake_name_taken(connection, user_id, candidate, origin):
            return candidate
        index += 1


def get_manual_origin_suggestions(
    connection, user_id: int, *, search: str = "", limit: int = 50
) -> list[str]:
    """Distinct origins for the autocomplete (H7, decision 2026-10-09): only
    active dishes of the viewer and published ones; never another user's
    personal dishes nor quick adds, because an origin is often a personal place
    or person ("grandma Geno")."""
    search_condition, search_params, search_order = _build_fuzzy_search(
        connection, "source.name", search
    )
    params = {
        **search_params,
        "visibility_user_id": user_id,
        "limit": max(1, min(int(limit or 50), 500)),
    }
    query = f"""
        WITH source AS (
            SELECT DISTINCT entity.origin AS name
            FROM manual_intake entity
            WHERE {_food_visibility_sql(PortionOrigin.MANUAL_INTAKE, "entity", include_retained=False)}
              AND entity.origin IS NOT NULL
        )
        SELECT source.name
        FROM source
        WHERE {search_condition or "TRUE"}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]
