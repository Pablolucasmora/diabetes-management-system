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

# Single place where logging is configured (level and format). No other
# module may call logging.basicConfig() or print() for operational, startup
# or security events.
LOG_LEVEL = logging.DEBUG if APP_ENV in {"development", "test"} else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Third-party noise that drowns our own DEBUG logs without adding anything:
# the multipart form parser emits five lines per field of every POST. Their
# level is raised instead of lowering the global one, so the app keeps its
# DEBUG output in development.
for _noisy_logger in ("python_multipart", "python_multipart.multipart", "multipart"):
    logging.getLogger(_noisy_logger).setLevel(logging.INFO)

DB_INIT_ON_STARTUP = _as_bool("DB_INIT_ON_STARTUP", APP_ENV == "development")

DATABASE_URL = _require("DATABASE_URL")
if not DATABASE_URL.startswith(("postgres://", "postgresql://")):
    raise RuntimeError(
        "DATABASE_URL must be a postgres:// or postgresql:// connection string"
    )

# Migrations identity (§12.6): owner of the schema, never used by routes/,
# services/ or database/queries/.
MIGRATIONS_DATABASE_URL = (os.getenv("MIGRATIONS_DATABASE_URL") or "").strip()
if DB_INIT_ON_STARTUP:
    if not MIGRATIONS_DATABASE_URL:
        logging.getLogger(__name__).critical(
            "MIGRATIONS_DATABASE_URL is required when DB_INIT_ON_STARTUP is enabled"
        )
        raise RuntimeError("MIGRATIONS_DATABASE_URL is required when DB_INIT_ON_STARTUP is enabled")
# The format is validated whenever the variable is set, even if the bootstrap
# does not run in this process (§8.1): the manual flow uses it as well.
if MIGRATIONS_DATABASE_URL and not MIGRATIONS_DATABASE_URL.startswith(("postgres://", "postgresql://")):
    raise RuntimeError("MIGRATIONS_DATABASE_URL must be a postgres:// or postgresql:// connection string")

# Runtime role that the bootstrap grants DML on the objects it creates.
DB_RUNTIME_ROLE = (os.getenv("DB_RUNTIME_ROLE") or "daybetes_app").strip()

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "daybetes_session")
CSRF_COOKIE_NAME = os.getenv("CSRF_COOKIE_NAME", "daybetes_csrf")
SESSION_TTL_SECONDS = _as_int("SESSION_TTL_SECONDS", 60 * 60 * 24 * 14)
SESSION_RETENTION_SECONDS = _as_int("SESSION_RETENTION_SECONDS", 60 * 60 * 24 * 14)
SESSION_REFRESH_SECONDS = _as_int("SESSION_REFRESH_SECONDS", 60 * 30)
SESSION_COOKIE_SECURE = _as_bool("SESSION_COOKIE_SECURE", APP_ENV != "development")
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "lax")

# User registration: open in development and closed by default in production
# (§8.1). When closed, its routes are not registered and answer 404.
REGISTRATION_ENABLED = _as_bool("REGISTRATION_ENABLED", APP_ENV == "development")

# Client IP (infra_conventions §9): CF-Connecting-IP can only be trusted when
# Cloudflare Tunnel is the only way into the app, i.e. in production.
TRUST_CF_CONNECTING_IP = _as_bool("TRUST_CF_CONNECTING_IP", APP_ENV == "production")

AUTH_RATE_LIMIT_ATTEMPTS =_as_int("AUTH_RATE_LIMIT_ATTEMPTS", 6)
AUTH_RATE_LIMIT_WINDOW_SECONDS = _as_int("AUTH_RATE_LIMIT_WINDOW_SECONDS", 60 * 10)
AUTH_RATE_LIMIT_BLOCK_SECONDS = _as_int("AUTH_RATE_LIMIT_BLOCK_SECONDS", 60 * 15)

AUTH_TOKEN_PEPPER = _require("AUTH_TOKEN_PEPPER")
PASSWORD_PEPPER = _require("PASSWORD_PEPPER")

# Open Food Facts adapter (H17, §8.1). It is only a prefill of the create form,
# so the timeout stays short and there are no retries.
OPEN_FOOD_FACTS_BASE_URL = (
    os.getenv("OPEN_FOOD_FACTS_BASE_URL") or "https://world.openfoodfacts.org"
).strip().rstrip("/")
if not OPEN_FOOD_FACTS_BASE_URL.startswith("https://"):
    raise RuntimeError("OPEN_FOOD_FACTS_BASE_URL must be an https:// URL")
OPEN_FOOD_FACTS_TIMEOUT_SECONDS = _as_int("OPEN_FOOD_FACTS_TIMEOUT_SECONDS", 6)
if not 1 <= OPEN_FOOD_FACTS_TIMEOUT_SECONDS <= 30:
    raise RuntimeError("OPEN_FOOD_FACTS_TIMEOUT_SECONDS must be between 1 and 30")

# Assistant for logging meals (code_conventions.md §8.12). The key is an
# optional secret: empty means the assistant does not exist in the app (its
# routes are not registered and nothing links to it), and no data leaves it.
ANTHROPIC_API_KEY = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
ASSISTANT_ENABLED = bool(ANTHROPIC_API_KEY)
# Changed without touching code (§8.12). The model id is not validated against a
# list: a wrong one fails on the first message with the generic error.
ASSISTANT_MODEL = (os.getenv("ASSISTANT_MODEL") or "claude-opus-5-5").strip()
ASSISTANT_EFFORT = (os.getenv("ASSISTANT_EFFORT") or "low").strip().lower()
if ASSISTANT_EFFORT not in {"low", "medium", "high", "xhigh", "max"}:
    raise RuntimeError("ASSISTANT_EFFORT must be one of: low, medium, high, xhigh, max")
# One call to the API; the SDK retries 429, 5xx and network errors twice with
# backoff, so a message waits at most about three times this.
ASSISTANT_TIMEOUT_SECONDS = _as_int("ASSISTANT_TIMEOUT_SECONDS", 60)
if not 5 <= ASSISTANT_TIMEOUT_SECONDS <= 300:
    raise RuntimeError("ASSISTANT_TIMEOUT_SECONDS must be between 5 and 300")
# Rounds of tools per message: at the limit it stops, keeps what was done and says so.
ASSISTANT_MAX_TOOL_ROUNDS = _as_int("ASSISTANT_MAX_TOOL_ROUNDS", 8)
if not 1 <= ASSISTANT_MAX_TOOL_ROUNDS <= 20:
    raise RuntimeError("ASSISTANT_MAX_TOOL_ROUNDS must be between 1 and 20")
