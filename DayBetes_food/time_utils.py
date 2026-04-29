from datetime import datetime, timezone
from zoneinfo import ZoneInfo


APP_TIMEZONE = ZoneInfo("Europe/Madrid")
UTC_TIMEZONE = timezone.utc


def utc_now_naive() -> datetime:
    return datetime.now(UTC_TIMEZONE).replace(tzinfo=None)


def local_now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def local_today():
    return local_now().date()


def utc_naive_to_local(value):
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC_TIMEZONE)
    return value.astimezone(APP_TIMEZONE)


def local_naive_to_utc(value):
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=APP_TIMEZONE)
    return value.astimezone(UTC_TIMEZONE).replace(tzinfo=None)
