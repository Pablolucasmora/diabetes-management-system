from fasthtml.common import *
from html import escape
from urllib.parse import quote_plus
from DayBetes_food.database.queries.crud import update_password_hash

from DayBetes_food.auth.security import (
    generate_token,
    hash_password,
    hash_token,
    is_strong_password,
    is_valid_email,
    is_valid_username,
    normalize_identifier,
    sanitize_text,
    verify_password,
)
from DayBetes_food.auth.models import CreateUserCommand
from DayBetes_food.auth.service import (
    GENERIC_AUTH_ERROR,
    clear_login_failures,
    create_session,
    create_user,
    get_user_by_identifier,
    register_login_failure,
    revoke_session,
    touch_user_login,
    rate_limit_login_allowed,
)
from DayBetes_food.config import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
)
from DayBetes_food.database.connection import get_connection


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host or ""
    return ""


def _form_shell(title: str, action: str, csrf_token: str, fields_html: str, submit_text: str, alt_text: str, alt_href: str, error: str = "", status_code: int = 200):
    safe_title = escape(title)
    safe_action = escape(action)
    safe_csrf = escape(csrf_token or "")
    safe_submit = escape(submit_text)
    safe_alt_text = escape(alt_text)
    safe_alt_href = escape(alt_href)
    safe_error = escape(error or "")

    error_block = (
        f'<div class="text-sm text-red-700 text-center">{safe_error}</div>'
        if safe_error else
        '<div class="hidden"></div>'
    )
    html = f"""
    <!doctype html>
    <html lang="es">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{safe_title}</title>
        <link rel="icon" type="image/svg+xml" href="/images/ui/Clock_Page.svg">
        <link rel="stylesheet" href="/css/output.css">
      </head>
      <body style="background-color:#f6f2eb;">
        <div class="min-h-screen flex flex-col items-center justify-center gap-4 px-4">
          <div class="flex flex-col gap-1 text-center">
            <h1 class="text-2xl font-bold text-gray-800">{safe_title}</h1>
            <p class="text-sm text-gray-600">Acceso seguro a DayBetes</p>
          </div>
          <form action="{safe_action}" method="post" class="web_container p-5 rounded-3xl flex flex-col gap-3 w-full md:w-md lg:w-md">
            <input type="hidden" name="csrf_token" value="{safe_csrf}">
            {fields_html}
            <button type="submit" class="web_button w-full py-2.5 text-sm">{safe_submit}</button>
          </form>
          {error_block}
          <a href="{safe_alt_href}" class="text-sm text-gray-700 underline text-center">{safe_alt_text}</a>
        </div>
      </body>
    </html>
    """
    return HTMLResponse(html, status_code=status_code)


def _redirect_with_error(path: str, message: str):
    return RedirectResponse(url=f"{path}?error={quote_plus(message)}", status_code=303)


def _registration_form(request: Request, error: str = "", status_code: int = 200):
    return _form_shell(
        title="Crear cuenta",
        action="/auth/register/submit",
        csrf_token=getattr(request.state, "csrf_token", ""),
        fields_html="""
            <input name="username" placeholder="Usuario (3-32 caracteres)" required="required"
              class="web_input border border-white rounded-lg px-3 py-2 text-sm">
            <input type="email" name="email" placeholder="Email" required="required"
              class="web_input border border-white rounded-lg px-3 py-2 text-sm">
            <p class="text-xs text-gray-600">
              Usuario: 3-32 caracteres, solo letras, numeros y guion bajo (_).
            </p>
            <input type="password" name="password" placeholder="Contrasena segura" required="required"
              class="web_input border border-white rounded-lg px-3 py-2 text-sm">
            <input type="password" name="password_confirm" placeholder="Repite contrasena" required="required"
              class="web_input border border-white rounded-lg px-3 py-2 text-sm">
            <p class="text-xs text-gray-600">
              Minimo 12 caracteres y al menos 3 de 4: mayusculas, minusculas, numeros y simbolos.
            </p>
        """,
        submit_text="Registrarse",
        alt_text="Ya tienes cuenta? Inicia sesion",
        alt_href="/auth/login",
        error=error,
        status_code=status_code,
    )


def _set_auth_cookies(response, session_token: str, csrf_token: str):
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/",
    )


def _clear_auth_cookies(response):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


def _require_post(request: Request):
    if request.method != "POST":
        return HTMLResponse("Method Not Allowed", status_code=405)
    return None


