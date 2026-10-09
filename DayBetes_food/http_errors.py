"""Building of the HTTP error channel (error_conventions.md §7 and §7.1).

This module is the only source of the error headers: the correlation
identifier (`X-Request-ID`), the public code and message (`X-App-Error`,
`X-App-Error-Message`) and the `appError` event of `HX-Trigger`.

It is shared by the global boundary (`main.py`) and by the routes that
**return** the error instead of raising it (the cart, §7.1: inline editing
with an empty body). Without this common point, those routes bypassed the
boundary and their responses went out without `X-Request-ID` (finding 50 of
audit/audit_intake_event.md).

It imports no routes or components: only the error catalog.
"""

import json
import re
import uuid

from starlette.responses import HTMLResponse

from DayBetes_food.errors import AppError


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def request_id(request) -> str:
    """Correlation identifier of the request (§6, last rule).

    It accepts the one sent by the client only if it has a valid shape;
    otherwise it generates one. It is never trusted for anything security-related.
    """
    supplied = request.headers.get("X-Request-ID", "").strip()
    return supplied if _REQUEST_ID_RE.fullmatch(supplied) else uuid.uuid4().hex


def header_safe_message(message: str) -> str:
    """Message safe for an HTTP header.

    Starlette encodes headers as latin-1, so an em dash, typographic quotes
    or a `€` in the public message raise `UnicodeEncodeError` **while building
    the response**: the `422` or `409` the route meant to return turns into a
    generic `500`. Non-representable characters are replaced instead of letting
    it blow up; the full text travels in the `HX-Trigger` JSON, which escapes
    to `\\uXXXX` and has no such limitation (finding 51 of
    audit/audit_intake_event.md).
    """
    return (message or "").encode("latin-1", "replace").decode("latin-1")


def app_error_headers(request, error, message: str = "") -> dict:
    """Headers of the visible error channel for an HTMX response (§7.1).

    `error` can be a class from `DayBetes_food/errors.py` or an instance;
    the code and the default message always come from the central catalog,
    never invented per endpoint (§8.3).
    """
    if isinstance(error, type) and issubclass(error, AppError):
        error = error()
    public_message = message or error.public_message
    return {
        "X-Request-ID": request_id(request),
        "X-App-Error": error.code,
        "X-App-Error-Message": header_safe_message(public_message),
        "HX-Trigger": json.dumps(
            {"appError": {"code": error.code, "message": public_message}}
        ),
    }


def app_error_response(request, error, message: str = ""):
    """Error response of a route: semantic status, empty body and headers (§7.1).

    Used by the routes that **return** the error instead of raising it. Inline
    actions (cart, recipe ingredients) are not a save form, so they do **not**
    use the exception of `code_conventions.md` §9.5 (`200` + fragment inside
    the form): they keep their category's status (`422` validation, `404` not
    found, `409` conflict, §3.2/§3.5/§3.6 of error_conventions.md) and return
    an empty body, because htmx must not swap an error over the component.

    So that the error is not invisible —htmx ignores the body of a `4xx`, so
    without this the user sees exactly the same as if they had not clicked
    anything— the response publishes the message through the
    `app_error_headers` headers (including the `appError` event of
    `HX-Trigger`, painted in `#app_toast` by `static/js/app_toast.js`).

    It is a **shared** helper: it lives next to the headers and every route
    that returns the error uses it, instead of reimplementing a private copy
    per module, which is what this section avoids (decision 2026-09-22).

    `error` can be a class from `DayBetes_food/errors.py` or an instance; the
    code and the default message always come from the central catalog, never
    invented per endpoint (error_conventions.md §8.3).
    """
    if isinstance(error, type) and issubclass(error, AppError):
        error = error()
    return HTMLResponse(
        "",
        status_code=error.status_code,
        headers=app_error_headers(request, error, message),
    )


def error_json_body(error, request_id_value: str) -> dict:
    """JSON error body in the single §6 format.

    It exists so that no layer improvises `{"detail": ...}` again, which §6
    explicitly forbids (finding 52 of audit/audit_intake_event.md).
    """
    if isinstance(error, type) and issubclass(error, AppError):
        error = error()
    return {
        "error": {
            "code": error.code,
            "message": error.public_message,
            "fields": error.fields,
        },
        "request_id": request_id_value,
    }
