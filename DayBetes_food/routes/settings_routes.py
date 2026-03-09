from fasthtml.common import *
from DayBetes_food.components.settings.settings_main import settings_main
from DayBetes_food.components.ui import render_page


def setup_settings_routes(rt):
    @rt("/settings")
    def get(req):
        return render_page(
            req,
            lambda connection: settings_main(connection, current_user=req.state.user),
            show_cart=True,
        )
