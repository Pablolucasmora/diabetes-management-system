"""
Shared query helpers for the `database/queries/` package.

This module no longer holds per-table CRUD functions (see code_conventions.md
§1.3.1). It only contains:

- generic SQL execution helpers (`_execute_query`, `_execute_query_many`);
- the safe dynamic UPDATE builder (`_build_update_query` and its
  validation/whitelist helpers);
- fuzzy-search helpers shared by several table modules
  (`_build_fuzzy_search`, `_add_fuzzy_name_condition`);
- ownership/favorite filter helpers shared by `catalog.py`, `manual_intake.py`
  and `recipe.py` (`_add_entity_filters`, `_favorite_filter_sql`);
- tag normalization helpers shared by `tags.py` and `linked_tags.py`
  (`_normalize_tag_name`, `_tag_color_from_name`);
- constants shared across table modules (`TRGM_SIMILARITY_THRESHOLD`,
  `APP_TIMEZONE_SQL`).

Table-specific queries live in one module per table
(`users.py`, `catalog.py`, `manual_intake.py`, `recipe.py`, `tags.py`,
`linked_tags.py`, `user_favorites.py`, `food_brands.py`, `intake_event.py`,
`portion_detail.py`) plus `entries.py` for reads that span more than one
table with no single owning table. All of them are re-exported from
`database/queries/__init__.py`.
"""

import logging
import re
from enum import Enum
from typing import Optional, Any

from psycopg import sql

logger = logging.getLogger(__name__)

TRGM_SIMILARITY_THRESHOLD = 0.25
APP_TIMEZONE_SQL = "Europe/Madrid"
_HAS_PG_TRGM = None
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_UPDATE_TABLES = {
    "catalog",
    "manual_intake",
    "recipe",
    "intake_event",
    "portion_detail",
}


class RawSQL(Enum):
    NOW = "NOW()"


_RAW_SQL_EXPRESSIONS = {
    RawSQL.NOW: sql.SQL("NOW()"),
}


class UnsupportedUpdateTarget(Exception):
    """Raised when a dynamic UPDATE target is not controlled by the backend."""


# ============================================
# GENERIC HELPERS
# ============================================

def _execute_query(
    connection,
    query: str,
    params: dict = None,
    commit: bool = True,
    rollback_on_error: bool = True,
) -> Optional[Any]:
    """Generic helper to execute queries."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params or {})
            if commit:
                connection.commit()
            return cursor.fetchone()
    except Exception as e:
        if rollback_on_error:
            connection.rollback()
            logger.error("Error in query: %s", e, exc_info=True)
            return None
        raise


def _execute_query_many(
    connection,
    query: str,
    params: dict = None,
    commit: bool = True,
    rollback_on_error: bool = True,
) -> list:
    """Generic helper to execute queries that return multiple rows."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params or {})
            if commit:
                connection.commit()
            return cursor.fetchall()
    except Exception as e:
        if rollback_on_error:
            connection.rollback()
            logger.error("Error in query: %s", e, exc_info=True)
            return []
        raise


def _validate_update_request(
    table: str,
    params: dict,
    where_field: str,
    auto_fields: dict,
    raw_fields: dict,
    null_fields: set[str],
) -> None:
    if table not in _ALLOWED_UPDATE_TABLES:
        raise UnsupportedUpdateTarget(f"Unsupported update table: {table!r}")

    identifiers = [where_field]
    identifiers.extend((params or {}).keys())
    identifiers.extend((auto_fields or {}).keys())
    identifiers.extend((raw_fields or {}).keys())
    identifiers.extend(null_fields or set())
    for field in identifiers:
        if not isinstance(field, str) or not _IDENTIFIER_RE.fullmatch(field):
            raise UnsupportedUpdateTarget(f"Invalid update identifier: {field!r}")

    if where_field not in (params or {}):
        raise UnsupportedUpdateTarget(f"Missing UPDATE key: {where_field!r}")

    groups = {
        "params": set((params or {}).keys()),
        "auto_fields": set((auto_fields or {}).keys()),
        "raw_fields": set((raw_fields or {}).keys()),
    }
    all_fields = set()
    for group_name, fields in groups.items():
        overlap = all_fields.intersection(fields)
        if overlap:
            raise UnsupportedUpdateTarget(
                f"UPDATE fields appear in multiple groups: {sorted(overlap)!r}"
            )
        all_fields.update(fields)

    for field, expression in (raw_fields or {}).items():
        if not isinstance(expression, RawSQL) or expression not in _RAW_SQL_EXPRESSIONS:
            raise UnsupportedUpdateTarget(f"Unsupported raw SQL expression for {field!r}")