def setup_auth_routes(rt):
    @rt("/auth/login")
    def get(req: Request):
        if getattr(req.state, "user", None):
            return RedirectResponse(url="/menu", status_code=303)

        csrf_token = getattr(req.state, "csrf_token", "")
        return _form_shell(
            title="Iniciar sesion",
            action="/auth/login/submit",
            csrf_token=csrf_token,
            fields_html="""
                <input name="identifier" placeholder="Email o usuario" required="required"
                  class="web_input border border-white rounded-lg px-3 py-2 text-sm">
                <input type="password" name="password" placeholder="Contrasena" required="required"
                  class="web_input border border-white rounded-lg px-3 py-2 text-sm">
            """,
            submit_text="Entrar",
            alt_text="No tienes cuenta? Registrate",
            alt_href="/auth/register",
            error=req.query_params.get("error", ""),
        )

    @rt("/auth/register")
    def get(req: Request):
        if getattr(req.state, "user", None):
            return RedirectResponse(url="/menu", status_code=303)

        return _registration_form(req, error=req.query_params.get("error", ""))

    @rt("/auth/register/submit")
    def post(
        request: Request,
        username: str = "",
        email: str = "",
        password: str = "",
        password_confirm: str = "",
    ):
        method_error = _require_post(request)
        if method_error is not None:
            return method_error
        if getattr(request.state, "user", None):
            return RedirectResponse(url="/menu", status_code=303)

        username = normalize_identifier(sanitize_text(username, 50))
        email = normalize_identifier(sanitize_text(email, 255))

        if not is_valid_username(username):
            return _redirect_with_error("/auth/register", "Usuario invalido: usa 3-32 caracteres (letras, numeros o _)")
        if not is_valid_email(email):
            return _redirect_with_error("/auth/register", "Email invalido")
        if password != password_confirm or not is_strong_password(password):
            return _redirect_with_error(
                "/auth/register",
                "Contrasena no valida: minimo 12 caracteres y 3 de 4 tipos (mayusculas, minusculas, numeros, simbolos)",
            )

        with get_connection() as connection:
            create_user(
                connection,
                CreateUserCommand(
                    email=email,
                    username=username,
                    password_hash=hash_password(password),
                ),
            )
        return RedirectResponse(
            url="/auth/login?error=Cuenta+creada.+Inicia+sesion+para+continuar",
            status_code=303,
        )

    @rt("/auth/login/submit")
    def post(request: Request, identifier: str = "", password: str = ""):
        method_error = _require_post(request)
        if method_error is not None:
            return method_error
        if getattr(request.state, "user", None):
            return RedirectResponse(url="/menu", status_code=303)

        identifier = normalize_identifier(sanitize_text(identifier, 255))
        limiter_key_hash = hash_token(f"{identifier}:{_client_ip(request)}")

        with get_connection() as connection:
            if not rate_limit_login_allowed(connection, limiter_key_hash):
                return _redirect_with_error("/auth/login", GENERIC_AUTH_ERROR)

            # Migración gradual de la base de datos, para añadir el pepper
            user = get_user_by_identifier(connection, identifier)
            if not user:
                register_login_failure(connection, limiter_key_hash)
                return _redirect_with_error("/auth/login", GENERIC_AUTH_ERROR)

            is_valid, new_hash = verify_password(user.password_hash, password or "")
            if not is_valid:
                register_login_failure(connection, limiter_key_hash)
                return _redirect_with_error("/auth/login", GENERIC_AUTH_ERROR)

            ip_hash = hash_token(_client_ip(request))
            ua_hash = hash_token(request.headers.get("user-agent", ""))
            session_token = generate_token()
            csrf_token = generate_token()
            try:
                with connection.transaction():
                    if new_hash:
                        update_password_hash(connection, user.id, new_hash, commit=False)
                    clear_login_failures(connection, limiter_key_hash, commit=False)
                    touch_user_login(connection, user.id, commit=False)
                    create_session(
                        connection,
                        user_id=user.id,
                        session_token=session_token,
                        csrf_token=csrf_token,
                        ip_hash=ip_hash,
                        user_agent_hash=ua_hash,
                        commit=False,
                    )
            except Exception:
                return _redirect_with_error("/auth/login", "No se pudo iniciar la sesion")

        response = RedirectResponse(url="/menu", status_code=303)
        _set_auth_cookies(response, session_token=session_token, csrf_token=csrf_token)
        return response

    @rt("/auth/logout")
    def post(request: Request):
        method_error = _require_post(request)
        if method_error is not None:
            return method_error
        session_token = request.cookies.get(SESSION_COOKIE_NAME, "")
        if session_token:
            with get_connection() as connection:
                revoke_session(connection, session_token)

        response = RedirectResponse(url="/auth/login", status_code=303)
        _clear_auth_cookies(response)
        return response
