"""Maximum size of a request body (code_conventions.md §5.5).

Starlette reads a whole form, files included, before the route runs, so a size
checked in the route (the assistant's photos) comes after the body was already
received. This ASGI middleware stops a larger body as it arrives: by its
`Content-Length` when the client declares it, and by counting the bytes
otherwise (a chunked body). The answer is `400 malformed_request` with the error
channel of error_conventions.md §7.1, before any route or form parser runs.
"""

from starlette.requests import Request

from DayBetes_food.domain.assistant import ASSISTANT_PHOTO_MAX_BYTES, ASSISTANT_PHOTOS_MAX
from DayBetes_food.errors import MalformedRequestError
from DayBetes_food.http_errors import app_error_response
from DayBetes_food.security_headers import add_security_headers

# Forms of the app: text fields only, far under this.
DEFAULT_MAX_BODY_BYTES = 1_000_000
# The assistant message: its photos at their limit, plus the text and the form.
_ASSISTANT_MAX_BODY_BYTES = ASSISTANT_PHOTOS_MAX * ASSISTANT_PHOTO_MAX_BYTES + 1_000_000
MAX_BODY_BYTES_BY_PATH = {"/assistant/message": _ASSISTANT_MAX_BODY_BYTES}
TOO_LARGE_MESSAGE = "The request is too large."


class BodyTooLargeError(MalformedRequestError):
    """Raised while a body without Content-Length is read past its limit. It is
    an AppError, so the global boundary answers it as malformed_request (400)."""

    public_message = TOO_LARGE_MESSAGE


class BodySizeLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = MAX_BODY_BYTES_BY_PATH.get(scope["path"], DEFAULT_MAX_BODY_BYTES)
        declared = Request(scope).headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await _reject(scope, receive, send)
            return

        received = 0
        started = False

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLargeError()
            return message

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLargeError:
            if started:
                raise
            await _reject(scope, receive, send)
        except BaseExceptionGroup as group:
            # BaseHTTPMiddleware reads the body inside a task group, which wraps it.
            if started or group.subgroup(BodyTooLargeError) is None:
                raise
            await _reject(scope, receive, send)


async def _reject(scope, receive, send) -> None:
    # Outside the middleware that adds the headers.
    response = add_security_headers(app_error_response(Request(scope), MalformedRequestError, TOO_LARGE_MESSAGE))
    await response(scope, receive, send)
