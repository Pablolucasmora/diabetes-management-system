from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class UserRead:
    id: int
    email: str
    username: str
    is_active: bool


@dataclass(frozen=True)
class UserAuthRead(UserRead):
    # Authentication-only model; never pass it to presentation or response code.
    password_hash: str = field(repr=False)


@dataclass(frozen=True)
class CreateUserCommand:
    email: str
    username: str
    password_hash: str


@dataclass(frozen=True)
class AuthSessionRead:
    id: int
    user_id: int
    csrf_token_hash: str = field(repr=False)
    expires_at: datetime
    revoked_at: datetime | None
    last_seen_at: datetime
    email: str
    username: str
    is_active: bool


def user_read_from_row(row: dict) -> UserRead:
    return UserRead(
        id=int(row["id"]),
        email=str(row["email"]),
        username=str(row["username"]),
        is_active=bool(row["is_active"]),
    )


def user_auth_read_from_row(row: dict) -> UserAuthRead:
    base = user_read_from_row(row)
    return UserAuthRead(
        **base.__dict__,
        password_hash=str(row["password_hash"]),
    )


def auth_session_read_from_row(row: dict) -> AuthSessionRead:
    return AuthSessionRead(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        csrf_token_hash=str(row["csrf_token_hash"]),
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        last_seen_at=row["last_seen_at"],
        email=str(row["email"]),
        username=str(row["username"]),
        is_active=bool(row["is_active"]),
    )
