// Keeps an open suggestion list above the cards that come after it
// (frontend_conventions.md §8).
//
// Every glass card (backdrop-filter) is its own stacking context, so the
// z-index of a list inside it only counts within that card: the next card
// is painted on top. While a list is open, every ancestor that creates a
// stacking context is raised too. Ancestors that already have their own
// z-index (sticky headers, the nav) are left alone. A counter per ancestor
// lets two fields share a card: closing one does not lower the other.
(function () {
  var RAISED_Z = "30"; // under the loading overlay (40) and the nav (50)

  function createsLayer(style) {
    var backdrop = style.backdropFilter || style.webkitBackdropFilter || "none";
    return (
      backdrop !== "none" ||
      style.filter !== "none" ||
      style.transform !== "none" ||
      style.isolation === "isolate" ||
      parseFloat(style.opacity) < 1
    );
  }

  function raise(el) {
    var count = el.__dbRaiseCount || 0;
    if (count === 0) {
      el.__dbRaiseSaved = { z: el.style.zIndex, position: el.style.position };
      if (getComputedStyle(el).position === "static") el.style.position = "relative";
      el.style.zIndex = RAISED_Z;
    }
    el.__dbRaiseCount = count + 1;
  }

  function lower(el) {
    el.__dbRaiseCount = (el.__dbRaiseCount || 1) - 1;
    if (el.__dbRaiseCount > 0) return;
    var saved = el.__dbRaiseSaved || { z: "", position: "" };
    el.style.zIndex = saved.z;
    el.style.position = saved.position;
  }

  window.dbRaiseDropdown = function (root, on) {
    if (!root) return;
    if (on) {
      if (root.__dbRaised) return;
      var raised = [];
      root.style.zIndex = "80";
      for (var el = root.parentElement; el && el !== document.body; el = el.parentElement) {
        var style = getComputedStyle(el);
        if (!createsLayer(style)) continue;
        if (!el.__dbRaiseCount && style.zIndex !== "auto") continue;
        raise(el);
        raised.push(el);
      }
      root.__dbRaised = raised;
      return;
    }
    if (!root.__dbRaised) return;
    root.style.zIndex = "";
    root.__dbRaised.forEach(lower);
    root.__dbRaised = null;
  };
})();
