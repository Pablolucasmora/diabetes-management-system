from fasthtml.common import *
from DayBetes_food.components.stats.stats_main import stats_main
from DayBetes_food.components.ui import render_page


def setup_stats_routes(rt):
    @rt("/stats")
    def get(req):
        return render_page(req, stats_main, show_cart=True)
