(function () {
  // Canal único de avisos de error de la web (decisión 2026-09-10, hallazgo 37
  // de audit/audit_intake_event.md).
  //
  // Las rutas HTMX conservan su status semántico y devuelven cuerpo vacío; el
  // mensaje público viaja en cabeceras (`X-App-Error-Message`) y, cuando la
  // respuesta es 2xx, en el evento `appError` de `HX-Trigger`. Aquí se pinta
  // sobre #app_toast, definido una sola vez en el layout (components/ui.py).
  if (window.__dbAppToastBootstrapped) return;
  window.__dbAppToastBootstrapped = true;

  var HIDE_MS = 4000;
  var DEDUPE_MS = 300;
  var hideTimer = null;
  var lastMessage = "";
  var lastShownAt = 0;

  // Mensaje por defecto por status, para las respuestas que aún no declaran
  // uno propio (por ejemplo el 403 de "sin header HX-Request").
  var DEFAULT_BY_STATUS = {
    400: "La petición no tiene un formato válido.",
    401: "Necesitas iniciar sesión.",
    403: "No tienes permiso para realizar esta operación.",
    404: "El recurso no existe o no está disponible.",
    409: "La operación entra en conflicto con el estado actual.",
    422: "Los datos enviados no son válidos.",
    429: "Se han realizado demasiadas peticiones. Inténtalo más tarde.",
  };

  function showToast(message) {
    if (!message) return;
    var now = Date.now();
    // Una misma respuesta puede llegar por cabecera y por HX-Trigger: se pinta
    // una sola vez.
    if (message === lastMessage && now - lastShownAt < DEDUPE_MS) return;
    lastMessage = message;
    lastShownAt = now;

    var box = document.getElementById("app_toast");
    var slot = document.getElementById("app_toast_message");
    if (!box || !slot) return;

    slot.textContent = message;
    box.classList.remove("opacity-0", "invisible", "pointer-events-none");
    box.classList.add("opacity-100");

    if (hideTimer) window.clearTimeout(hideTimer);
    hideTimer = window.setTimeout(function () {
      box.classList.remove("opacity-100");
      box.classList.add("opacity-0", "invisible", "pointer-events-none");
    }, HIDE_MS);
  }
  window.dbShowAppToast = showToast;

  function messageFromXhr(xhr) {
    if (!xhr) return "";
    var header = "";
    try {
      header = xhr.getResponseHeader("X-App-Error-Message") || "";
    } catch (e) {
      header = "";
    }
    if (header) return header;
    return DEFAULT_BY_STATUS[xhr.status] || "";
  }

  function bind() {
    // 4xx/5xx: htmx no hace swap, así que este es el único aviso que ve el
    // usuario.
    document.body.addEventListener("htmx:responseError", function (event) {
      var detail = event && event.detail ? event.detail : null;
      showToast(messageFromXhr(detail ? detail.xhr : null));
    });
    document.body.addEventListener("htmx:sendError", function () {
      showToast("No se ha podido contactar con el servidor.");
    });

    // Errores señalados con HX-Trigger sobre una respuesta 2xx. `appError`
    // lleva mensaje propio; `addError` es el evento heredado de
    // routes/food_routes.py, que hasta ahora no escuchaba nadie.
    document.body.addEventListener("appError", function (event) {
      var detail = event && event.detail ? event.detail : null;
      showToast((detail && detail.message) || DEFAULT_BY_STATUS[422]);
    });
    document.body.addEventListener("addError", function () {
      showToast("No se ha podido completar la operación.");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
