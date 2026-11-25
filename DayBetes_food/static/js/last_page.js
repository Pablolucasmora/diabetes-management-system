// The installed app reopens the page it was left on (frontend_conventions.md §11).
// A phone closes an app in the background whenever it wants, and it then starts at
// the menu: within 30 minutes, the page that was showing opens over the menu, so Back
// goes to the menu. Only the address of a plain page is kept, in this phone, never
// what is typed; the login page, which logging out leads to, forgets it.
(function () {
  if (window.__dbLastPage) return;
  window.__dbLastPage = true;

  var KEY = "dbLastPage";
  var STARTED = "dbAppStarted";
  var MAX_AGE_MS = 30 * 60 * 1000;
  // Neither forms nor the scanner. The query is kept only where it is the view and
  // never a typed search (§5).
  var PAGES = /^\/(cart|stats|food|assistant|settings|settings\/(guide|tags|injections|meal_type_schedule|insulin(\/pens|\/brands)?)|food\/item\/(catalog|manual_intake|recipe)\/\d+)$/;
  var WITH_QUERY = { "/food": true, "/assistant": true };

  // Storage can be missing or blocked: then the app just starts at the menu.
  function attempt(work) {
    try { return work(); } catch (_) { return null; }
  }

  if (window.location.pathname.indexOf("/auth/") === 0) {
    attempt(function () { window.localStorage.removeItem(KEY); });
    return;
  }

  function installed() {
    return window.navigator.standalone === true || window.matchMedia("(display-mode: standalone)").matches;
  }
  if (!installed()) return;

  function save() {
    var path = window.location.pathname;
    attempt(function () {
      if (!PAGES.test(path)) {
        window.localStorage.removeItem(KEY);
        return;
      }
      var url = path + (WITH_QUERY[path] ? window.location.search : "");
      window.localStorage.setItem(KEY, JSON.stringify({ url: url, at: Date.now() }));
    });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") save();
  });
  window.addEventListener("pagehide", save);

  // sessionStorage is empty only when the app has just been opened.
  function reopen() {
    var started = attempt(function () { return window.sessionStorage.getItem(STARTED); });
    attempt(function () { window.sessionStorage.setItem(STARTED, "1"); });
    if (started || window.location.pathname !== "/menu" || !window.htmx) return;
    var last = attempt(function () { return JSON.parse(window.localStorage.getItem(KEY)); });
    if (!last || typeof last.url !== "string" || !PAGES.test(last.url.split("?")[0])) return;
    if (!(Date.now() - last.at < MAX_AGE_MS)) return;
    var link = document.createElement("a");
    link.hidden = true;
    link.setAttribute("hx-get", last.url);
    link.setAttribute("hx-target", "#main_content");
    link.setAttribute("hx-push-url", "true");
    document.body.appendChild(link);
    window.htmx.process(link);
    link.click();
    link.remove();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", reopen);
  } else {
    reopen();
  }
})();
