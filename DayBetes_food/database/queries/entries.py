"""Cross-entity reads over the polymorphic "food entry" concept
(`catalog` / `manual_intake`, and in `get_consumed_food_usage_rankings`
also `portion_detail` + `intake_event`).

None of these queries has a single owning table: they aggregate or combine
several tables for a specific read need (autocomplete, "rescue"
suggestions, usage rankings). They are not the CRUD of an entity, and
that is why they do not live in any individual table's file
(code_conventions.md §1.3.1).
"""

from DayBetes_food.database.mappers import mention_suggestion_from_row
from DayBetes_food.database.queries.crud import (
    _RECIPE_VISIBLE,
    _build_fuzzy_search,
    _escape_like,
    _food_visibility_sql,
    _execute_query,
    _execute_query_many,
)
from DayBetes_food.domain.constants import IntakeEventState, PortionOrigin, SystemTag
from DayBetes_food.domain.food_entry import MENTION_SUGGESTIONS_MAX, MENTION_USAGE_DAYS, MentionSuggestion
from DayBetes_food.domain.search_text import normalize_search_text, search_text_sql
from DayBetes_food.domain.tag import SYSTEM_TAG_MEAL_TYPE
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


def get_rescue_entries_suggestions(
    connection, user_id: int, kind: SystemTag = SystemTag.RESCUE, search: str = "", limit: int = 50
) -> list[dict]:
    """Foods offered by a tab of the quick log pop-up (frontend_conventions.md §9.6).

    A food is suggested in the tab of `kind` if this user put that system tag
    on it or already ate it in a meal of the tab's type (rescue or exercise).
    With an empty search only those are returned, most recently used first.
    With a search, every visible `catalog` and `manual_intake` row whose name or
    brand/origin matches, ignoring case and accents, is returned, suggested
    foods first. Visibility is the shared SQL rule, retained rows included.
    """
    term = normalize_search_text(search)
    params = {
        "visibility_user_id": user_id,
        "system_key": kind.value,
        "meal_type": SYSTEM_TAG_MEAL_TYPE[kind].value,
        "q": term,
        "q_like": f"%{_escape_like(term)}%",
        "limit": max(1, min(int(limit or 50), 200)),
    }
    query = """
        WITH kind_tag AS (
            SELECT id FROM tags WHERE system_key = %(system_key)s
        ),
        rescue_history AS (
            SELECT pd.catalog_id, pd.manual_intake_id, MAX(ie.meal_time) AS last_used
            FROM portion_detail pd
            INNER JOIN intake_event ie ON ie.id = pd.intake_event_id
            WHERE ie.users_id = %(visibility_user_id)s
              AND ie.meal_type = %(meal_type)s
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
                    INNER JOIN kind_tag kt ON kt.id = lt.tag_id
                    WHERE lt.catalog_id = c.id AND lt.users_id = %(visibility_user_id)s
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
                    INNER JOIN kind_tag kt ON kt.id = lt.tag_id
                    WHERE lt.manual_intake_id = m.id AND lt.users_id = %(visibility_user_id)s
                ) AS is_tagged,
                rh.last_used
            FROM manual_intake m
            LEFT JOIN rescue_history rh ON rh.manual_intake_id = m.id
            WHERE {manual_visibility}
        )
        SELECT entry_type, entry_id, name, subtitle, serving_g, carbs_100g,
               (is_tagged OR last_used IS NOT NULL) AS is_suggested
        FROM (
            SELECT * FROM catalog_rows
            UNION ALL
            SELECT * FROM manual_rows
        ) src
        WHERE CASE
            WHEN %(q)s = '' THEN (is_tagged OR last_used IS NOT NULL)
            ELSE ({name} LIKE %(q_like)s OR {subtitle} LIKE %(q_like)s)
        END
        ORDER BY (is_tagged OR last_used IS NOT NULL) DESC,
                 last_used DESC NULLS LAST,
                 name ASC, entry_type ASC, entry_id ASC
        LIMIT %(limit)s;
    """.format(
        catalog_visibility=_food_visibility_sql(PortionOrigin.CATALOG, "c", include_retained=True),
        manual_visibility=_food_visibility_sql(PortionOrigin.MANUAL_INTAKE, "m", include_retained=True),
        name=search_text_sql("name"),
        subtitle=search_text_sql("subtitle"),
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
                "is_suggested": bool(row.get("is_suggested")),
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


def _match_tier_sql(column: str, param_prefix: str) -> str:
    """How well `column` matches the term of a `_build_fuzzy_search` call with
    the same `param_prefix`: 0 equal, 1 starts with it, 2 contains it, 3 only
    similar (or matched through another column). Reuses that call's params."""
    return (
        f"CASE WHEN lower({column}) = %({param_prefix}_norm)s THEN 0 "
        f"WHEN lower({column}) LIKE %({param_prefix}_prefix)s THEN 1 "
        f"WHEN lower({column}) ILIKE %({param_prefix}_like)s THEN 2 "
        f"ELSE 3 END"
    )


def get_mention_suggestions(
    connection, user_id: int, search: str = "", *, limit: int = MENTION_SUGGESTIONS_MAX
) -> list[MentionSuggestion]:
    """Entries offered after `/` in the assistant (frontend_conventions.md §9.11).

    Foods (`catalog`), dishes (`manual_intake`, never quick adds) and recipes the
    viewer can see, with the same visibility rules as the Food list, retained
    rows included. The search matches the name (without case or accents in
    `catalog` and `recipe`, §11.7), the brand of a food and the origin of a
    dish. With a search the order is: how well the name matches, favorites,
    most eaten in the last MENTION_USAGE_DAYS days, name. Without a search only
    favorites and recently eaten entries are returned. Recipes have no usage:
    a consumed portion never references its recipe. The assistant's own search
    tool asks for fewer rows (`limit`, code_conventions.md §8.12).
    """
    raw = (search or "").strip()
    term = normalize_search_text(raw)
    params = {
        "visibility_user_id": user_id,
        "state": IntakeEventState.CONSUMED.value,
        "days": MENTION_USAGE_DAYS,
        "limit": max(1, min(int(limit), MENTION_SUGGESTIONS_MAX)),
    }
    if term:
        catalog_name, catalog_params, _ = _build_fuzzy_search(
            connection, "c.search_name", term, param_prefix="mention_catalog"
        )
        brand, brand_params, _ = _build_fuzzy_search(
            connection, "brand_search.label", raw, param_prefix="mention_brand"
        )
        manual_name, manual_params, _ = _build_fuzzy_search(
            connection, "m.name", raw, param_prefix="mention_manual"
        )
        origin, origin_params, _ = _build_fuzzy_search(
            connection, "m.origin", raw, param_prefix="mention_origin"
        )
        recipe_name, recipe_params, _ = _build_fuzzy_search(
            connection, "entity.search_name", term, param_prefix="mention_recipe"
        )
        for extra in (catalog_params, brand_params, manual_params, origin_params, recipe_params):
            params.update(extra)
        # Brands resolved apart with `= ANY(ARRAY(...))`, as in list_catalog_items (§11.7).
        catalog_filter = (
            f"AND ({catalog_name} OR c.brand_id = ANY(ARRAY("
            f"SELECT brand_search.id FROM food_brands brand_search WHERE {brand})))"
        )
        manual_filter = f"AND ({manual_name} OR {origin})"
        recipe_filter = f"AND {recipe_name}"
        catalog_tier = _match_tier_sql("c.search_name", "mention_catalog")
        manual_tier = _match_tier_sql("m.name", "mention_manual")
        recipe_tier = _match_tier_sql("entity.search_name", "mention_recipe")
        outer_filter = "TRUE"
    else:
        catalog_filter = manual_filter = recipe_filter = ""
        catalog_tier = manual_tier = recipe_tier = "0"
        outer_filter = "(src.is_favorite OR src.usage_count > 0)"

    query = f"""
        WITH usage AS (
            SELECT pd.catalog_id, pd.manual_intake_id, COUNT(*)::int AS usage_count
            FROM portion_detail pd
            INNER JOIN intake_event ie ON ie.id = pd.intake_event_id
            WHERE ie.users_id = %(visibility_user_id)s
              AND ie.state = %(state)s
              AND ie.deleted_at IS NULL
              AND ie.meal_time >= CURRENT_TIMESTAMP - (%(days)s * INTERVAL '1 day')
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
                    SELECT 1 FROM user_favorites uf
                    WHERE uf.user_id = %(visibility_user_id)s AND uf.catalog_id = c.id
                ) AS is_favorite,
                COALESCE(u.usage_count, 0) AS usage_count,
                {catalog_tier} AS match_tier
            FROM catalog c
            LEFT JOIN food_brands fb ON fb.id = c.brand_id
            LEFT JOIN usage u ON u.catalog_id = c.id
            WHERE {_food_visibility_sql(PortionOrigin.CATALOG, "c", include_retained=True)}
            {catalog_filter}
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
                    SELECT 1 FROM user_favorites uf
                    WHERE uf.user_id = %(visibility_user_id)s AND uf.manual_intake_id = m.id
                ) AS is_favorite,
                COALESCE(u.usage_count, 0) AS usage_count,
                {manual_tier} AS match_tier
            FROM manual_intake m
            LEFT JOIN usage u ON u.manual_intake_id = m.id
            WHERE {_food_visibility_sql(PortionOrigin.MANUAL_INTAKE, "m", include_retained=True)}
            {manual_filter}
        ),
        recipe_rows AS (
            SELECT
                'recipe'::text AS entry_type,
                entity.id AS entry_id,
                entity.name AS name,
                ''::text AS subtitle,
                NULL::real AS serving_g,
                NULL::real AS carbs_100g,
                EXISTS (
                    SELECT 1 FROM user_favorites uf
                    WHERE uf.user_id = %(visibility_user_id)s AND uf.recipe_id = entity.id
                ) AS is_favorite,
                0 AS usage_count,
                {recipe_tier} AS match_tier
            FROM recipe entity
            WHERE {_RECIPE_VISIBLE}
            {recipe_filter}
        )
        SELECT src.entry_type, src.entry_id, src.name, src.subtitle, src.serving_g,
               src.carbs_100g, src.is_favorite
        FROM (
            SELECT * FROM catalog_rows
            UNION ALL
            SELECT * FROM manual_rows
            UNION ALL
            SELECT * FROM recipe_rows
        ) src
        WHERE {outer_filter}
        ORDER BY src.match_tier ASC,
                 src.is_favorite DESC,
                 src.usage_count DESC,
                 lower(src.name) ASC, src.entry_type ASC, src.entry_id ASC
        LIMIT %(limit)s;
    """
    rows = _execute_query_many(connection, query, params, commit=False)
    return [mention_suggestion_from_row(row) for row in rows if row]
