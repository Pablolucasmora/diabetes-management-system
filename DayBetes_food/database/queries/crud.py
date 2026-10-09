"""
Shared query helpers for the `database/queries/` package.

This module no longer holds per-table CRUD functions (see code_conventions.md
§1.3.1). It only contains:

- generic SQL execution helpers (`_execute_query`, `_execute_query_many`);
- the safe dynamic UPDATE builder (`_build_update_query` and its
  validation/whitelist helpers);
- fuzzy-search helpers shared by several table modules
  (`_build_fuzzy_search`, `_add_fuzzy_name_condition`);
- ownership/favorite filter helpers used by `recipe.py`
  (`_add_entity_filters`, `_favorite_filter_sql`);
- the visibility rule of `catalog` and `manual_intake`, shared by
  `catalog.py`, `manual_intake.py` and `entries.py` (`_food_visibility_sql`);
- tag normalization helpers shared by `tags.py` and `linked_tags.py`
  (`_normalize_tag_name`, `_tag_color_from_name`);
- constants shared across table modules (`TRGM_SIMILARITY_THRESHOLD`).

Table-specific queries live in one module per table
(`users.py`, `catalog.py`, `manual_intake.py`, `recipe.py`, `tags.py`,
`linked_tags.py`, `user_favorites.py`, `food_brands.py`, `intake_event.py`,
`portion_detail.py`) plus `entries.py` for reads that span more than one
table with no single owning table. All of them are re-exported from
`database/queries/__init__.py`.
"""

import re
from enum import Enum
from typing import Optional, Any

from psycopg import sql

from DayBetes_food.domain.constants import PortionOrigin

