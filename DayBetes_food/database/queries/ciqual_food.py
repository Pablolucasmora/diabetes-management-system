"""Queries for `ciqual_food`, the local copy of Ciqual (measurement_conventions.md
§12.3). Read-only: the load script replaces it."""

from DayBetes_food.database.mappers import ciqual_food_read_from_row
from DayBetes_food.database.queries.crud import _execute_query, _search_reference_foods
from DayBetes_food.domain.catalog import barcode_search_codes
from DayBetes_food.domain.constants import PrefillSource

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
    """A word search, raw foods and simple names first; a barcode finds nothing here."""
    if barcode_search_codes(search):
        return []
    rows = _search_reference_foods(
        connection,
        search,
        table_sql="ciqual_food ciq",
        alias="ciq",
        columns_sql=_COLUMNS,
        not_offered_sql=_NOT_COPIED,
        tiebreak_sql=r"(ciq.name_en ~* '\mraw\M') DESC, length(ciq.name_es), ciq.code",
        params={"user_id": user_id},
        limit=limit,
        offset=offset,
    )
    return [ciqual_food_read_from_row(row) for row in rows]
