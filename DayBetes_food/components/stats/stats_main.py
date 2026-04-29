from datetime import datetime
from fasthtml.common import *
from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.stats.stats_calculations import get_stats_payload
from DayBetes_food.components.stats.stats_sections import (
    daily_totals_section,
    meal_breakdown_section,
    no_user_section,
    stats_header,
)
from DayBetes_food.components.stats.stats_shared import STATS_PAGE_CLS


def stats_main(connection):
    user_id = get_current_user_id()
    if not user_id:
        return Div(no_user_section(), cls=STATS_PAGE_CLS)

    today = datetime.now().date()
    payload = get_stats_payload(connection, user_id=user_id, today=today)

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
