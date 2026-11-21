"""How a fraction that split an amount was obtained (study_conventions.md §6.3)."""

import pytest
from starlette.datastructures import FormData

from DayBetes_food.domain.constants import AmountInputUnit, FractionMethod
from DayBetes_food.domain.fridge import KeepPart, take_split_method
from DayBetes_food.domain.portion_detail import combine_split_methods
from DayBetes_food.errors import ValidationError
from DayBetes_food.routes.cart_routes import _parse_eaten

EYEBALL, WEIGHED = FractionMethod.EYEBALL, FractionMethod.WEIGHED


@pytest.mark.parametrize(
    ("methods", "expected"),
    [
        ((), None),
        ((None, None), None),
        ((None, WEIGHED), WEIGHED),
        ((WEIGHED, WEIGHED), WEIGHED),
        ((WEIGHED, EYEBALL), EYEBALL),
        ((EYEBALL, None), EYEBALL),
    ],
)
def test_the_least_precise_split_wins(methods, expected):
    assert combine_split_methods(*methods) is expected


def test_a_take_in_grams_is_weighed_and_in_percent_by_eye():
    assert take_split_method(AmountInputUnit.GRAMS) is WEIGHED
    assert take_split_method(AmountInputUnit.PERCENT) is EYEBALL


def test_keep_part_is_weighed_only_with_both_weights():
    assert KeepPart(fraction=0.5, rest_weight=None).split_method is EYEBALL
    assert KeepPart(fraction=0.5, rest_weight=120.0).split_method is WEIGHED


def _form(**fields):
    return FormData([("plate_id", "4"), ("ingested_unit_4", "%"), *fields.items()])


def test_eaten_is_by_eye_unless_marked_weighed():
    assert _parse_eaten(_form(ingested_value_4="50"))[0].method is EYEBALL
    assert _parse_eaten(_form(ingested_value_4="50", eaten_method_4="weighed"))[0].method is WEIGHED


def test_an_unknown_eaten_method_is_rejected():
    with pytest.raises(ValidationError):
        _parse_eaten(_form(ingested_value_4="50", eaten_method_4="guess"))
