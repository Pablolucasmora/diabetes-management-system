"""Queries for `off_product`, the local copy of Open Food Facts
(measurement_conventions.md §12.2). Read-only: the load script replaces it.
"""

from DayBetes_food.database.mappers import off_product_read_from_row
from DayBetes_food.database.queries.crud import (
    _execute_query,
    _execute_query_many,
    _food_visibility_sql,
    _search_reference_foods,
)
from DayBetes_food.domain.catalog import barcode_search_codes
from DayBetes_food.domain.constants import PortionOrigin

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
    codes = barcode_search_codes(code)
    if not codes:
        return None
    row = _execute_query(
        connection,
        f"SELECT {_COLUMNS} FROM off_product off WHERE off.code = ANY(%(codes)s) ORDER BY off.code DESC LIMIT 1;",
        {"codes": codes},
        commit=False,
    )
    return off_product_read_from_row(row) if row else None


def search_off_products(connection, user_id: int, search: str, *, limit: int, offset: int = 0) -> list:
    """A barcode finds its product; anything else is a word search.
    Products whose name is only a store brand stay out of the word search."""
    codes = barcode_search_codes(search)
    if codes:
        rows = _execute_query_many(
            connection,
            f"""
            SELECT {_COLUMNS} FROM off_product off
            WHERE off.code = ANY(%(codes)s) AND {_NOT_IN_CATALOG}
            ORDER BY off.code DESC
            LIMIT %(limit)s OFFSET %(offset)s;
            """,
            {"visibility_user_id": user_id, "codes": codes, "limit": limit, "offset": offset},
            commit=False,
        )
    else:
        rows = _search_reference_foods(
            connection,
            search,
            table_sql="off_product off",
            alias="off",
            columns_sql=_COLUMNS,
            searchable_sql="NOT off.name_is_store_brand",
            not_offered_sql=_NOT_IN_CATALOG,
            tiebreak_sql="off.unique_scans_n DESC NULLS LAST, off.name, off.code",
            params={"visibility_user_id": user_id},
            limit=limit,
            offset=offset,
        )
    return [off_product_read_from_row(row) for row in rows]