def _build_update_query(
    table: str,
    params: dict,
    where_field: str = "id",
    auto_fields: dict = None,
    raw_fields: dict = None,
    null_fields: set[str] = None,
    extra_where: sql.Composed = None,
) -> Optional[sql.Composed]:
    """
    Builds a generic and safe UPDATE query.
    Automatically filters the WHERE field to not update it in the SET
    and discards None values to avoid accidentally overwriting with NULL.

    Args:
        table: Table name
        params: Dictionary with all fields and values
        where_field: Field for WHERE (default: "id")
        auto_fields: Fields always included in SET with normal param values
                     (e.g. {"is_active": True}). Values go as %(key)s parameters.
        raw_fields: Fields always included in SET with controlled RawSQL
                    expressions (e.g. {"updated_at": RawSQL.NOW}).
        null_fields: Fields explicitly allowed to be set to NULL when their
                     value in params is None. Fields not included here keep
                     the existing behavior and are skipped when None.

    Returns:
        Generated SQL query, or None if there are no valid fields to update.
    """
    params = dict(params or {})
    auto_fields = dict(auto_fields or {})
    raw_fields = dict(raw_fields or {})
    null_fields = set(null_fields or set())
    _validate_update_request(table, params, where_field, auto_fields, raw_fields, null_fields)

    for field, value in auto_fields.items():
        params[field] = value

    fields = [
        k
        for k, v in params.items()
        if k != where_field and (v is not None or k in null_fields or k in auto_fields)
    ]

    if not fields and not raw_fields:
        return None

    set_parts = [
        sql.SQL("{} = {}").format(sql.Identifier(field), sql.Placeholder(field))
        for field in fields
    ]
    set_parts.extend(
        sql.SQL("{} = {}").format(sql.Identifier(field), _RAW_SQL_EXPRESSIONS[expression])
        for field, expression in raw_fields.items()
    )
    extra_where_sql = sql.SQL(" AND ") + extra_where if extra_where else sql.SQL("")
    return sql.SQL("UPDATE {} SET {} WHERE {} = {}{} RETURNING {};").format(
        sql.Identifier(table),
        sql.SQL(", ").join(set_parts),
        sql.Identifier(where_field),
        sql.Placeholder(where_field),
        extra_where_sql,
        sql.Identifier(where_field),
    )


def _pg_trgm_enabled(connection) -> bool:
    global _HAS_PG_TRGM
    if _HAS_PG_TRGM is not None:
        return _HAS_PG_TRGM
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') AS enabled;")
            row = cursor.fetchone()
            _HAS_PG_TRGM = bool(row and row.get("enabled"))
    except Exception:
        _HAS_PG_TRGM = False
    return _HAS_PG_TRGM


