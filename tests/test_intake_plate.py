"""Plates of a meal: fraction eaten, derived name and exact time
(measurement_conventions.md §4.4, §4.5.1, §4.6.3)."""

from datetime import datetime, time, timezone

import pytest

from DayBetes_food.domain.constants import AmountInputUnit
from DayBetes_food.domain.intake_plate import (
    PlateEaten,
    derive_plate_name,
    eaten_fraction,
    resolve_eaten_at,
)
from DayBetes_food.errors import ValidationError


def test_an_empty_eaten_field_means_the_whole_plate():
    assert eaten_fraction(None, 300) == 1.0
    assert eaten_fraction(PlateEaten(1, None, AmountInputUnit.PERCENT), 300) == 1.0


def test_eaten_in_percent_and_in_grams():
    assert eaten_fraction(PlateEaten(1, 75, AmountInputUnit.PERCENT), 300) == pytest.approx(0.75)
    assert eaten_fraction(PlateEaten(1, 150, AmountInputUnit.GRAMS), 300) == pytest.approx(0.5)


@pytest.mark.parametrize(
    "eaten",
    [
        PlateEaten(1, 0, AmountInputUnit.PERCENT),  # nothing eaten: the meal is deleted, not confirmed
        PlateEaten(1, 120, AmountInputUnit.PERCENT),
        PlateEaten(1, 400, AmountInputUnit.GRAMS),
    ],
)
def test_a_fraction_out_of_range_is_rejected(eaten):
    with pytest.raises(ValidationError):
        eaten_fraction(eaten, 300)


def test_derived_plate_name_takes_the_first_word_of_two_ingredients():
    assert derive_plate_name(["Arroz basmati Hacendado", "Pechuga de pollo", "Tomate"]) == "Arroz, Pechuga"
    assert derive_plate_name(["Yogur natural"]) == "Yogur"


def test_exact_time_goes_to_the_closest_day_of_the_meal():
    # A meal at 00:44 Madrid time; "23:50" is the evening before, not the next one.
    meal_time = datetime(2026, 11, 16, 23, 44, tzinfo=timezone.utc)  # 00:44 on the 17th in Madrid
    eaten_at = resolve_eaten_at(meal_time, "Europe/Madrid", time(23, 50), meal_time)
    assert eaten_at.astimezone(timezone.utc) == datetime(2026, 11, 16, 22, 50, tzinfo=timezone.utc)
