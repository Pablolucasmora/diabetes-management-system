(function () {
  var CSRF_COOKIE_NAME = (function () {
    var meta = document.querySelector('meta[name="csrf-cookie-name"]');
    return (meta && meta.content) || "daybetes_csrf";
  })();

  function getCookie(name) {
    var prefix = name + "=";
    var cookies = document.cookie ? document.cookie.split(";") : [];
    for (var i = 0; i < cookies.length; i += 1) {
      var cookie = cookies[i].trim();
      if (cookie.indexOf(prefix) === 0) return decodeURIComponent(cookie.slice(prefix.length));
    }
    return "";
  }

  function ensureFormToken(form, token) {
    if (!form || !token) return;
    var input = form.querySelector("input[name='csrf_token']");
    if (!input) {
      input = document.createElement("input");
      input.type = "hidden";
      input.name = "csrf_token";
      form.appendChild(input);
    }
    input.value = token;
  }

  function syncAllForms() {
    var token = getCookie(CSRF_COOKIE_NAME);
    if (!token) return;
    var forms = document.querySelectorAll("form");
    for (var i = 0; i < forms.length; i += 1) {
      ensureFormToken(forms[i], token);
    }
  }

  document.body.addEventListener("htmx:configRequest", function (event) {
    var token = getCookie(CSRF_COOKIE_NAME);
    if (!token || !event || !event.detail || !event.detail.headers) return;
    event.detail.headers["X-CSRF-Token"] = token;
  });

  document.addEventListener("submit", function (event) {
    syncAllForms();
  }, true);

  document.body.addEventListener("htmx:afterSwap", function () {
    syncAllForms();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncAllForms);
  } else {
    syncAllForms();
  }
})();
