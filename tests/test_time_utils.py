"""Zone of the request (measurement_conventions.md §9.1, decision 2026-11-17)."""

from datetime import datetime, timezone

import pytest

from DayBetes_food.time_utils import (
    DEFAULT_TIMEZONE,
    current_timezone,
    local_naive_to_utc_aware,
    parse_timezone,
    reset_request_timezone,
    set_request_timezone,
)


@pytest.mark.parametrize("name", ["Atlantic/Canary", "America/Argentina/Buenos_Aires", "UTC"])
def test_known_zones_are_accepted(name):
    assert parse_timezone(name).key == name


@pytest.mark.parametrize("name", ["", None, "../../etc/passwd", "Europe/Nowhere", "x" * 70, "Europe/Madrid; rm"])
def test_unknown_or_unsafe_names_are_rejected(name):
    assert parse_timezone(name) is None


def test_typed_times_are_read_in_the_zone_of_the_request():
    token = set_request_timezone(parse_timezone("Atlantic/Canary"))
    try:
        assert local_naive_to_utc_aware(datetime(2026, 11, 17, 14, 0)) == datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc)
    finally:
        reset_request_timezone(token)
    assert current_timezone() == DEFAULT_TIMEZONE
    assert local_naive_to_utc_aware(datetime(2026, 11, 17, 14, 0)) == datetime(2026, 11, 17, 13, 0, tzinfo=timezone.utc)
