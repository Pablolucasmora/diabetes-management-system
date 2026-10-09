from fasthtml.common import *
from datetime import datetime, timezone
from html import escape
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse

from DayBetes_food.auth.context import reset_current_user_id, set_current_user_id
from DayBetes_food.auth.security import generate_token
from DayBetes_food.auth.service import get_session_with_user, is_csrf_valid, refresh_session
from DayBetes_food.config import (
    CSRF_COOKIE_NAME,
    DB_INIT_ON_STARTUP,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    SESSION_REFRESH_SECONDS,
)
from DayBetes_food.database.db_init import init_db
from DayBetes_food.database.connection import get_connection
from DayBetes_food.errors import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    InfrastructureError,
    ValidationError,
)
from DayBetes_food.http_errors import (
    app_error_headers,
    error_json_body,
    request_id as _request_id,
)
from DayBetes_food.routes import (
    setup_auth_routes,
    setup_food_routes,
    setup_main_routes,
    setup_cart_routes,
    setup_stats_routes,
    setup_settings_routes,
)


async def lifespan(app):
    # Code before the yield runs once at startup, before serving requests;
    # code after it runs at shutdown. Replaces on_event("startup"), removed in
    # Starlette 1.0. FastHTML expects the bare generator, without
    # @asynccontextmanager: it wraps it itself.
    if DB_INIT_ON_STARTUP:
        init_db()
    yield


app, rt = fast_app(
    title="DayBetes",
    htmlkw={"lang": "en"},
    static_path='DayBetes_food/static',
    lifespan=lifespan,
)

logger = logging.getLogger(__name__)


def _error_html(message: str, *, fragment: bool) -> str:
    safe_message = escape(message)
    if fragment:
        return (
            '<div class="web_container p-3 rounded-xl border border-red-200 '
            'bg-red-50 text-sm text-red-700">'
            f"{safe_message}</div>"
        )
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{safe_message}</title></head><body>{_error_html(message, fragment=True)}</body></html>"
    )


def _error_response(request: Request, error: AppError, request_id: str):
    is_json = "application/json" in request.headers.get("accept", "").lower()
    is_htmx = request.headers.get("HX-Request") == "true"
    headers = {"X-Request-ID": request_id}
    status_code = 200 if is_htmx and isinstance(error, ValidationError) else error.status_code
    if is_json:
        return JSONResponse(
            error_json_body(error, request_id),
            status_code=error.status_code,
            headers=headers,
        )
    return HTMLResponse(
        _error_html(error.public_message, fragment=is_htmx),
        status_code=status_code,
        headers=headers,
    )


async def _handle_app_error(request: Request, error: AppError):
    request_id = _request_id(request)
    if error.log_level == "error":
        cause = error.__cause__
        if cause is not None:
            logger.error(
                "Application error",
                exc_info=(type(cause), cause, cause.__traceback__),
                extra={"error_code": error.code, "request_id": request_id},
            )
        else:
            logger.error(
                "Application error",
                extra={"error_code": error.code, "request_id": request_id},
            )
    return _error_response(request, error, request_id)


async def _handle_unexpected_error(request: Request, error: Exception):
    request_id = _request_id(request)
    logger.error(
        "Unexpected application error",
        exc_info=(type(error), error, error.__traceback__),
        extra={"error_code": "infrastructure_error", "request_id": request_id},
    )
    return _error_response(request, InfrastructureError(), request_id)


app.add_exception_handler(AppError, _handle_app_error)
app.add_exception_handler(Exception, _handle_unexpected_error)

app.add_middleware(GZipMiddleware, minimum_size=512)

STATIC_CACHE_CONTROL = "public, max-age=604800"
ASSET_PREFIXES = ("/css/", "/js/", "/images/")
PUBLIC_PATH_PREFIXES = ("/auth", "/css", "/js", "/images", "/favicon", "/robots.txt")
AUTH_POST_EXEMPT_PATHS = {"/auth/login/submit", "/auth/register/submit"}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _is_public_path(path: str) -> bool:
    return path == "/" or path.startswith(PUBLIC_PATH_PREFIXES)


