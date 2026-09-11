"""Construcción del canal HTTP de error (error_conventions.md §7 y §7.1).

Este módulo es la única fuente de las cabeceras de error: el identificador de
correlación (`X-Request-ID`), el código y el mensaje público (`X-App-Error`,
`X-App-Error-Message`) y el evento `appError` de `HX-Trigger`.

Lo comparten el boundary global (`main.py`) y las rutas que **devuelven** el
error en vez de levantarlo (el carrito, §7.1: edición en línea con cuerpo
vacío). Sin este punto común, esas rutas no pasaban por el boundary y sus
respuestas salían sin `X-Request-ID` (hallazgo 50 de
audit/audit_intake_event.md).

No importa rutas ni componentes: solo el catálogo de errores.
"""

import json
import re
import uuid

from DayBetes_food.errors import AppError


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def request_id(request) -> str:
    """Identificador de correlación de la petición (§6, última regla).

    Acepta el que envíe el cliente solo si tiene forma válida; en cualquier
    otro caso genera uno. No se confía en él para nada de seguridad.
    """
    supplied = request.headers.get("X-Request-ID", "").strip()
    return supplied if _REQUEST_ID_RE.fullmatch(supplied) else uuid.uuid4().hex


def header_safe_message(message: str) -> str:
    """Mensaje apto para una cabecera HTTP.

    Starlette codifica las cabeceras en latin-1, así que un guion largo, unas
    comillas tipográficas o un `€` en el mensaje público levantan
    `UnicodeEncodeError` **al construir la respuesta**: el `422` o el `409` que
    la ruta quería dar se convierte en un `500` genérico. Se sustituyen los
    caracteres no representables en vez de dejar que reviente; el texto íntegro
    viaja en el JSON de `HX-Trigger`, que escapa a `\\uXXXX` y no tiene esa
    limitación (hallazgo 51 de audit/audit_intake_event.md).
    """
    return (message or "").encode("latin-1", "replace").decode("latin-1")


def app_error_headers(request, error, message: str = "") -> dict:
    """Cabeceras del canal de error visible para una respuesta HTMX (§7.1).

    `error` puede ser una clase de `DayBetes_food/errors.py` o una instancia;
    el código y el mensaje por defecto salen siempre del catálogo central,
    nunca se inventan por endpoint (§8.3).
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


def error_json_body(error, request_id_value: str) -> dict:
    """Cuerpo JSON de error del formato único de §6.

    Existe para que ninguna capa vuelva a improvisar `{"detail": ...}`, que
    §6 prohíbe explícitamente (hallazgo 52 de audit/audit_intake_event.md).
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
