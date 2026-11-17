"""Local time of the request (measurement_conventions.md §9).

The zone is the browser's (decision of the user, 2026-11-17, audit H-10):
static/js/timezone.js keeps the IANA name `Intl` reports in a cookie, and the
middleware of main.py validates it and sets it for the request. Without that
cookie, or with a name that is not a known IANA zone, the zone is
DEFAULT_TIMEZONE. It is the zone in which typed times are read, in which times
are shown, and the one stored as `timezone_at_event` of a new event.
"""

import re
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones


DEFAULT_TIMEZONE = ZoneInfo("Europe/Madrid")
UTC_TIMEZONE = timezone.utc
# Cookie written by static/js/timezone.js; the name is repeated there.
TIMEZONE_COOKIE_NAME = "daybetes_tz"

_ZONE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+){0,2}$")
_request_timezone: ContextVar[ZoneInfo | None] = ContextVar("request_timezone", default=None)


@lru_cache(maxsize=1)
def _known_zone_names() -> frozenset[str]:
    return frozenset(available_timezones())


def parse_timezone(name: str | None) -> ZoneInfo | None:
    """The IANA zone with that name, or None when it is empty or unknown. The
    value comes from a cookie: it is checked against the list of known zones,
    never used as a file path as it comes."""
    value = (name or "").strip()
    if not value or len(value) > 64 or not _ZONE_NAME_RE.match(value):
        return None
    if value not in _known_zone_names():
        return None
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def set_request_timezone(zone: ZoneInfo | None) -> Token:
    return _request_timezone.set(zone)


def reset_request_timezone(token: Token) -> None:
    _request_timezone.reset(token)


def current_timezone() -> ZoneInfo:
    """Zone of the current request, or DEFAULT_TIMEZONE outside one."""
    return _request_timezone.get() or DEFAULT_TIMEZONE


def local_now() -> datetime:
    return datetime.now(current_timezone())


def local_today():
    return local_now().date()


def to_local(value):
    """Naive or aware UTC -> local time of the request.

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
    return value.astimezone(current_timezone())


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
        value = value.replace(tzinfo=current_timezone())
    return value.astimezone(UTC_TIMEZONE)
