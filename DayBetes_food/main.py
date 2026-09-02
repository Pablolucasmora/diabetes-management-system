from fasthtml.common import *
from datetime import datetime, timezone
from html import escape
import logging
import re
import uuid
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
from DayBetes_food.errors import AppError, InfrastructureError, ValidationError
from DayBetes_food.routes import (
    setup_auth_routes,
    setup_food_routes,
    setup_main_routes,
    setup_cart_routes,
    setup_stats_routes,
    setup_settings_routes,
)


app, rt = fast_app(
    title="DayBetes",
    htmlkw={"lang": "en"},
    static_path='DayBetes_food/static',
)

logger = logging.getLogger(__name__)


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID", "").strip()
    return supplied if _REQUEST_ID_RE.fullmatch(supplied) else uuid.uuid4().hex


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
            {
                "error": {
                    "code": error.code,
                    "message": error.public_message,
                    "fields": error.fields,
                },
                "request_id": request_id,
            },
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
AUTH_POST_EXEMPT_PATHS = {"/auth/login/submit", "/auth/register/submit", "/auth/logout"}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _is_public_path(path: str) -> bool:
    return path == "/" or path.startswith(PUBLIC_PATH_PREFIXES)


def _is_htmx_request(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


@app.middleware("http")
async def auth_security_middleware(request: Request, call_next):
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
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

    if not request.state.user and not _is_public_path(request.url.path):
        if _is_htmx_request(request):
            return HTMLResponse("", status_code=401, headers={"HX-Redirect": "/auth/login"})
        if request.method == "GET":
            return RedirectResponse(url="/auth/login", status_code=302)
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    ctx_token = set_current_user_id(request.state.user["id"] if request.state.user else None)
    try:
        response = await call_next(request)
    finally:
        reset_current_user_id(ctx_token)

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")

    if request.cookies.get(CSRF_COOKIE_NAME) != csrf_cookie:
        response.set_cookie(
            CSRF_COOKIE_NAME,
            csrf_cookie,
            httponly=False,
            secure=SESSION_COOKIE_SECURE,
            samesite=SESSION_COOKIE_SAMESITE,
            path="/",
        )
    return response

@app.middleware("http")
async def add_asset_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith(ASSET_PREFIXES):
        response.headers.setdefault("Cache-Control", STATIC_CACHE_CONTROL)
    return response

# --- COMPONENT INITIALIZATION ---

def _init_db_on_startup():
    if DB_INIT_ON_STARTUP:
        init_db()

if hasattr(app, "on_event"):
    app.on_event("startup")(_init_db_on_startup)
else:
    _init_db_on_startup()

setup_main_routes(rt)

setup_auth_routes(rt)

setup_food_routes(rt)

setup_cart_routes(rt)

setup_stats_routes(rt)

setup_settings_routes(rt)
