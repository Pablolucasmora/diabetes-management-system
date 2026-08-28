from datetime import date, datetime

from DayBetes_food.database.queries.crud import (
    get_consumed_events,
    get_consumed_events_for_day,
    get_portion_detail_by_events,
)
from DayBetes_food.components.stats.stats_shared import (
    MEAL_TYPE_LABELS,
    MEAL_TYPE_ORDER,
    NUTRIENT_SPECS,
    empty_totals,
    to_float,
)
from DayBetes_food.components.cart.cart_shared import portion_intake_amount
from DayBetes_food.time_utils import utc_naive_to_local


def _portion_nutrient_100g(portion: dict, nutrient_key: str):
    catalog_value = portion.get(f"catalog_{nutrient_key}_100g")
    manual_value = portion.get(f"manual_{nutrient_key}_100g")
    return catalog_value if catalog_value is not None else manual_value


def _compute_totals_for_portions(portions: list[dict]) -> dict:
    totals = empty_totals()
    for portion in portions:
        intake_amount = portion_intake_amount(portion)
        if intake_amount <= 0:
            continue
        for nutrient_key, _, _ in NUTRIENT_SPECS:
            per_100g = _portion_nutrient_100g(portion, nutrient_key)
            if per_100g is None:
                continue
            totals[nutrient_key] += (intake_amount * to_float(per_100g)) / 100.0
    return totals


def _sum_totals(target: dict, source: dict):
    for nutrient_key, _, _ in NUTRIENT_SPECS:
        target[nutrient_key] += to_float(source.get(nutrient_key))


def _totals_average(totals: dict, count: int) -> dict:
    if count <= 0:
        return empty_totals()
    return {
        nutrient_key: to_float(totals.get(nutrient_key)) / count
        for nutrient_key, _, _ in NUTRIENT_SPECS
    }


def _has_non_zero_totals(totals: dict) -> bool:
    return any(to_float(totals.get(nutrient_key)) > 0 for nutrient_key, _, _ in NUTRIENT_SPECS)


def _event_day_key(event: dict) -> str:
    meal_time = event.get("meal_time")
    if isinstance(meal_time, datetime):
        local_time = utc_naive_to_local(meal_time)
        return local_time.date().isoformat() if local_time else meal_time.date().isoformat()
    if isinstance(meal_time, date):
        return meal_time.isoformat()
    return "sin_fecha"


def get_stats_payload(connection, user_id: int, today: date) -> dict:
    today_events = get_consumed_events_for_day(connection, users_id=user_id, day=today)
    today_event_ids = [int(event["id"]) for event in today_events]
    today_portions = get_portion_detail_by_events(connection, today_event_ids)

    portions_by_today_event = {}
    for portion in today_portions:
        event_id = int(portion.get("intake_event_id") or 0)
        portions_by_today_event.setdefault(event_id, []).append(portion)

    today_event_totals = {}
    for event in today_events:
        event_id = int(event["id"])
        today_event_totals[event_id] = _compute_totals_for_portions(portions_by_today_event.get(event_id, []))

    today_totals = empty_totals()
    for totals in today_event_totals.values():
        _sum_totals(today_totals, totals)

    all_consumed_events = get_consumed_events(connection, users_id=user_id)
    all_event_ids = [int(event["id"]) for event in all_consumed_events]
    all_portions = get_portion_detail_by_events(connection, all_event_ids)

    portions_by_event = {}
    for portion in all_portions:
        event_id = int(portion.get("intake_event_id") or 0)
        portions_by_event.setdefault(event_id, []).append(portion)

    daily_totals_by_day = {}
    meal_type_historical_totals = {}
    for event in all_consumed_events:
        event_id = int(event["id"])
        day_key = _event_day_key(event)
        if day_key not in daily_totals_by_day:
            daily_totals_by_day[day_key] = empty_totals()
        event_totals = _compute_totals_for_portions(portions_by_event.get(event_id, []))
        _sum_totals(daily_totals_by_day[day_key], event_totals)

        meal_type = (event.get("meal_type") or "sin_tipo").strip() or "sin_tipo"
        if meal_type not in meal_type_historical_totals:
            meal_type_historical_totals[meal_type] = empty_totals()
        _sum_totals(meal_type_historical_totals[meal_type], event_totals)

    valid_daily_totals = [one_day_totals for one_day_totals in daily_totals_by_day.values() if _has_non_zero_totals(one_day_totals)]
    days_count = len(valid_daily_totals)
    daily_average_totals = empty_totals()
    if days_count > 0:
        for one_day_totals in valid_daily_totals:
            _sum_totals(daily_average_totals, one_day_totals)
        daily_average_totals = _totals_average(daily_average_totals, days_count)

    meal_type_daily_averages = {}
    for meal_type, totals in meal_type_historical_totals.items():
        meal_type_daily_averages[meal_type] = _totals_average(totals, days_count)

    grouped = {meal_type: {"count": 0, "totals": empty_totals()} for meal_type in MEAL_TYPE_ORDER}
    for event in today_events:
        event_id = int(event["id"])
        meal_type = (event.get("meal_type") or "sin_tipo").strip() or "sin_tipo"
        if meal_type not in grouped:
            grouped[meal_type] = {"count": 0, "totals": empty_totals()}
        grouped[meal_type]["count"] += 1
        _sum_totals(grouped[meal_type]["totals"], today_event_totals.get(event_id, empty_totals()))

    meal_groups = []
    for meal_type in MEAL_TYPE_ORDER:
        group = grouped.get(meal_type)
        if not group or group["count"] <= 0:
            continue
        meal_groups.append(
            {
                "label": MEAL_TYPE_LABELS.get(meal_type, meal_type),
                "count": int(group["count"]),
                "totals": group["totals"],
                "averages": meal_type_daily_averages.get(meal_type, empty_totals()),
            }
        )

    return {
        "today_events_count": len(today_events),
        "today_totals": today_totals,
        "daily_average_totals": daily_average_totals,
        "historical_days_count": days_count,
        "meal_groups": meal_groups,
    }
