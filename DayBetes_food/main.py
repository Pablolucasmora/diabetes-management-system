from fasthtml.common import *
from datetime import datetime
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse

from DayBetes_food.auth.context import reset_current_user_id, set_current_user_id
from DayBetes_food.auth.security import generate_token
from DayBetes_food.auth.service import get_session_with_user, is_csrf_valid, refresh_session
from DayBetes_food.config import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    SESSION_REFRESH_SECONDS,
)
from DayBetes_food.database.db_init import init_db
from DayBetes_food.database.connection import get_connection
from DayBetes_food.routes.auth_routes import setup_auth_routes
from DayBetes_food.routes.food_routes import setup_food_routes
from DayBetes_food.routes.main_routes import setup_main_routes
from DayBetes_food.routes.cart_routes import setup_cart_routes
from DayBetes_food.routes.stats_routes import setup_stats_routes
from DayBetes_food.routes.settings_routes import setup_settings_routes


app, rt = fast_app(
    title="DayBetes",
    htmlkw={"lang": "es"},
    static_path='DayBetes_food/static',
)

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
                    "id": session_row["user_id"],
                    "email": session_row["email"],
                    "username": session_row["username"],
                }
                last_seen = session_row.get("last_seen_at")
                if last_seen and (datetime.utcnow() - last_seen).total_seconds() >= SESSION_REFRESH_SECONDS:
                    refresh_session(connection, int(session_row["id"]))

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
