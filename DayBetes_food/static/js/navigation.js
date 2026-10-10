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
// the pages ahead.
(function () {
  if (window.__dbNavigation) return;
  window.__dbNavigation = true;

  function currentDepth() {
    var state = window.history.state;
    return state && typeof state.dbDepth === "number" ? state.dbDepth : 0;
  }

  var depth = currentDepth();

  function markDepth(value) {
    depth = value;
    var state = Object.assign({}, window.history.state || {}, { dbDepth: value });
    window.history.replaceState(state, "", window.location.href);
  }

  document.addEventListener("htmx:pushedIntoHistory", function () {
    markDepth(depth + 1);
  });

  window.addEventListener("popstate", function (event) {
    depth = event.state && typeof event.state.dbDepth === "number" ? event.state.dbDepth : 0;
  });

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
    window.htmx.ajax("GET", target, { target: "#main_content", swap: "innerHTML" });
  };
})();
