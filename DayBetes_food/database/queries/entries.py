"""Cross-entity reads over the polymorphic "food entry" concept
(`catalog` / `manual_intake`, and in `get_consumed_food_usage_rankings`
also `portion_detail` + `intake_event`).

None of these queries has a single owning table: they aggregate or combine
several tables for a specific read need (autocomplete, "rescue"
suggestions, usage rankings). They are not the CRUD of an entity, and
that is why they do not live in any individual table's file
(code_conventions.md §1.3.1).
"""

from DayBetes_food.database.queries.crud import (
    _build_fuzzy_search,
    _food_visibility_sql,
    _execute_query,
    _execute_query_many,
)
from DayBetes_food.domain.constants import RESCUE_TAG_NAME, IntakeEventState, MealType, PortionOrigin
from DayBetes_food.time_utils import APP_TIMEZONE


def get_subtype_suggestions(connection, search: str = "", limit: int = 50) -> list[str]:
    search_condition, search_params, search_order = _build_fuzzy_search(connection, "source.name", search)
    params = {**search_params, "limit": max(1, min(int(limit or 50), 500))}
    query = """
        WITH source AS (
            SELECT DISTINCT trim(c.subtype) AS name
            FROM catalog c
            WHERE c.deleted_at IS NULL
              AND c.subtype IS NOT NULL AND trim(c.subtype) <> ''
            UNION
            SELECT DISTINCT trim(m.subtype) AS name
            FROM manual_intake m
            WHERE m.deleted_at IS NULL
              AND m.subtype IS NOT NULL AND trim(m.subtype) <> ''
        )
        SELECT source.name AS name
        FROM source
        WHERE {search_condition}
        ORDER BY {search_order}
        LIMIT %(limit)s;
    """.format(search_condition=search_condition or "TRUE", search_order=search_order)
    rows = _execute_query_many(connection, query, params, commit=False)
    return [str(row["name"]) for row in rows if row and row.get("name")]


def get_subtype_label(connection, subtype: str) -> str | None:
    """Return the stored subtype that matches `subtype` case-insensitively, or None.

    Validation by existence in SQL, without the 500-row cap of the autocomplete (H25).
    """
    query = """
        SELECT s.label
        FROM (
            SELECT trim(c.subtype) AS label FROM catalog c WHERE c.deleted_at IS NULL
            UNION
            SELECT trim(m.subtype) FROM manual_intake m
            WHERE m.deleted_at IS NULL AND m.subtype IS NOT NULL
        ) s
        WHERE lower(s.label) = lower(%(subtype)s)
        ORDER BY s.label
        LIMIT 1;
    """
    row = _execute_query(connection, query, {"subtype": subtype}, commit=False)
    return str(row["label"]) if row and row.get("label") is not None else None


def get_rescue_entries_suggestions(connection, user_id: int, search: str = "", limit: int = 50) -> list[dict]:
    """Foods offered by the rescue pop-up (frontend_conventions.md §9.6).

    A food is a rescue food if it carries the RESCUE_TAG_NAME tag or if this
    user already ate it in a `rescue` event. With an empty search only those
    are returned, most recently used first. With a search, every visible
    `catalog` and `manual_intake` row that matches is returned, rescue foods
    first. Visibility is the shared SQL rule, retained rows included.
    """
    normalized = (search or "").strip()
    params = {
        "visibility_user_id": user_id,
        "rescue_tag": RESCUE_TAG_NAME,
        "rescue_meal_type": MealType.RESCUE.value,
        "q": normalized,
        "q_like": f"%{normalized}%",
        "limit": max(1, min(int(limit or 50), 200)),
    }
    query = """
        WITH rescue_tag AS (
            SELECT id
            FROM tags
            WHERE lower(trim(name)) = lower(%(rescue_tag)s)
        ),
        rescue_history AS (
            SELECT pd.catalog_id, pd.manual_intake_id, MAX(ie.meal_time) AS last_used
            FROM portion_detail pd
            INNER JOIN intake_event ie ON ie.id = pd.intake_event_id
            WHERE ie.users_id = %(visibility_user_id)s
              AND ie.meal_type = %(rescue_meal_type)s
              AND ie.deleted_at IS NULL
            GROUP BY pd.catalog_id, pd.manual_intake_id
        ),
        catalog_rows AS (
            SELECT
                'catalog'::text AS entry_type,
                c.id AS entry_id,
                c.name AS name,
                COALESCE(fb.label, '') AS subtitle,
                c.default_portion AS serving_g,
                c.carbs_100g AS carbs_100g,
                EXISTS (
                    SELECT 1 FROM linked_tags lt
                    INNER JOIN rescue_tag rt ON rt.id = lt.tag_id
                    WHERE lt.catalog_id = c.id
                ) AS is_tagged,
                rh.last_used
            FROM catalog c
            LEFT JOIN food_brands fb ON fb.id = c.brand_id
            LEFT JOIN rescue_history rh ON rh.catalog_id = c.id
            WHERE {catalog_visibility}
        ),
        manual_rows AS (
            SELECT
                'manual_intake'::text AS entry_type,
                m.id AS entry_id,
                m.name AS name,
                COALESCE(m.origin, '') AS subtitle,
                m.default_portion AS serving_g,
                m.carbs_100g AS carbs_100g,
                EXISTS (
                    SELECT 1 FROM linked_tags lt
                    INNER JOIN rescue_tag rt ON rt.id = lt.tag_id
                    WHERE lt.manual_intake_id = m.id
                ) AS is_tagged,
                rh.last_used
            FROM manual_intake m
            LEFT JOIN rescue_history rh ON rh.manual_intake_id = m.id
            WHERE {manual_visibility}
        )
        SELECT entry_type, entry_id, name, subtitle, serving_g, carbs_100g,
               (is_tagged OR last_used IS NOT NULL) AS is_rescue
        FROM (
            SELECT * FROM catalog_rows
            UNION ALL
            SELECT * FROM manual_rows
        ) src
        WHERE CASE
            WHEN %(q)s = '' THEN (is_tagged OR last_used IS NOT NULL)
            ELSE (name ILIKE %(q_like)s OR subtitle ILIKE %(q_like)s)
        END
        ORDER BY (is_tagged OR last_used IS NOT NULL) DESC,
                 last_used DESC NULLS LAST,
                 name ASC, entry_type ASC, entry_id ASC
        LIMIT %(limit)s;
    """.format(
        catalog_visibility=_food_visibility_sql(PortionOrigin.CATALOG, "c", include_retained=True),
        manual_visibility=_food_visibility_sql(PortionOrigin.MANUAL_INTAKE, "m", include_retained=True),
    )
    rows = _execute_query_many(connection, query, params, commit=False)
    out = []
    for row in rows:
        if not row:
            continue
        serving_g = row.get("serving_g")
        out.append(
            {
                "entry_type": str(row.get("entry_type") or ""),
                "entry_id": int(row.get("entry_id") or 0),
                "name": str(row.get("name") or "").strip(),
                "subtitle": str(row.get("subtitle") or "").strip(),
                "serving_g": (float(serving_g) if serving_g is not None else None),
                "carbs_100g": (float(row["carbs_100g"]) if row.get("carbs_100g") is not None else None),
                "is_rescue": bool(row.get("is_rescue")),
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
            # §4.1: the state comes from the central enum, not from a literal in the SQL.
            "state": IntakeEventState.CONSUMED.value,
        },
        commit=False,
    )
