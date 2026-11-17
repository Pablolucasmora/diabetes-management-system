import hashlib
import re
import secrets

# A direct import: argon2-cffi is a required dependency, and if it cannot be
# imported the app must fail at startup, not reject every login silently.
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from DayBetes_food.config import AUTH_TOKEN_PEPPER, PASSWORD_PEPPER


_password_hasher = PasswordHasher()
# Hash of a random secret, verified when the user does not exist so that a
# missing user takes as long as a wrong password (no user enumeration by timing).
_DUMMY_PASSWORD_HASH = _password_hasher.hash(secrets.token_urlsafe(32) + PASSWORD_PEPPER)
_EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def normalize_identifier(value: str) -> str:
    return (value or "").strip().lower()


def sanitize_text(value: str) -> str:
    """Normalize an input text: drop non-printable characters and trim
    surrounding whitespace.

    It is normalization only (§7.2): it does **not** truncate. Each field's
    maximum length is its column's, and it is checked at the boundary, which
    rejects the excess instead of silently trimming it (§7.3, decision 2026-09-09).
    """
    return "".join(ch for ch in (value or "") if ch.isprintable()).strip()


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email or ""))


def is_valid_username(username: str) -> bool:
    return bool(_USERNAME_RE.match(username or ""))


def is_strong_password(password: str) -> bool:
    if password is None or len(password) < 12:
        return False
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_symbol = any(not c.isalnum() for c in password)
    score = sum([has_upper, has_lower, has_digit, has_symbol])
    return score >= 3


def hash_password(password: str) -> str:
    peppered = password + PASSWORD_PEPPER
    return _password_hasher.hash(peppered)

def verify_password(password_hash: str, password: str) -> tuple[bool, str | None]:
    if not password_hash or not password:
        return False, None

    # 1. Try with the pepper (user already migrated)
    try:
        _password_hasher.verify(password_hash, password + PASSWORD_PEPPER)
        return True, None
    except VerifyMismatchError:
        pass
    except (InvalidHashError, TypeError):
        return False, None

    # 2. Try without the pepper (legacy user) → migrate
    try:
        _password_hasher.verify(password_hash, password)
        new_hash = _password_hasher.hash(password + PASSWORD_PEPPER)
        return True, new_hash
    except (VerifyMismatchError, InvalidHashError, TypeError):
        return False, None

def burn_password_check(password: str) -> None:
    """Spend the time of one Argon2 verification without a real hash: used when
    the login identifier matches no active user (code_conventions.md §5.2)."""
    try:
        _password_hasher.verify(_DUMMY_PASSWORD_HASH, (password or "") + PASSWORD_PEPPER)
    except (VerifyMismatchError, InvalidHashError):
        pass


def generate_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    raw = f"{AUTH_TOKEN_PEPPER}:{token}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
