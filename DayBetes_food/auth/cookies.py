"""The cookies of a session (code_conventions.md §8.2): one place for their attributes.

Both last as long as the session (SESSION_TTL_SECONDS) and are renewed with it, so
closing the browser or the installed app does not end it. They go together: a session
cookie with another CSRF token would answer 403 to every write (§5.2).
"""

from DayBetes_food.config import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    SESSION_TTL_SECONDS,
)


def set_auth_cookies(response, *, session_token: str, csrf_token: str) -> None:
    for name, value, httponly in (
        (SESSION_COOKIE_NAME, session_token, True),
        (CSRF_COOKIE_NAME, csrf_token, False),
    ):
        response.set_cookie(
            name,
            value,
            max_age=SESSION_TTL_SECONDS,
            httponly=httponly,
            secure=SESSION_COOKIE_SECURE,
            samesite=SESSION_COOKIE_SAMESITE,
            path="/",
        )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
