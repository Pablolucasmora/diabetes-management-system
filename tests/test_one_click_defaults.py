"""The amount method of the + of a food's row (measurement_conventions.md §6.11)."""

from types import SimpleNamespace

from DayBetes_food.domain.constants import AmountMethod, ServingMethod
from DayBetes_food.domain.portion_detail import one_click_portion_defaults


def _food(default_portion, serving_method=None, default_amount_method=AmountMethod.KITCHEN_SCALE):
    return SimpleNamespace(
        default_portion=default_portion,
        serving_method=serving_method,
        default_amount_method=default_amount_method,
        initial_state=None,
    )


def test_a_serving_is_the_usual_amount_when_not_said():
    assert one_click_portion_defaults(_food(200))["amount_method"] is AmountMethod.USUAL_AMOUNT


def test_a_package_serving_is_the_package_weight():
    defaults = one_click_portion_defaults(_food(60, ServingMethod.PACKAGE))
    assert defaults["amount_method"] is AmountMethod.PACKAGE


def test_without_serving_the_food_default_applies():
    assert one_click_portion_defaults(_food(None))["amount_method"] is AmountMethod.KITCHEN_SCALE
