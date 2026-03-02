import os


def _as_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


APP_ENV = os.getenv("APP_ENV", "development")

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "daybetes_session")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "daybetes_csrf")
SESSION_TTL_SECONDS = _as_int("SESSION_TTL_SECONDS", 60 * 60 * 24 * 14)
SESSION_REFRESH_SECONDS = _as_int("SESSION_REFRESH_SECONDS", 60 * 30)
SESSION_COOKIE_SECURE = _as_bool(os.getenv("SESSION_COOKIE_SECURE"), APP_ENV != "development")
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "lax")

AUTH_RATE_LIMIT_ATTEMPTS = _as_int("AUTH_RATE_LIMIT_ATTEMPTS", 6)
AUTH_RATE_LIMIT_WINDOW_SECONDS = _as_int("AUTH_RATE_LIMIT_WINDOW_SECONDS", 60 * 10)
AUTH_RATE_LIMIT_BLOCK_SECONDS = _as_int("AUTH_RATE_LIMIT_BLOCK_SECONDS", 60 * 15)

AUTH_TOKEN_PEPPER = os.getenv("AUTH_TOKEN_PEPPER", "")
