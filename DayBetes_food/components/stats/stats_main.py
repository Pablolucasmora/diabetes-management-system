from fasthtml.common import *
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.stats.stats_calculations import compute_stats_payload
from DayBetes_food.components.stats.stats_sections import (
    daily_totals_section,
    meal_breakdown_section,
    no_user_section,
    stats_header,
)
from DayBetes_food.components.stats.stats_shared import STATS_PAGE_CLS
from DayBetes_food.database.queries import (
    get_portion_detail_by_events,
    list_consumed_intake_events,
    list_consumed_intake_events_for_day,
)
from DayBetes_food.time_utils import local_today


def stats_main(connection):
    user_id = get_current_user_id()
    if not user_id:
        return Div(no_user_section(), cls=STATS_PAGE_CLS)

    today = local_today()
    today_events = list_consumed_intake_events_for_day(connection, user_id=user_id, day=today)
    today_event_ids = [event.id for event in today_events]
    today_portions = get_portion_detail_by_events(connection, today_event_ids)

    all_consumed_events = list_consumed_intake_events(connection, user_id=user_id)
    all_event_ids = [event.id for event in all_consumed_events]
    all_portions = get_portion_detail_by_events(connection, all_event_ids)

    payload = compute_stats_payload(today_events, today_portions, all_consumed_events, all_portions)

    return Div(
        stats_header(today=today, today_events_count=int(payload["today_events_count"])),
        daily_totals_section(
            today_events_count=int(payload["today_events_count"]),
            historical_days_count=int(payload["historical_days_count"]),
            today_totals=payload["today_totals"],
            daily_average_totals=payload["daily_average_totals"],
        ),
        meal_breakdown_section(meal_groups=payload["meal_groups"]),
        cls=STATS_PAGE_CLS,
    )
