"""Lecturas cross-entity sobre el concepto polimórfico "entrada de comida"
(`catalog` / `manual_intake`, y en `get_consumed_food_usage_rankings`
también `portion_detail` + `intake_event`).

Ninguna de estas queries tiene una única tabla dueña: agregan o combinan
varias tablas para una necesidad de lectura concreta (autocompletado,
sugerencias de "rescate", rankings de uso). No son CRUD de una entidad y
por eso no viven en el archivo de ninguna tabla individual
(code_conventions.md §1.3.1).
"""

from DayBetes_food.database.queries.crud import _build_fuzzy_search, _execute_query_many
from DayBetes_food.domain.constants import IntakeEventState
from DayBetes_food.time_utils import APP_TIMEZONE


def get_subtype_suggestions(connection, search: str = "", limit: int = 50) -> list[str]:
    search_condition, search_params, search_order = _build_fuzzy_search(connection, "name", search)
    params = {**search_params, "limit": max(1, min(int(limit or 50), 500))}
    query = """
        WITH source AS (
            SELECT DISTINCT trim(subtype) AS name
            FROM catalog
            WHERE deleted_at IS NULL
              AND subtype IS NOT NULL AND trim(subtype) <> ''
            UNION
            SELECT DISTINCT trim(subtype) AS name
            FROM manual_intake
            WHERE deleted_at IS NULL
              AND subtype IS NOT NULL AND trim(subtype) <> ''
        )
        SELECT name
        FROM source
        WHERE {search_condition}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """.format(search_condition=search_condition or "TRUE", search_order=search_order)
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def get_category_suggestions(connection, search: str = "", limit: int = 50) -> list[str]:
    search_condition, search_params, search_order = _build_fuzzy_search(connection, "name", search)
    params = {**search_params, "limit": max(1, min(int(limit or 50), 500))}
    query = """
        WITH defaults AS (
            SELECT unnest(ARRAY[
                'meat', 'fish', 'dairy', 'eggs', 'processed_meat',
                'legumes', 'tubers', 'nuts', 'vegetables', 'fruits',
                'cereals', 'oils_and_fats', 'sweets', 'beverages',
                'sauces', 'condiments', 'supplements'
            ]) AS name
        ),
        source AS (
            SELECT DISTINCT trim(category) AS name
            FROM catalog
            WHERE deleted_at IS NULL
              AND category IS NOT NULL AND trim(category) <> ''
            UNION
            SELECT name FROM defaults
        )
        SELECT name
        FROM source
        WHERE {search_condition}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """.format(search_condition=search_condition or "TRUE", search_order=search_order)
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def get_rescue_entries_suggestions(connection, users_id: int, search: str = "", limit: int = 50) -> list[dict]:
    normalized = (search or "").strip()
    params = {
        "users_id": users_id,
        "q": normalized,
        "q_like": f"%{normalized}%",
        "limit": max(1, min(int(limit or 50), 200)),
    }
    query = """
        WITH rescue_tag AS (
            SELECT id
            FROM tags
            WHERE lower(trim(name)) = 'rescate'
            LIMIT 1
        ),
        catalog_rows AS (
            SELECT
                'catalog'::text AS entry_type,
                c.id AS entry_id,
                c.name AS name,
                COALESCE(fb.label, '') AS subtitle,
                COALESCE(c.default_portion, 100.0) AS serving_g,
                NULL::double precision AS available_g
            FROM linked_tags lt
            INNER JOIN rescue_tag rt ON rt.id = lt.tag_id
            INNER JOIN catalog c ON c.id = lt.catalog_id
            LEFT JOIN food_brands fb ON fb.id = c.brand_id
            WHERE c.deleted_at IS NULL
              AND (c.is_private = FALSE OR c.created_by = %(users_id)s)
              AND (%(q)s = '' OR c.name ILIKE %(q_like)s OR COALESCE(fb.label, '') ILIKE %(q_like)s)
        ),
        manual_rows AS (
            SELECT
                'manual_intake'::text AS entry_type,
                m.id AS entry_id,
                m.name AS name,
                COALESCE(m.origin, '') AS subtitle,
                COALESCE(m.amount_g, 100.0) AS serving_g,
                COALESCE(m.amount_g, 0.0) AS available_g
            FROM linked_tags lt
            INNER JOIN rescue_tag rt ON rt.id = lt.tag_id
            INNER JOIN manual_intake m ON m.id = lt.manual_intake_id
            WHERE m.deleted_at IS NULL
              AND (m.is_private = FALSE OR m.created_by = %(users_id)s)
              AND (%(q)s = '' OR m.name ILIKE %(q_like)s OR COALESCE(m.origin, '') ILIKE %(q_like)s)
        )
        SELECT *
        FROM (
            SELECT * FROM catalog_rows
            UNION ALL
            SELECT * FROM manual_rows
        ) src
        ORDER BY name ASC, entry_type ASC, entry_id ASC
        LIMIT %(limit)s;
    """
    rows = _execute_query_many(connection, query, params, commit=False)
    out = []
    for row in rows:
        if not row:
            continue
        out.append(
            {
                "entry_type": str(row.get("entry_type") or ""),
                "entry_id": int(row.get("entry_id") or 0),
                "name": str(row.get("name") or "").strip(),
                "subtitle": str(row.get("subtitle") or "").strip(),
                "serving_g": float(row.get("serving_g") or 100.0),
                "available_g": (float(row.get("available_g")) if row.get("available_g") is not None else None),
            }
        )
    return out


