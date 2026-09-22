from datetime import date, datetime

from DayBetes_food.components.stats.stats_shared import (
    MEAL_TYPE_LABELS,
    MEAL_TYPE_ORDER,
    NUTRIENT_SPECS,
    empty_totals,
    to_float,
)
from DayBetes_food.components.cart.cart_shared import portion_intake_amount
from DayBetes_food.time_utils import to_local


def _portion_nutrient_100g(portion, nutrient_key: str):
    return getattr(portion.source, f"{nutrient_key}_100g")


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


def _event_day_key(event) -> str:
    meal_time = event.meal_time
    if isinstance(meal_time, datetime):
        local_time = to_local(meal_time)
        return local_time.date().isoformat() if local_time else meal_time.date().isoformat()
    if isinstance(meal_time, date):
        return meal_time.isoformat()
    return "sin_fecha"


def compute_stats_payload(
    today_events: list,
    today_portions: list[dict],
    all_consumed_events: list,
    all_portions: list[dict],
) -> dict:
    portions_by_today_event = {}
    for portion in today_portions:
        event_id = int(portion.destination_id or 0)
        portions_by_today_event.setdefault(event_id, []).append(portion)

    today_event_totals = {}
    for event in today_events:
        today_event_totals[event.id] = _compute_totals_for_portions(portions_by_today_event.get(event.id, []))

    today_totals = empty_totals()
    for totals in today_event_totals.values():
        _sum_totals(today_totals, totals)

    portions_by_event = {}
    for portion in all_portions:
        event_id = int(portion.destination_id or 0)
        portions_by_event.setdefault(event_id, []).append(portion)

    daily_totals_by_day = {}
    meal_type_historical_totals = {}
    for event in all_consumed_events:
        day_key = _event_day_key(event)
        if day_key not in daily_totals_by_day:
            daily_totals_by_day[day_key] = empty_totals()
        event_totals = _compute_totals_for_portions(portions_by_event.get(event.id, []))
        _sum_totals(daily_totals_by_day[day_key], event_totals)

        meal_type = event.meal_type.value if event.meal_type else "sin_tipo"
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
        meal_type = event.meal_type.value if event.meal_type else "sin_tipo"
        if meal_type not in grouped:
            grouped[meal_type] = {"count": 0, "totals": empty_totals()}
        grouped[meal_type]["count"] += 1
        _sum_totals(grouped[meal_type]["totals"], today_event_totals.get(event.id, empty_totals()))

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
