"""Plates of a meal: fraction eaten, derived name and exact time
(measurement_conventions.md §4.4, §4.5.1, §4.6.3)."""

from datetime import datetime, time, timedelta, timezone

import pytest

from DayBetes_food.domain.constants import AmountInputUnit
from DayBetes_food.domain.intake_plate import (
    PlateEaten,
    check_ended_at,
    derive_plate_name,
    eaten_fraction,
    resolve_eaten_at,
    resolve_ended_at,
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


def test_an_end_after_midnight_is_the_next_day():
    # A dinner at 23:00 Madrid time that ends at 00:30 ends on the next day.
    start = datetime(2026, 11, 16, 22, 0, tzinfo=timezone.utc)  # 23:00 on the 16th in Madrid
    ended_at = resolve_ended_at(start, "Europe/Madrid", time(0, 30))
    assert ended_at.astimezone(timezone.utc) == datetime(2026, 11, 16, 23, 30, tzinfo=timezone.utc)


def test_an_end_later_the_same_day_stays_on_that_day():
    start = datetime(2026, 11, 16, 13, 0, 40, tzinfo=timezone.utc)  # 14:00:40 in Madrid
    ended_at = resolve_ended_at(start, "Europe/Madrid", time(14, 45))
    assert ended_at.astimezone(timezone.utc) == datetime(2026, 11, 16, 13, 45, tzinfo=timezone.utc)


def test_an_end_is_after_its_start_and_not_in_the_future():
    start = datetime(2026, 11, 16, 13, 0, 40, tzinfo=timezone.utc)
    now = start + timedelta(hours=1)
    check_ended_at(start, start + timedelta(minutes=30), now)
    with pytest.raises(ValidationError):
        check_ended_at(start, start.replace(second=0), now)  # the same minute as the start
    with pytest.raises(ValidationError):
        check_ended_at(start, now + timedelta(minutes=1), now)
