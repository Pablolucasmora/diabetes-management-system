"""Food routes, split by area (audit H-11). setup_food_routes registers
them all; the order of the groups keeps the original registration order
as far as it matters for matching (checked when the split was made)."""

from DayBetes_food.routes.food.browse import setup_browse_routes
from DayBetes_food.routes.food.entries import setup_entries_routes
from DayBetes_food.routes.food.recipes import setup_recipes_routes
from DayBetes_food.routes.food.adding import setup_adding_routes
from DayBetes_food.routes.food.menus import setup_menus_routes


def setup_food_routes(rt):
    setup_browse_routes(rt)
    setup_entries_routes(rt)
    setup_recipes_routes(rt)
    setup_adding_routes(rt)
    setup_menus_routes(rt)
