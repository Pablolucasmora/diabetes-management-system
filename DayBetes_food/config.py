import logging
import os

from dotenv import load_dotenv

load_dotenv()

VALID_APP_ENVIRONMENTS = {"development", "test", "production"}


def _as_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(
        f"Invalid boolean value for {name}: {raw!r}. "
        "Expected one of: 1/true/yes/on, 0/false/no/off."
    )


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer value for {name}: {raw!r}.") from exc


def _require(name: str) -> str:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        raise RuntimeError(f"{name} is required and cannot be empty")
    return raw.strip()


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
if APP_ENV not in VALID_APP_ENVIRONMENTS:
    raise RuntimeError(
        f"Unknown APP_ENV {APP_ENV!r}. Expected one of: {sorted(VALID_APP_ENVIRONMENTS)}."
    )

# Punto único de configuración de logging (nivel y formato). Ningún otro
# módulo debe llamar a logging.basicConfig() ni a print() para eventos
# operativos, de arranque o de seguridad.
LOG_LEVEL = logging.DEBUG if APP_ENV in {"development", "test"} else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

DB_INIT_ON_STARTUP = _as_bool("DB_INIT_ON_STARTUP", APP_ENV == "development")

DATABASE_URL = _require("DATABASE_URL")
if not DATABASE_URL.startswith(("postgres://", "postgresql://")):
    raise RuntimeError(
        "DATABASE_URL must be a postgres:// or postgresql:// connection string"
    )

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "daybetes_session")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "daybetes_csrf")
SESSION_TTL_SECONDS = _as_int("SESSION_TTL_SECONDS", 60 * 60 * 24 * 14)
SESSION_RETENTION_SECONDS = _as_int("SESSION_RETENTION_SECONDS", 60 * 60 * 24 * 14)
SESSION_REFRESH_SECONDS = _as_int("SESSION_REFRESH_SECONDS", 60 * 30)
SESSION_COOKIE_SECURE = _as_bool("SESSION_COOKIE_SECURE", APP_ENV != "development")
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "lax")

AUTH_RATE_LIMIT_ATTEMPTS = _as_int("AUTH_RATE_LIMIT_ATTEMPTS", 6)
AUTH_RATE_LIMIT_WINDOW_SECONDS = _as_int("AUTH_RATE_LIMIT_WINDOW_SECONDS", 60 * 10)
AUTH_RATE_LIMIT_BLOCK_SECONDS = _as_int("AUTH_RATE_LIMIT_BLOCK_SECONDS", 60 * 15)

AUTH_TOKEN_PEPPER = _require("AUTH_TOKEN_PEPPER")
PASSWORD_PEPPER = _require("PASSWORD_PEPPER")
