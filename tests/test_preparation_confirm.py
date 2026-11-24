"""Preparation to confirm of the cart and the food page (frontend_conventions.md §7.1, §9.4)."""

from datetime import datetime, timezone
from types import SimpleNamespace

from fasthtml.common import to_xml

from DayBetes_food.components.preparation import PreparationToConfirm
from DayBetes_food.domain.constants import ConservationMethod, CookingMethod, PortionDestination, PortionOrigin
from DayBetes_food.domain.portion_detail import (
    PreparationFood,
    missing_preparation_fields,
    preparation_levels,
    rank_preparation_options,
)

OLD = datetime(2026, 10, 1, tzinfo=timezone.utc)
NEW = datetime(2026, 11, 20, tzinfo=timezone.utc)


def _row(portion_id=1, *, cooking=None, conservation=None, quick_add=False, destination=PortionDestination.INTAKE_EVENT):
    return SimpleNamespace(
        id=portion_id,
        origin=PortionOrigin.CATALOG,
        origin_id=10,
        destination=destination,
        cooking=cooking,
        conservation=conservation,
        source=SimpleNamespace(is_quick_add=quick_add, subtype="pasta", category="cereals"),
    )


def test_levels_go_from_the_food_to_its_subtype_and_category():
    food = PreparationFood(PortionOrigin.CATALOG, 10, "pasta", "cereals")
    assert preparation_levels(food) == [("catalog", "10"), ("catalog_subtype", "pasta"), ("category", "cereals")]


def test_a_dish_without_subtype_keeps_only_its_own_history():
    dish = PreparationFood(PortionOrigin.MANUAL_INTAKE, 4, None, None)
    assert preparation_levels(dish) == [("manual_intake", "4")]


def test_the_most_frequent_comes_first_and_a_tie_goes_to_the_most_recent():
    counts = {("catalog", "10", "cooking"): [("oven", 2, OLD), ("boiled_soft", 2, NEW), ("fried", 5, OLD)]}
    assert rank_preparation_options(counts, [("catalog", "10")], "cooking") == ("fried", "boiled_soft")


def test_the_fallback_completes_up_to_two_without_repeats():
    counts = {
        ("catalog", "10", "cooking"): [("boiled_soft", 3, NEW)],
        ("catalog_subtype", "pasta", "cooking"): [("boiled_soft", 9, NEW), ("boiled_al_dente", 4, OLD)],
        ("category", "cereals", "cooking"): [("oven", 20, NEW)],
    }
    levels = [("catalog", "10"), ("catalog_subtype", "pasta"), ("category", "cereals")]
    assert rank_preparation_options(counts, levels, "cooking") == ("boiled_soft", "boiled_al_dente")


def test_no_history_at_any_level_offers_nothing():
    assert rank_preparation_options({}, [("catalog", "10")], "conservation") == ()


def test_only_the_missing_fields_of_a_meal_row_are_asked():
    assert missing_preparation_fields(_row()) == ("cooking", "conservation")
    assert missing_preparation_fields(_row(cooking=CookingMethod.OVEN)) == ("conservation",)
    assert missing_preparation_fields(_row(cooking=CookingMethod.OVEN, conservation=ConservationMethod.FRIDGE)) == ()


def test_a_quick_add_or_a_container_row_asks_nothing():
    assert missing_preparation_fields(_row(quick_add=True)) == ()
    assert missing_preparation_fields(_row(destination=PortionDestination.FRIDGE)) == ()


def test_the_cart_offers_only_the_missing_fields_that_have_values(monkeypatch):
    from DayBetes_food.services import intake_event

    rows = [
        {"level": "catalog", "key": "10", "field": "cooking", "value": "oven", "n": 3, "last_at": NEW},
        {"level": "category", "key": "cereals", "field": "conservation", "value": "fridge", "n": 1, "last_at": OLD},
    ]
    monkeypatch.setattr(intake_event, "get_preparation_counts", lambda *args, **kwargs: rows)
    set_cooking = _row(2, cooking=CookingMethod.OVEN)
    result = intake_event.cart_preparation_to_confirm(None, 1, [_row(1), set_cooking, _row(3, quick_add=True)])
    assert result == {1: {"cooking": ("oven",), "conservation": ("fridge",)}, 2: {"conservation": ("fridge",)}}


def test_the_first_value_comes_chosen_and_only_the_cart_sends_fields():
    options = {"cooking": ("boiled_soft", "oven"), "conservation": ("fridge",)}
    cart = to_xml(
        PreparationToConfirm(
            options,
            "Pasta",
            hx_post="/cart/portion/1/preparation/confirm",
            hx_target="#c",
            dismiss_key="prep_dismissed_1",
        )
    )
    assert cart.count('aria-pressed="true"') == 2
    assert 'name="cooking" value="boiled_soft"' in cart
    assert 'hx-post="/cart/portion/1/preparation/confirm"' in cart
    assert 'data-prep-key="prep_dismissed_1"' in cart
    page = to_xml(PreparationToConfirm(options, "Pasta", scope_id="food_form"))
    assert 'name="cooking"' not in page
    assert 'data-prep-scope="food_form"' in page
    # Both can be dismissed; only the cart remembers it.
    assert "data-prep-dismiss" in cart and "data-prep-dismiss" in page
    assert "data-prep-key" not in page
