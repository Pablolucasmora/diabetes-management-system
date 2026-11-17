"""Amounts and metrics of the portions (measurement_conventions.md §4, §5.2, §6)."""

import math

import pytest

from DayBetes_food.domain.constants import AmountInputUnit, AmountMethod, MacrosSource, PortionOrigin
from DayBetes_food.domain.portion_detail import (
    amount_to_grams,
    calculate_macro_summary_metrics,
    parse_amount_grams,
    raw_amount,
)
from DayBetes_food.errors import ValidationError


@pytest.mark.parametrize(
    ("value", "unit", "serving", "grams"),
    [
        (80, AmountInputUnit.GRAMS, None, 80),
        (2, AmountInputUnit.PORTION, 125, 250),
        (1, AmountInputUnit.OZ, None, 28.349523125),
        (1, AmountInputUnit.LB, None, 453.59237),
    ],
)
def test_amount_to_grams(value, unit, serving, grams):
    assert math.isclose(amount_to_grams(value, unit, serving), grams)


@pytest.mark.parametrize(
    ("unit", "serving"),
    [(AmountInputUnit.PERCENT, None), (AmountInputUnit.PORTION, None)],
)
def test_amount_to_grams_rejects_units_without_mass(unit, serving):
    with pytest.raises(ValidationError):
        amount_to_grams(1, unit, serving)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), 100001, None, "12"])
def test_parse_amount_grams_rejects(value):
    with pytest.raises(ValidationError):
        parse_amount_grams(value)


def test_raw_amount_converts_cooked_weight_with_the_factor():
    # 300 g of cooked rice with factor 2.5 (cooked / raw) were 120 g raw.
    assert raw_amount(300, PortionOrigin.CATALOG, True, 2.5) == pytest.approx(120)
    # Without the mark, or without a factor, the amount is used as weighed.
    assert raw_amount(300, PortionOrigin.CATALOG, False, 2.5) == 300
    assert raw_amount(300, PortionOrigin.CATALOG, True, None) == 300
    # manual_intake has no factor.
    assert raw_amount(300, PortionOrigin.MANUAL_INTAKE, True, 2.5) == 300


def test_amount_confidence_is_the_share_of_weighed_grams(portion):
    portions = [
        portion(100, AmountMethod.KITCHEN_SCALE),
        portion(50, AmountMethod.PACKAGE),
        portion(50, AmountMethod.EYEBALL),
        portion(100, None),  # not given counts as not weighed
    ]
    metrics = calculate_macro_summary_metrics(portions)
    assert metrics["amount_confidence"] == pytest.approx(150 / 300)


def test_quality_confidence_and_coverage(portion):
    portions = [
        portion(100, carbs=10, macros_source=MacrosSource.LABEL),
        portion(100, carbs=None, macros_source=MacrosSource.AI_ESTIMATE),
    ]
    metrics = calculate_macro_summary_metrics(portions)
    assert metrics["quality_confidence"] == pytest.approx(0.5)
    assert metrics["carbs_coverage"] == pytest.approx(0.5)
    assert metrics["sugars_coverage"] == 0


def test_metrics_of_an_empty_meal_are_zero():
    metrics = calculate_macro_summary_metrics([])
    assert metrics["amount_confidence"] == 0
    assert metrics["carbs_coverage"] == 0
