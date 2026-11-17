from DayBetes_food.auth.context import get_current_user_id
from DayBetes_food.components.stats.stats_main import stats_main, stats_without_user
from DayBetes_food.components.ui import render_page
from DayBetes_food.database.connection import get_connection
from DayBetes_food.database.queries import (
    list_consumed_intake_events,
    list_consumed_intake_events_for_day,
    list_portions_by_events,
)
from DayBetes_food.time_utils import local_today


def setup_stats_routes(rt):
    @rt("/stats")
    def get(req):
        user_id = get_current_user_id()
        if not user_id:
            return render_page(req, stats_without_user(), show_cart=True)
        today = local_today()
        # The route reads; the component only renders (code_conventions.md §1.4).
        with get_connection() as connection:
            today_events = list_consumed_intake_events_for_day(connection, user_id=int(user_id), day=today)
            today_portions = list_portions_by_events(connection, int(user_id), [event.id for event in today_events])
            all_events = list_consumed_intake_events(connection, user_id=int(user_id))
            all_portions = list_portions_by_events(connection, int(user_id), [event.id for event in all_events])
        content = stats_main(today, today_events, today_portions, all_events, all_portions)
        return render_page(req, content, show_cart=True)
