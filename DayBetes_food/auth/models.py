from dataclasses import dataclass, field


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
