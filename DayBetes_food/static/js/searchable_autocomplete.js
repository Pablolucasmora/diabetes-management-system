// Searchable autocomplete inputs of the Food forms (brand, subtype, origin):
// suggestions as you type and the value kept while the form is open
// (components/food/food_widgets.py). Moved out of a Python string (audit H-11).
(function () {
  if (window.__dbSearchableAutocompleteBootstrapped) return;
  window.__dbSearchableAutocompleteBootstrapped = true;

  function normalize(v) { return String(v || "").trim(); }
  function storageKeyFor(input) {
    if (!input) return "";
    var form = input.form;
    var action = form && form.getAttribute ? (form.getAttribute("hx-post") || form.getAttribute("action") || "") : "";
    return "dbSearchableValue::" + window.location.pathname + window.location.search + "::" + (input.name || "") + "::" + action;
  }
  function persistValue(input) {
    if (!input || !window.localStorage) return;
    var key = storageKeyFor(input);
    if (!key) return;
    window.localStorage.setItem(key, String(input.value || ""));
  }
  function restoreValue(input) {
    if (!input || !window.localStorage) return;
    var key = storageKeyFor(input);
    if (!key) return;
    var saved = window.localStorage.getItem(key);
    if (saved == null) return;
    if (!normalize(input.value)) {
      input.value = saved;
    }
  }
  function escapeHtml(v) {
    return String(v || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function bindOne(root) {
    if (!root || root.dataset.searchableBound === "1") return;
    root.dataset.searchableBound = "1";

    var input = root.querySelector("[data-searchable-input='true']");
    var box = root.querySelector("[data-searchable-suggestions='true']");
    var addedFlag = root.querySelector("[data-searchable-added-flag='true']");
    if (!input || !box) return;
    // The open list has to rise above the cards below it, which
    // means raising its glass ancestors too (dropdown_layer.js).
    function raise(on) {
      if (window.dbRaiseDropdown) window.dbRaiseDropdown(root, on);
    }

    var options = [];
    try { options = JSON.parse(root.dataset.searchableOptions || "[]"); }
    catch (_) { options = []; }
    var allowAdd = root.dataset.searchableAllowAdd === "1";
    var caseMode = root.dataset.searchableCaseMode || "lower";
    restoreValue(input);

    function formatByCaseMode(v) {
      var text = normalize(v);
      if (!text) return "";
      if (caseMode === "title") {
        var words = text.toLowerCase().split(/\s+/);
        for (var i = 0; i < words.length; i += 1) {
          var w = words[i];
          if (!w) continue;
          words[i] = w.charAt(0).toUpperCase() + w.slice(1);
        }
        return words.join(" ");
      }
      return text.toLowerCase();
    }

    function closeBox() {
      box.style.display = "none";
      box.innerHTML = "";
      raise(false);
    }

    function setAddedFlag(value) {
      if (!addedFlag) return;
      addedFlag.value = value ? "1" : "0";
    }

    function similarityScore(nameLower, qLower) {
      if (!qLower) return 0;
      if (nameLower === qLower) return 1000;
      if (nameLower.indexOf(qLower) === 0) return 800;
      if (nameLower.indexOf(qLower) !== -1) return 600;

      var qSet = new Set(qLower.split(""));
      var nSet = new Set(nameLower.split(""));
      var inter = 0;
      qSet.forEach(function (ch) { if (nSet.has(ch)) inter += 1; });
      var union = new Set([].concat(Array.from(qSet), Array.from(nSet))).size || 1;
      return Math.floor((inter / union) * 300);
    }

    function render() {
      var q = normalize(input.value);
      var qLower = q.toLowerCase();
      var matches = [];

      for (var i = 0; i < options.length; i += 1) {
        var name = normalize(options[i]);
        if (!name) continue;
        var lower = name.toLowerCase();
        var score = similarityScore(lower, qLower);
        if (!q || score > 0) matches.push({ name: name, score: score });
      }

      matches.sort(function (a, b) {
        if (b.score !== a.score) return b.score - a.score;
        return a.name.localeCompare(b.name);
      });

      var rows = [];
      for (var j = 0; j < matches.length; j += 1) {
        var label = matches[j].name;
        var safe = escapeHtml(label);
        rows.push(
          "<li class='border-b border-gray-200'>" +
          "<button type='button' data-searchable-pick='" +
          safe +
          "' class='w-full text-left px-3 py-2 bg-white hover:bg-gray-200 text-sm text-gray-800 transition-colors'>" +
          safe +
          "</button></li>"
        );
      }

      var exactExists = options.some(function (x) {
        return normalize(x).toLowerCase() === qLower;
      });

      if (allowAdd && q && !exactExists) {
        rows.push(
          "<li class='border-b border-gray-200'>" +
          "<button type='button' data-searchable-add='true' class='w-full text-left px-3 py-2 bg-white hover:bg-gray-200 text-sm font-semibold text-gray-800 transition-colors'>Add: '" +
          escapeHtml(q) +
          "'</button></li>"
        );
      }

      if (rows.length) {
        box.innerHTML = (
          "<div data-searchable-scroll='true' class='p-0 max-h-44 overflow-y-auto' " +
          "style='-webkit-overflow-scrolling:touch;overscroll-behavior:contain;touch-action:pan-y;'>" +
          "<ul>" + rows.join("") + "</ul></div>"
        );
        var items = box.querySelectorAll("li");
        if (items.length > 0) items[items.length - 1].classList.remove("border-b", "border-gray-200");
        var scrollArea = box.querySelector("[data-searchable-scroll='true']");
        if (scrollArea) {
          scrollArea.addEventListener("wheel", function (ev) { ev.stopPropagation(); }, { passive: true });
          scrollArea.addEventListener("touchmove", function (ev) { ev.stopPropagation(); }, { passive: true });
        }
        raise(true);
      } else {
        box.innerHTML = "";
        raise(false);
      }
      box.style.display = rows.length ? "block" : "none";
    }

    box.addEventListener("click", function (ev) {
      var target = ev.target;
      if (!target) return;
      if (target.dataset && target.dataset.searchableAdd === "true") {
        var q = normalize(input.value);
        if (!q) return;
        var qLower = q.toLowerCase();
        var exists = options.some(function (x) { return normalize(x).toLowerCase() === qLower; });
        var formatted = formatByCaseMode(q);
        if (!exists) options.push(formatted);
        input.value = formatted;
        setAddedFlag(true);
        persistValue(input);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        input.dispatchEvent(new CustomEvent("db-searchable-commit", { bubbles: true }));
        setAddedFlag(true);
        closeBox();
        return;
      }
      var pick = target.dataset ? target.dataset.searchablePick : "";
      if (pick) {
        input.value = pick;
        setAddedFlag(false);
        persistValue(input);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        input.dispatchEvent(new CustomEvent("db-searchable-commit", { bubbles: true }));
        closeBox();
      }
    });

    input.addEventListener("focus", render);
    input.addEventListener("input", function () {
      setAddedFlag(false);
      persistValue(input);
      render();
    });
    input.addEventListener("change", function () { persistValue(input); });
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") closeBox();
    });
    document.addEventListener("click", function (ev) {
      var target = ev.target;
      if (!root.contains(target)) {
        closeBox();
        return;
      }
      if (target !== input && !box.contains(target)) {
        closeBox();
      }
    });
  }

  function bindAll() {
    var roots = document.querySelectorAll("[data-searchable-autocomplete='true']");
    for (var i = 0; i < roots.length; i += 1) bindOne(roots[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindAll);
  } else {
    bindAll();
  }
  document.body.addEventListener("htmx:afterSwap", bindAll);
})();
