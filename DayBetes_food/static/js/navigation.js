// One rule for every "Back" button of the web (frontend_conventions.md §5).
//
// Back means "the page I came from", so it goes back in the history: it never
// opens a page as a new entry, which is what made two pages bounce into each
// other (edit -> Back -> detail -> Back -> edit). When there is no page of the
// web behind (the page was opened directly, or after a full reload such as a
// redirect after saving), it opens the page's parent instead, replacing the
// current entry so that it cannot be come back to.
//
// Each history entry pushed by htmx records how many pages of the web are
// behind it (`dbDepth`), because history.length also counts other sites and
// the pages ahead, and which page it came from (`dbPrev`), so a swipe Back can
// show that page before going there (swipe_nav.js, §13).
//
// `window.dbHistory` keeps htmx's own history right when a page changes
// without htmx (a swipe, §13): the page left is saved as htmx would save it,
// and htmx is told which page is now the current one. It reads and writes
// htmx's sessionStorage keys, so it follows the vendored htmx 2.0.7: check it
// when htmx is updated.
(function () {
  if (window.__dbNavigation) return;
  window.__dbNavigation = true;

  var CACHE_KEY = "htmx-history-cache";
  var PATH_KEY = "htmx-current-path-for-history";

  function here() {
    return window.location.pathname + window.location.search;
  }

  function currentDepth() {
    var state = window.history.state;
    return state && typeof state.dbDepth === "number" ? state.dbDepth : 0;
  }

  var depth = currentDepth();
  var current = here();

  function mark(values) {
    var state = Object.assign({}, window.history.state || {}, values);
    window.history.replaceState(state, "", window.location.href);
  }

  document.addEventListener("htmx:pushedIntoHistory", function () {
    depth += 1;
    mark({ dbDepth: depth, dbPrev: current });
    current = here();
  });

  // HX-Replace-Url swaps the state for htmx's own: the entry keeps its depth
  // and where it came from.
  document.addEventListener("htmx:replacedInHistory", function (event) {
    var state = window.history.state || {};
    mark({ dbDepth: depth, dbPrev: state.dbPrev || null });
    current = here();
  });

  window.addEventListener("popstate", function (event) {
    depth = event.state && typeof event.state.dbDepth === "number" ? event.state.dbDepth : 0;
    current = here();
  });

  // ---- htmx's history, for page changes made without htmx ----

  function storage() {
    try {
      return window.sessionStorage;
    } catch (error) {
      return null;
    }
  }

  // The form htmx gives a URL as a key of its cache.
  function normalize(url) {
    var parsed = new URL(url, window.location.origin);
    var path = parsed.pathname + parsed.search;
    return path === "/" ? path : path.replace(/\/+$/, "");
  }

  function readCache(store) {
    try {
      return JSON.parse(store.getItem(CACHE_KEY) || "[]") || [];
    } catch (error) {
      return [];
    }
  }

  // The page on screen, saved as htmx saves it before leaving a page: its
  // content and where it was scrolled to, so Back brings it back as it was.
  // Not a page that asks not to be kept (hx-history="false").
  function saveCurrent() {
    var store = storage();
    mark({ htmx: true });
    if (!store || !window.htmx) return;
    if (document.querySelector('[hx-history="false" i],[data-hx-history="false" i]')) return;
    var size = window.htmx.config.historyCacheSize;
    if (size <= 0) {
      store.removeItem(CACHE_KEY);
      return;
    }
    var element = document.querySelector("[hx-history-elt],[data-hx-history-elt]") || document.body;
    var copy = element.cloneNode(true);
    copy.querySelectorAll("." + window.htmx.config.requestClass).forEach(function (node) {
      node.classList.remove(window.htmx.config.requestClass);
    });
    copy.querySelectorAll("[data-disabled-by-htmx]").forEach(function (node) {
      node.removeAttribute("disabled");
    });
    var url = normalize(store.getItem(PATH_KEY) || here());
    var cache = readCache(store).filter(function (item) { return item.url !== url; });
    cache.push({ url: url, content: copy.innerHTML, title: document.title, scroll: window.scrollY });
    while (cache.length > size) cache.shift();
    while (cache.length > 0) {
      try {
        store.setItem(CACHE_KEY, JSON.stringify(cache));
        break;
      } catch (error) {
        cache.shift();
      }
    }
  }

  // htmx saves the page on screen under the path it was told about last.
  function setCurrent(url) {
    var store = storage();
    if (store) store.setItem(PATH_KEY, url);
    current = here();
  }

  // What htmx would bring back for that URL (content and scroll), or null.
  function snapshot(url) {
    var store = storage();
    if (!store) return null;
    var key = normalize(url);
    var cache = readCache(store);
    for (var i = 0; i < cache.length; i += 1) {
      if (cache[i].url === key) return cache[i];
    }
    return null;
  }

  // Where Back goes from here: the page this entry came from, or the parent
  // given to the Back button when there is no page of the web behind.
  function backTarget(fallbackUrl) {
    var state = window.history.state || {};
    if (currentDepth() > 0) return state.dbPrev ? { url: state.dbPrev, inHistory: true } : null;
    return { url: fallbackUrl || "/menu", inHistory: false };
  }

  window.dbHistory = {
    saveCurrent: saveCurrent,
    setCurrent: setCurrent,
    snapshot: snapshot,
    backTarget: backTarget,
  };

  window.dbBack = function (fallbackUrl) {
    window.scrollTo({ top: 0, behavior: "auto" });
    if (currentDepth() > 0) {
      window.history.back();
      return;
    }
    var target = fallbackUrl || "/menu";
    if (!window.htmx) {
      window.location.replace(target);
      return;
    }
    // The URL changes first: what reacts to the swap (the nav island) reads it.
    window.history.replaceState({ htmx: true, dbDepth: 0 }, "", target);
    depth = 0;
    setCurrent(target);
    window.htmx.ajax("GET", target, { target: "#main_content", swap: "innerHTML" });
  };
})();
