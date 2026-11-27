// Pages of the island kept in the tab's memory (frontend_conventions.md §12),
// so a swipe (swipe_nav.js, §13) never waits for the network.
//
// - Kept 60 s, and never past a save: each page keeps the data version it was
//   asked with (preload.js), and one under an older version is never used.
// - Asked for as htmx asks, marked as a preload: a pure read, and DiaBot
//   leaves its turns unseen until the page is shown (code_conventions §9.2).
// - An island page that arrives through htmx is kept too.
// - `show` draws a kept page as htmx draws a response: the page left saved for
//   Back, a new history entry, the swap and the same events the rest of the
//   web listens to. `restore` draws the page Back goes to.
(function () {
  if (window.dbPageCache) return;

  var KEPT_MS = 60000;
  var ISLAND_PATHS = ["/menu", "/stats", "/assistant", "/food", "/settings"];

  var pages = {};
  var loading = {};

  function dataVersion() {
    return typeof window.dbDataVersion === "function" ? window.dbDataVersion() : 0;
  }

  function get(url) {
    var page = pages[url];
    if (!page) return null;
    if (page.version !== dataVersion() || Date.now() - page.at > KEPT_MS) {
      delete pages[url];
      return null;
    }
    return page.html;
  }

  function keep(url, html, version) {
    if (version !== dataVersion()) return;
    pages[url] = { html: html, version: version, at: Date.now() };
  }

  // The page's HTML, from memory or asked for now; null when it cannot be
  // had (an error, a redirect to log in, a save meanwhile).
  function load(url) {
    var kept = get(url);
    if (kept !== null) return Promise.resolve(kept);
    if (loading[url]) return loading[url];
    var version = dataVersion();
    loading[url] = fetch(url, {
      credentials: "same-origin",
      headers: {
        "HX-Request": "true",
        "HX-Preloaded": "true",
        "HX-Current-URL": window.location.href,
        "X-Data-Version": String(version),
      },
    })
      .then(function (response) {
        var usable = response.status === 200 && !response.redirected &&
          !response.headers.get("HX-Redirect") && !response.headers.get("HX-Location");
        return usable ? response.text() : null;
      })
      .then(function (html) {
        if (html === null || version !== dataVersion()) return null;
        keep(url, html, version);
        return html;
      })
      .catch(function () { return null; })
      .then(function (html) {
        delete loading[url];
        return html;
      });
    return loading[url];
  }

  function swapIn(main, url, html) {
    // Settled at once: whatever the page does on load (DiaBot going to its
    // last turn) happens before the next frame.
    window.htmx.swap(
      main,
      html,
      { swapStyle: "innerHTML", swapDelay: 0, settleDelay: 0 },
      { contextElement: main, eventInfo: { target: main, elt: main, pathInfo: { requestPath: url } } }
    );
  }

  function canSwap(main) {
    return !!(main && window.htmx && typeof window.htmx.swap === "function" && window.dbHistory);
  }

  // As htmx goes to a page: the page left is saved for Back, a new history
  // entry, htmx told which page is current, then the swap.
  function show(url, html) {
    var main = document.getElementById("main_content");
    if (!canSwap(main)) return false;
    window.dbHistory.saveCurrent();
    window.history.pushState({ htmx: true }, "", url);
    window.htmx.trigger(document.body, "htmx:pushedIntoHistory", { path: url });
    window.dbHistory.setCurrent(url);
    swapIn(main, url, html);
    keep(url, html, dataVersion());
    return true;
  }

  // As htmx brings a page back with Back: the history entry is already there
  // (popstate, or the replaced one of dbBack), so only the swap.
  function restore(url, html) {
    var main = document.getElementById("main_content");
    if (!canSwap(main)) return false;
    window.dbHistory.setCurrent(url);
    swapIn(main, url, html);
    window.htmx.trigger(document.body, "htmx:historyRestore", { path: url });
    return true;
  }

  function keepArrived(event) {
    var detail = event.detail || {};
    var config = detail.requestConfig || {};
    if (!detail.target || detail.target.id !== "main_content") return;
    if (!detail.xhr || detail.xhr.status !== 200 || String(config.verb).toLowerCase() !== "get") return;
    if (ISLAND_PATHS.indexOf(config.path) < 0 || typeof detail.serverResponse !== "string") return;
    keep(config.path, detail.serverResponse, dataVersion());
  }

  document.addEventListener("htmx:beforeSwap", keepArrived);

  window.dbPageCache = { get: get, load: load, show: show, restore: restore };
})();
