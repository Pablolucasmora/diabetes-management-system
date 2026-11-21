"""The served totals per plate behind `Eating` in the cart summary
(frontend_conventions.md §7.14)."""

import json
from types import SimpleNamespace

from DayBetes_food.components.cart.cart_components import MacrosSummary, _eaten_plate_totals
from DayBetes_food.domain.constants import AmountMethod, PortionOrigin


def _portion(plate_id, amount, carbs_100g, calories_100g=100.0):
    source = SimpleNamespace(
        cooking_factor=None,
        calories_100g=calories_100g,
        carbs_100g=carbs_100g,
        sugars_100g=None,
        fats_100g=None,
        saturated_100g=None,
        proteins_100g=None,
        fiber_100g=None,
        macros_source=None,
    )
    return SimpleNamespace(
        plate_id=plate_id,
        amount=amount,
        origin=PortionOrigin.CATALOG,
        is_cooked_weight=False,
        amount_method=AmountMethod.KITCHEN_SCALE,
        source=source,
    )


def test_totals_are_grouped_by_plate():
    totals = _eaten_plate_totals([_portion(1, 200, 50), _portion(1, 100, 10), _portion(2, 50, None)])

    assert totals["1"]["amount"] == 300
    assert totals["1"]["carbs"] == 110
    assert totals["1"]["kcal"] == 300
    # A macro the food does not give adds nothing, as in the served totals.
    assert totals["2"]["carbs"] == 0
    assert totals["2"]["amount"] == 50


def test_portions_without_plate_are_left_out():
    assert _eaten_plate_totals([_portion(None, 100, 10)]) == {}


def test_summary_carries_the_plate_totals():
    event = SimpleNamespace(id=7, amount_confidence=None)
    html = str(MacrosSummary(event, [_portion(3, 100, 20)]))

    assert 'data-eaten-summary="7"' in html
    start = html.index("data-eaten-plates='") + len("data-eaten-plates='")
    plates = json.loads(html[start : html.index("'", start)])
    assert plates["3"]["carbs"] == 20
