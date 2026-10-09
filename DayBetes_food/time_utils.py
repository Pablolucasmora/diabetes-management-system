from datetime import datetime, timezone
from zoneinfo import ZoneInfo


APP_TIMEZONE = ZoneInfo("Europe/Madrid")
UTC_TIMEZONE = timezone.utc


def local_now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def local_today():
    return local_now().date()


def to_local(value):
    """Naive or aware UTC -> local time (APP_TIMEZONE).

    The migration of `meal_time` to TIMESTAMPTZ is complete: every time
    column in the meals domain now uses TIMESTAMPTZ. The naive branch is
    kept for defensive compatibility with any legacy read.
    """
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC_TIMEZONE)
    return value.astimezone(APP_TIMEZONE)


def utc_now() -> datetime:
    """Current aware instant in UTC (for TIMESTAMPTZ columns)."""
    return datetime.now(UTC_TIMEZONE)


def local_naive_to_utc_aware(value):
    """Local date/time from a form -> aware instant in UTC.

    It does NOT drop tzinfo: the target is a TIMESTAMPTZ column, and a naive
    value would be reinterpreted with the PostgreSQL session's TimeZone.
    """
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=APP_TIMEZONE)
    return value.astimezone(UTC_TIMEZONE)