def _is_htmx_request(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _response_sets_cookie(response, cookie_name: str) -> bool:
    prefix = f"{cookie_name}=".encode()
    return any(key == b"set-cookie" and value.startswith(prefix) for key, value in response.raw_headers)


async def auth_security_middleware(request: Request, call_next):
    # Static assets are cacheable (Cache-Control: public, see
    # add_asset_cache_headers) and may be served from a CDN/edge. If this path
    # wrote a CSRF cookie here, that Set-Cookie header could be cached and
    # replayed to different visitors, poisoning their CSRF cookie with a token
    # that does not belong to their session. A GET for a public asset has
    # nothing to authenticate or CSRF-validate.
    if request.url.path.startswith(ASSET_PREFIXES):
        return await call_next(request)

    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME) or generate_token()
    request.state.csrf_token = csrf_cookie
    request.state.user = None

    session_cookie = request.cookies.get(SESSION_COOKIE_NAME, "")
    session_row = None
    if session_cookie:
        with get_connection() as connection:
            session_row = get_session_with_user(connection, session_cookie)
            if session_row:
                request.state.user = {
                    "id": session_row.user_id,
                    "email": session_row.email,
                    "username": session_row.username,
                }
                last_seen = session_row.last_seen_at
                if last_seen and (datetime.now(timezone.utc) - last_seen).total_seconds() >= SESSION_REFRESH_SECONDS:
                    refresh_session(connection, session_row.id)

    csrf_exempt = request.url.path in AUTH_POST_EXEMPT_PATHS
    if request.method in UNSAFE_METHODS and not csrf_exempt:
        supplied_token = request.headers.get("X-CSRF-Token", "")
        if not supplied_token and request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
            form = await request.form()
            supplied_token = str(form.get("csrf_token", ""))

        if not supplied_token or supplied_token != csrf_cookie or not is_csrf_valid(session_row, supplied_token):
            # A CSRF failure is a `403` with a generic message (§9), but in the
            # project's error format: the middleware runs outside the global
            # boundary (an exception raised here never reaches
            # `_handle_app_error`), so it builds the response through the same
            # shared channel instead of improvising `{"detail": ...}`, which §6
            # forbids. For HTMX the body is empty and the notice travels in the
            # §7.1 headers, as in the cart routes: that way the "tab left open
            # since yesterday" gets its own message instead of an opaque `403`
            # (finding 52 of audit/audit_intake_event.md).
            csrf_error = AuthorizationError()
            csrf_message = "Tu sesión ha caducado. Recarga la página e inténtalo de nuevo."
            if _is_htmx_request(request):
                return HTMLResponse(
                    "",
                    status_code=csrf_error.status_code,
                    headers=app_error_headers(request, csrf_error, csrf_message),
                )
            csrf_request_id = _request_id(request)
            return JSONResponse(
                error_json_body(csrf_error, csrf_request_id),
                status_code=csrf_error.status_code,
                headers={"X-Request-ID": csrf_request_id},
            )

    if not request.state.user and not _is_public_path(request.url.path):
        if _is_htmx_request(request):
            return HTMLResponse("", status_code=401, headers={"HX-Redirect": "/auth/login"})
        if request.method == "GET":
            return RedirectResponse(url="/auth/login", status_code=302)
        # Same reason as the `403` above: the single §6 format, no
        # `{"detail": ...}`.
        auth_error = AuthenticationError()
        auth_request_id = _request_id(request)
        return JSONResponse(
            error_json_body(auth_error, auth_request_id),
            status_code=auth_error.status_code,
            headers={"X-Request-ID": auth_request_id},
        )

    ctx_token = set_current_user_id(request.state.user["id"] if request.state.user else None)
    try:
        response = await call_next(request)
    finally:
        reset_current_user_id(ctx_token)

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")

    # If the route itself (e.g. login/register) already set the CSRF cookie
    # bound to the session it just created, do not overwrite it with the
    # "orphan" token generated at the start of this function: doing so left the
    # browser with a cookie that was never stored in auth_sessions, and every
    # later POST (logout included) failed with 403.
    if request.cookies.get(CSRF_COOKIE_NAME) != csrf_cookie and not _response_sets_cookie(response, CSRF_COOKIE_NAME):
        response.set_cookie(
            CSRF_COOKIE_NAME,
            csrf_cookie,
            httponly=False,
            secure=SESSION_COOKIE_SECURE,
            samesite=SESSION_COOKIE_SAMESITE,
            path="/",
        )
    return response

async def add_asset_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith(ASSET_PREFIXES):
        response.headers.setdefault("Cache-Control", STATIC_CACHE_CONTROL)
    return response


# Starlette 1.0 removed the @app.middleware decorator. Each add_middleware
# wraps the previous ones, so the order of these lines sets the execution
# order: add_asset_cache_headers is the outer layer and GZip the inner one.
app.add_middleware(BaseHTTPMiddleware, dispatch=auth_security_middleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=add_asset_cache_headers)

# --- COMPONENT INITIALIZATION ---

setup_main_routes(rt)

setup_auth_routes(rt)

setup_food_routes(rt)

setup_cart_routes(rt)

setup_stats_routes(rt)

setup_settings_routes(rt)