def _build_fuzzy_search(
    connection,
    column: str,
    search: Optional[str],
    param_prefix: str = "search",
) -> tuple[str, dict, str]:
    normalized = (search or "").strip()
    if not normalized:
        return "", {}, "1"

    normalized_lower = normalized.lower()
    compact_search = re.sub(r"(.)\1+", r"\1", normalized_lower)
    param = lambda name: f"{param_prefix}_{name}"
    params = {
        param("norm"): normalized_lower,
        param("like"): f"%{normalized}%",
        param("prefix"): f"{normalized_lower}%",
        param("compact_like"): f"%{compact_search}%",
        param("threshold"): TRGM_SIMILARITY_THRESHOLD,
    }

    if _pg_trgm_enabled(connection):
        condition = (
            f"({column} ILIKE %({param('like')})s "
            f"OR lower({column}) %% %({param('norm')})s "
            f"OR similarity(lower({column}), %({param('norm')})s) >= %({param('threshold')})s "
            f"OR regexp_replace(lower({column}), '(.)\\1+', '\\1', 'g') ILIKE %({param('compact_like')})s)"
        )
        order = (
            f"CASE "
            f"WHEN lower({column}) = %({param('norm')})s THEN 0 "
            f"WHEN lower({column}) LIKE %({param('prefix')})s THEN 1 "
            f"ELSE 2 END, "
            f"similarity(lower({column}), %({param('norm')})s) DESC, {column}"
        )
    else:
        condition = (
            f"({column} ILIKE %({param('like')})s "
            f"OR regexp_replace(lower({column}), '(.)\\1+', '\\1', 'g') ILIKE %({param('compact_like')})s)"
        )
        order = (
            f"CASE "
            f"WHEN lower({column}) = %({param('norm')})s THEN 0 "
            f"WHEN lower({column}) LIKE %({param('prefix')})s THEN 1 "
            f"ELSE 2 END, {column}"
        )

    return condition, params, order


def _add_fuzzy_name_condition(
    connection,
    conditions: list,
    params: dict,
    column: str,
    search: Optional[str],
    param_prefix: str = "search",
) -> None:
    condition, search_params, _ = _build_fuzzy_search(connection, column, search, param_prefix=param_prefix)
    if not condition:
        return
    conditions.append(condition)
    params.update(search_params)


# ============================================
# ENTITY-LEVEL FILTER HELPERS
# (shared by catalog.py, manual_intake.py, recipe.py)
# ============================================

def _add_entity_filters(
    conditions: list,
    params: dict,
    owner_column: str,
    users_id: int = None,
    favorite_condition: str = None,
    viewer_user_id: int = None,
) -> None:
    # Las condiciones se cualifican con el alias `entity`: todas las llamadas
    # a esta función vienen de queries que aliasan así su tabla principal
    # (FROM catalog entity / FROM manual_intake entity / FROM recipe entity).
    # Sin cualificar, un JOIN con una tabla que tenga una columna del mismo
    # nombre (p.ej. food_brands.created_by) vuelve la referencia ambigua.
    if users_id:
        conditions.append(f"entity.{owner_column} = %(users_id)s")
        params["users_id"] = users_id
    if favorite_condition:
        conditions.append(favorite_condition)
    if viewer_user_id is not None:
        conditions.append(f"(entity.is_private = FALSE OR entity.{owner_column} = %(viewer_user_id)s)")
        params["viewer_user_id"] = viewer_user_id


def _favorite_filter_sql(target_column: str, favorite: bool, params: dict, viewer_user_id: int = None) -> str:
    params["favorite_filter_user_id"] = viewer_user_id
    operator = "EXISTS" if favorite else "NOT EXISTS"
    return (
        f"{operator} ("
        "SELECT 1 FROM user_favorites uf "
        f"WHERE uf.user_id = %(favorite_filter_user_id)s AND uf.{target_column} = entity.id"
        ")"
    )


# ============================================
# TAG NORMALIZATION HELPERS
# (shared by tags.py and linked_tags.py)
# ============================================

def _normalize_tag_name(tag: str) -> str:
    return " ".join((tag or "").strip().split())


def _tag_color_from_name(tag_name: str) -> str:
    text = _normalize_tag_name(tag_name).lower()
    hue = 0
    for ch in text:
        hue = (hue * 31 + ord(ch)) % 360
    return f"hsl({hue} 80% 90%)"
