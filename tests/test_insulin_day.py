"""The insulin day of the injection pop-up's pen (measurement_conventions.md §8.4)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from DayBetes_food.domain.insulin_pen import insulin_day_start

MADRID = ZoneInfo("Europe/Madrid")


def test_the_day_starts_at_half_past_six():
    now = datetime(2026, 11, 24, 9, 15, tzinfo=MADRID)
    assert insulin_day_start(now) == datetime(2026, 11, 24, 6, 30, tzinfo=MADRID)


def test_a_late_night_shot_still_belongs_to_the_day_before():
    now = datetime(2026, 11, 25, 1, 0, tzinfo=MADRID)
    assert insulin_day_start(now) == datetime(2026, 11, 24, 6, 30, tzinfo=MADRID)


def test_half_past_six_is_already_the_new_day():
    now = datetime(2026, 11, 24, 6, 30, tzinfo=MADRID)
    assert insulin_day_start(now) == now
