from contextvars import ContextVar
from typing import Optional


_CURRENT_USER_ID: ContextVar[Optional[int]] = ContextVar("current_user_id", default=None)


def set_current_user_id(user_id: Optional[int]):
    return _CURRENT_USER_ID.set(user_id)


def get_current_user_id() -> Optional[int]:
    return _CURRENT_USER_ID.get()


def reset_current_user_id(token) -> None:
    _CURRENT_USER_ID.reset(token)
