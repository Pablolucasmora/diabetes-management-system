import hashlib
import re
import secrets
import hmac

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHashError
except Exception:
    PasswordHasher = None
    VerifyMismatchError = Exception
    InvalidHashError = Exception

from DayBetes_food.config import AUTH_TOKEN_PEPPER


_password_hasher = PasswordHasher() if PasswordHasher else None
_EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64


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
    if _password_hasher:
        return _password_hasher.hash(password)
    salt = secrets.token_hex(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    ).hex()
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt}${derived}"


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash or not password:
        return False

    if password_hash.startswith("scrypt$"):
        try:
            _, n_raw, r_raw, p_raw, salt, expected = password_hash.split("$", 5)
            derived = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt.encode("utf-8"),
                n=int(n_raw),
                r=int(r_raw),
                p=int(p_raw),
                dklen=len(bytes.fromhex(expected)),
            ).hex()
            return hmac.compare_digest(derived, expected)
        except Exception:
            return False

    if not _password_hasher:
        return False

    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, TypeError):
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    raw = f"{AUTH_TOKEN_PEPPER}:{token}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