TRGM_SIMILARITY_THRESHOLD = 0.25
_HAS_PG_TRGM = None
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_UPDATE_TABLES = {
    "catalog",
    "manual_intake",
    "recipe",
    "intake_event",
    "intake_plate",
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
) -> Optional[Any]:
    """Generic helper to execute a query that returns at most one row.

    A SQL failure always propagates (code_conventions.md 2.5): in owner mode
    (`commit=True`) the helper rolls back its own operation first; in
    caller-owned mode (`commit=False`) it never rolls back. `None` therefore
    only ever means "no row", never "failed".
    Logging is left to the boundary that turns the exception into a response
    (error_conventions.md 10.3).
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params or {})
            if commit:
                connection.commit()
            return cursor.fetchone()
    except Exception:
        if commit:
            connection.rollback()
        raise


def _execute_query_many(
    connection,
    query: str,
    params: dict = None,
    commit: bool = True,
) -> list:
    """Generic helper to execute a query that returns several rows.

    Same error contract as `_execute_query`: `[]` only ever means "no rows".
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, params or {})
            if commit:
                connection.commit()
            return cursor.fetchall()
    except Exception:
        if commit:
            connection.rollback()
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
    qualified_key = sql.SQL("{}.{}").format(sql.Identifier(table), sql.Identifier(where_field))
    return sql.SQL("UPDATE {} SET {} WHERE {} = {}{} RETURNING {};").format(
        sql.Identifier(table),
        sql.SQL(", ").join(set_parts),
        qualified_key,
        sql.Placeholder(where_field),
        extra_where_sql,
        qualified_key,
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


def fuzzy_compact_sql(column: str) -> str:
    """The column lowercased with runs of a repeated letter collapsed ("coffee"
    -> "cofe"), so a search that doubles or drops a letter still matches.

    Shared by `_build_fuzzy_search` and the `idx_*_compact_trgm` indexes of
    `db_init.py`: an expression index is only used if the query repeats the
    exact same expression (§11.7).
    """
    return f"regexp_replace(lower({column}), '(.)\\1+', '\\1', 'g')"


def _set_trgm_similarity_threshold(connection) -> None:
    """Make the `%` operator use TRGM_SIMILARITY_THRESHOLD instead of the
    pg_trgm default (0.3). Unlike `similarity(...) >= x`, `%` can use a
    trigram index. Session scope: every request opens its own connection."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('pg_trgm.similarity_threshold', %(threshold)s, false);",
            {"threshold": str(TRGM_SIMILARITY_THRESHOLD)},
        )


def _build_fuzzy_search(
    connection,
    column: str,
    search: Optional[str],
    param_prefix: str = "search",
) -> tuple[str, dict, str]:
    """Fuzzy match of `column` against `search`: substring, trigram similarity
    and substring of the collapsed form (`fuzzy_compact_sql`).

    With pg_trgm every branch is written over `lower(column)` or its collapsed
    form, so the `idx_*_trgm` and `idx_*_compact_trgm` indexes can serve the
    whole OR; one branch without an index would turn it into a full scan.
    Returns the condition, its params and an ORDER BY expression.
    """
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
    }
    compact_column = fuzzy_compact_sql(column)

    if _pg_trgm_enabled(connection):
        _set_trgm_similarity_threshold(connection)
        condition = (
            f"(lower({column}) ILIKE %({param('like')})s "
            f"OR lower({column}) %% %({param('norm')})s "
            f"OR {compact_column} ILIKE %({param('compact_like')})s)"
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
            f"(lower({column}) ILIKE %({param('like')})s "
            f"OR {compact_column} ILIKE %({param('compact_like')})s)"
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
# (used by recipe.py)
# ============================================

def _add_entity_filters(
    conditions: list,
    params: dict,
    owner_column: str,
    users_id: int = None,
    favorite_condition: str = None,
    viewer_user_id: int = None,
) -> None:
    # Conditions are qualified with the `entity` alias: every call to this
    # function comes from queries that alias their main table that way
    # (FROM catalog entity / FROM manual_intake entity / FROM recipe entity).
    # Unqualified, a JOIN with a table that has a column with the same
    # name (e.g. food_brands.created_by) makes the reference ambiguous.
    if users_id:
        conditions.append(f"entity.{owner_column} = %(users_id)s")
        params["users_id"] = users_id
    if favorite_condition:
        conditions.append(favorite_condition)
    if viewer_user_id is not None:
        conditions.append(f"(entity.is_published OR entity.{owner_column} = %(viewer_user_id)s)")
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


_FOOD_VISIBILITY_COLUMNS = {  # technical whitelist (§4.6): user_favorites / portion_detail columns
    PortionOrigin.CATALOG: "catalog_id",
    PortionOrigin.MANUAL_INTAKE: "manual_intake_id",
}


def _food_visibility_sql(origin: PortionOrigin, alias: str, *, include_retained: bool) -> str:
    """SQL visibility rule of `catalog` and `manual_intake` (§11.2.2, §11.2.3, §11.4.1).

    Shared by catalog.py, manual_intake.py and entries.py, so it lives here
    (§1.3.1). `alias` is validated because it is interpolated; the user id
    always travels as the `%(visibility_user_id)s` SQL parameter. It returns:
    - listable: active AND (published OR owned by the viewer);
    - retained (optional): unpublished or archived, but kept in the viewer's
      favorites or in one of their recipes.
    manual_intake adds NOT is_quick_add to the whole rule: a quick add only
    exists through its portion, which reads it through the portion_detail JOIN,
    not through this rule (§11.2.3).
    """
    if not _IDENTIFIER_RE.fullmatch(alias or ""):
        raise ValueError(f"Invalid food visibility alias: {alias!r}")
    origin = PortionOrigin(origin)
    column = _FOOD_VISIBILITY_COLUMNS[origin]
    a = alias
    listable = (
        f"({a}.deleted_at IS NULL AND ({a}.is_published OR {a}.created_by = %(visibility_user_id)s))"
    )
    retained = (
        f"(EXISTS (SELECT 1 FROM user_favorites vf "
        f"WHERE vf.user_id = %(visibility_user_id)s AND vf.{column} = {a}.id)"
        f" OR EXISTS (SELECT 1 FROM portion_detail vpd JOIN recipe vr ON vr.id = vpd.recipe_id "
        f"WHERE vpd.{column} = {a}.id AND vr.users_id = %(visibility_user_id)s))"
    )
    rule = f"({listable} OR {retained})" if include_retained else listable
    if origin is PortionOrigin.MANUAL_INTAKE:
        rule = f"(NOT {a}.is_quick_add AND {rule})"
    return rule


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
