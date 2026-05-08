import hashlib
import re
import secrets
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHashError
except Exception:
    PasswordHasher = None
    VerifyMismatchError = Exception
    InvalidHashError = Exception

from DayBetes_food.config import AUTH_TOKEN_PEPPER, PASSWORD_PEPPER


_password_hasher = PasswordHasher() if PasswordHasher else None
_EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")


def normalize_identifier(value: str) -> str:
    return (value or "").strip().lower()


def sanitize_text(value: str, max_len: int) -> str:
    cleaned = "".join(ch for ch in (value or "") if ch.isprintable()).strip()
    return cleaned[:max_len]


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
    if not _password_hasher:
        raise RuntimeError("argon2-cffi is required for password hashing")
    peppered = password + PASSWORD_PEPPER
    return _password_hasher.hash(peppered)

def verify_password(password_hash: str, password: str) -> tuple[bool, str | None]:
    if not password_hash or not password:
        return False, None
    if not _password_hasher:
        return False, None

    # 1. Intenta con pepper (usuario ya migrado)
    try:
        _password_hasher.verify(password_hash, password + PASSWORD_PEPPER)
        return True, None
    except VerifyMismatchError:
        pass
    except (InvalidHashError, TypeError):
        return False, None

    # 2. Intenta sin pepper (usuario legacy) → migra
    try:
        _password_hasher.verify(password_hash, password)
        new_hash = _password_hasher.hash(password + PASSWORD_PEPPER)
        return True, new_hash
    except (VerifyMismatchError, InvalidHashError, TypeError):
        return False, None

def generate_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    raw = f"{AUTH_TOKEN_PEPPER}:{token}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
