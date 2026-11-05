"""Queries for `ciqual_food`, the local copy of Ciqual (measurement_conventions.md
§12.3). Read-only. Same word search as off_product (code_conventions.md §11.7)."""

from DayBetes_food.database.mappers import ciqual_food_read_from_row
from DayBetes_food.database.queries.crud import (
    _execute_query,
    _execute_query_many,
    _pg_trgm_enabled,
    _set_trgm_similarity_threshold,
)
from DayBetes_food.domain.catalog import barcode_search_codes
from DayBetes_food.domain.constants import PrefillSource
from DayBetes_food.domain.search_text import normalize_search_text

_MIN_CHARS = 3
_COLUMNS = """
    ciq.code, ciq.name_es, ciq.name_en, ciq.category_hint, ciq.subtype, ciq.calories_100g, ciq.carbs_100g,
    ciq.sugars_100g, ciq.fats_100g, ciq.saturated_100g, ciq.proteins_100g, ciq.fiber_100g, ciq.alcohol,
    ciq.carbs_confidence, ciq.fats_confidence, ciq.proteins_confidence, ciq.value_notes
"""
# Without what this user already copied, so nothing is offered twice.
_NOT_COPIED = f"""
    NOT EXISTS (
        SELECT 1 FROM catalog entity
        WHERE entity.prefill_source = '{PrefillSource.CIQUAL.value}'
          AND entity.prefill_source_id = ciq.code::text
          AND entity.created_by = %(user_id)s
          AND entity.deleted_at IS NULL
    )
"""


def get_ciqual_food(connection, code: int):
    row = _execute_query(
        connection, f"SELECT {_COLUMNS} FROM ciqual_food ciq WHERE ciq.code = %(code)s;", {"code": code}, commit=False
    )
    return ciqual_food_read_from_row(row) if row else None


def search_ciqual_foods(connection, user_id: int, search: str, *, limit: int, offset: int = 0) -> list:
    """Every word must appear, simple names first; a barcode finds nothing here."""
    normalized = normalize_search_text(search)
    if len(normalized) < _MIN_CHARS or barcode_search_codes(search):
        return []
    words = normalized.split()
    patterns = ["%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for word in words]
    params = {"user_id": user_id, "limit": limit, "offset": offset, "patterns": patterns}
    rows = _execute_query_many(
        connection,
        f"""
        SELECT {_COLUMNS} FROM ciqual_food ciq
        WHERE ciq.search_text LIKE ALL(%(patterns)s) AND {_NOT_COPIED}
        ORDER BY (ciq.search_text LIKE %(prefix)s) DESC, (ciq.name_en ~* '\\mraw\\M') DESC,
                 length(ciq.name_es), ciq.code
        LIMIT %(limit)s OFFSET %(offset)s;
        """,
        {**params, "prefix": patterns[0][1:]},
        commit=False,
    )
    words_match = bool(rows) or (
        offset > 0
        and _execute_query(
            connection,
            "SELECT 1 AS found FROM ciqual_food ciq WHERE ciq.search_text LIKE ALL(%(patterns)s) LIMIT 1;",
            {"patterns": patterns},
            commit=False,
        )
    )
    if not words_match and _pg_trgm_enabled(connection):
        _set_trgm_similarity_threshold(connection)
        rows = _execute_query_many(
            connection,
            f"""
            SELECT {_COLUMNS} FROM ciqual_food ciq
            WHERE ciq.search_text %% %(term)s AND {_NOT_COPIED}
            ORDER BY similarity(ciq.search_text, %(term)s) DESC, ciq.code
            LIMIT %(limit)s OFFSET %(offset)s;
            """,
            {**params, "term": normalized},
            commit=False,
        )
    return [ciqual_food_read_from_row(row) for row in rows]
