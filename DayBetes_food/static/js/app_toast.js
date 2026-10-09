(function () {
  // Single channel for the web's error notices (decision 2026-09-10, finding
  // 37 of audit/audit_intake_event.md).
  //
  // HTMX routes keep their semantic status and return an empty body; the
  // public message travels in headers (`X-App-Error-Message`) and, when the
  // response is 2xx, in the `appError` event of `HX-Trigger`. It is painted
  // here over #app_toast, defined once in the layout (components/ui.py).
  if (window.__dbAppToastBootstrapped) return;
  window.__dbAppToastBootstrapped = true;

  var HIDE_MS = 4000;
  var DEDUPE_MS = 300;
  var hideTimer = null;
  var lastMessage = "";
  var lastShownAt = 0;

  // Default message per status, for the responses that do not declare their
  // own yet (for example the 403 for "missing HX-Request header").
  var DEFAULT_BY_STATUS = {
    400: "The request is not well formed.",
    401: "You need to log in.",
    403: "You are not allowed to perform this action.",
    404: "The resource does not exist or is not available.",
    409: "The action conflicts with the current state.",
    422: "The submitted data is not valid.",
    429: "Too many requests. Please try again later.",
  };

  function showToast(message) {
    if (!message) return;
    var now = Date.now();
    // The same response can arrive through a header and through HX-Trigger:
    // it is painted only once.
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
    // 4xx/5xx: htmx does not swap, so this is the only notice the user
    // sees.
    document.body.addEventListener("htmx:responseError", function (event) {
      var detail = event && event.detail ? event.detail : null;
      showToast(messageFromXhr(detail ? detail.xhr : null));
    });
    document.body.addEventListener("htmx:sendError", function () {
      showToast("Could not reach the server.");
    });

    // Errors signalled with HX-Trigger on a 2xx response. `appError` carries
    // its own message; `addError` is the legacy event from
    // routes/food_routes.py, which nobody listened to until now.
    document.body.addEventListener("appError", function (event) {
      var detail = event && event.detail ? event.detail : null;
      showToast((detail && detail.message) || DEFAULT_BY_STATUS[422]);
    });
    document.body.addEventListener("addError", function () {
      showToast("The action could not be completed.");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
