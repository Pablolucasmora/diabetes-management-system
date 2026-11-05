"""Queries for `off_product`, the local copy of Open Food Facts
(measurement_conventions.md §12.2). Read-only: the load script replaces it.

The search is its own, not `_build_fuzzy_search`: that one compares the whole
term, so "hacendado gazpacho" returned any Hacendado product (§11.7).
"""

import re

from DayBetes_food.database.mappers import off_product_read_from_row
from DayBetes_food.database.queries.crud import (
    _execute_query,
    _execute_query_many,
    _food_visibility_sql,
    _pg_trgm_enabled,
    _set_trgm_similarity_threshold,
)
from DayBetes_food.domain.constants import PortionOrigin
from DayBetes_food.domain.search_text import normalize_search_text

OFF_SEARCH_MIN_CHARS = 3
OFF_SEARCH_LIMIT = 20

_COLUMNS = """
    off.code, off.name, off.brand, off.categories, off.calories_100g, off.carbs_100g,
    off.sugars_100g, off.fats_100g, off.saturated_100g, off.proteins_100g, off.fiber_100g,
    off.caffeine, off.alcohol_vol, off.default_portion, off.nutriscore, off.nova
"""
# Without the foods the viewer can already see, so nothing is offered twice.
_NOT_IN_CATALOG = f"""
    NOT EXISTS (
        SELECT 1 FROM catalog entity
        WHERE entity.barcode = off.code
          AND {_food_visibility_sql(PortionOrigin.CATALOG, "entity", include_retained=False)}
    )
"""


def get_off_product_by_code(connection, code: str):
    """A UPC-A scans as 12 digits and OFF stores it as 13, with a leading zero."""
    codes = [code, f"0{code}"] if len(code) == 12 else [code]
    row = _execute_query(
        connection,
        f"SELECT {_COLUMNS} FROM off_product off WHERE off.code = ANY(%(codes)s) ORDER BY off.code DESC LIMIT 1;",
        {"codes": codes},
        commit=False,
    )
    return off_product_read_from_row(row) if row else None


def search_off_products(connection, user_id: int, search: str) -> list:
    """Every word must appear; if none matches, the closest by similarity, so a
    typo still finds the product."""
    normalized = normalize_search_text(search)
    if len(normalized) < OFF_SEARCH_MIN_CHARS:
        return []
    words = normalized.split()
    first_word = words[0]
    params = {
        "visibility_user_id": user_id,
        "limit": OFF_SEARCH_LIMIT,
        "patterns": [f"%{_escape_like(word)}%" for word in words],
        "first_prefix": f"{_escape_like(first_word)}%",
        "first_word_start": rf"\m{re.escape(first_word)}",
    }
    rows = _execute_query_many(
        connection,
        f"""
        SELECT {_COLUMNS} FROM off_product off
        WHERE off.search_text LIKE ALL(%(patterns)s) AND {_NOT_IN_CATALOG}
        ORDER BY (off.search_text LIKE %(first_prefix)s) DESC,
                 (off.search_text ~ %(first_word_start)s) DESC,
                 off.unique_scans_n DESC NULLS LAST, off.name, off.code
        LIMIT %(limit)s;
        """,
        params,
        commit=False,
    )
    if not rows and _pg_trgm_enabled(connection):
        _set_trgm_similarity_threshold(connection)
        rows = _execute_query_many(
            connection,
            f"""
            SELECT {_COLUMNS} FROM off_product off
            WHERE off.search_text %% %(term)s AND {_NOT_IN_CATALOG}
            ORDER BY similarity(off.search_text, %(term)s) DESC, off.unique_scans_n DESC NULLS LAST, off.code
            LIMIT %(limit)s;
            """,
            {"visibility_user_id": user_id, "limit": OFF_SEARCH_LIMIT, "term": normalized},
            commit=False,
        )
    return [off_product_read_from_row(row) for row in rows]


def _escape_like(word: str) -> str:
    return word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