def get_consumed_food_usage_rankings(connection, users_id: int, days: int = 60) -> list[dict]:
    """Gets personalized food rankings weighted by frequency and time-of-day proximity."""
    safe_days = max(1, int(days or 60))
    query = """
        WITH base AS (
            SELECT
                pd.catalog_id,
                pd.manual_intake_id,
                (
                    EXTRACT(HOUR FROM (ie.meal_time AT TIME ZONE %(app_timezone)s)) * 60
                    + EXTRACT(MINUTE FROM (ie.meal_time AT TIME ZONE %(app_timezone)s))
                )::int AS event_minute,
                (
                    EXTRACT(HOUR FROM (CURRENT_TIMESTAMP AT TIME ZONE %(app_timezone)s)) * 60
                    + EXTRACT(MINUTE FROM (CURRENT_TIMESTAMP AT TIME ZONE %(app_timezone)s))
                )::int AS now_minute
            FROM portion_detail pd
            INNER JOIN intake_event ie ON ie.id = pd.intake_event_id
            WHERE ie.users_id = %(users_id)s
              AND ie.state = %(state)s
              AND ie.deleted_at IS NULL
              AND ie.meal_time >= CURRENT_TIMESTAMP - (%(days)s * INTERVAL '1 day')
        ),
        scored AS (
            SELECT
                catalog_id,
                manual_intake_id,
                LEAST(
                    ABS(event_minute - now_minute),
                    1440 - ABS(event_minute - now_minute)
                )::numeric AS minute_distance
            FROM base
        ),
        catalog_rank AS (
            SELECT
                'catalog'::text AS entry_type,
                catalog_id AS entry_id,
                COUNT(*)::int AS usage_count,
                AVG(minute_distance) AS avg_minute_distance,
                SUM(1.0 / (1.0 + (minute_distance / 60.0))) AS proximity_score
            FROM scored
            WHERE catalog_id IS NOT NULL
            GROUP BY catalog_id
        ),
        manual_rank AS (
            SELECT
                'manual_intake'::text AS entry_type,
                manual_intake_id AS entry_id,
                COUNT(*)::int AS usage_count,
                AVG(minute_distance) AS avg_minute_distance,
                SUM(1.0 / (1.0 + (minute_distance / 60.0))) AS proximity_score
            FROM scored
            WHERE manual_intake_id IS NOT NULL
            GROUP BY manual_intake_id
        ),
        combined AS (
            SELECT * FROM catalog_rank
            UNION ALL
            SELECT * FROM manual_rank
        )
        SELECT
            entry_type,
            entry_id,
            usage_count,
            avg_minute_distance,
            proximity_score,
            (usage_count * 100.0 + proximity_score * 10.0) AS rank_score
        FROM combined
        ORDER BY
            rank_score DESC,
            usage_count DESC,
            avg_minute_distance ASC,
            entry_type ASC,
            entry_id ASC;
    """
    return _execute_query_many(
        connection,
        query,
        {
            "users_id": users_id,
            "days": safe_days,
            "app_timezone": APP_TIMEZONE.key,
            # §4.1: el estado sale del enum central, no de un literal en el SQL.
            "state": IntakeEventState.CONSUMED.value,
        },
        commit=False,
    )
