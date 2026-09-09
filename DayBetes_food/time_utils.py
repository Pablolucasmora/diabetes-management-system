from datetime import datetime, timezone
from zoneinfo import ZoneInfo


APP_TIMEZONE = ZoneInfo("Europe/Madrid")
UTC_TIMEZONE = timezone.utc


def local_now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def local_today():
    return local_now().date()


def to_local(value):
    """UTC naive o aware -> hora local (APP_TIMEZONE).

    La migración de `meal_time` a TIMESTAMPTZ ya se completó: ahora todas las
    columnas de tiempo del dominio de comidas usan TIMESTAMPTZ. La rama naive
    se conserva por compatibilidad defensiva con cualquier lectura heredada.
    """
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC_TIMEZONE)
    return value.astimezone(APP_TIMEZONE)


def utc_now() -> datetime:
    """Instante actual aware en UTC (para columnas TIMESTAMPTZ)."""
    return datetime.now(UTC_TIMEZONE)


def local_naive_to_utc_aware(value):
    """Fecha/hora local de un formulario -> instante aware en UTC.

    NO descarta el tzinfo: el destino es una columna TIMESTAMPTZ y un naive se
    reinterpretaria con el TimeZone de la sesion de PostgreSQL.
    """
    if value is None:
        return None
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=APP_TIMEZONE)
    return value.astimezone(UTC_TIMEZONE)
