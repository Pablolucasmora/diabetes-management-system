// Assistant composer (frontend_conventions.md §9.11). Presentation only: the
// server returns the `/` suggestions and, when sending exists, re-reads every
// mentioned entry with its visibility rule (code_conventions.md §8.12).
//
// Typing `/` at the start or after a space or line break opens the
// suggestions above the composer; the text after it filters them. ↑ ↓ move,
// Tab or Enter pick, Esc closes, a tap picks. A picked entry replaces
// `/query` with `/Name ` and becomes a pill above the text box. Mentions
// travel as entry_type + entry_id in the hidden `mentions` field.
// Nothing is stored in localStorage and no field takes the focus on its own.
(function () {
  if (window.__dbAssistantBootstrapped) return;
  window.__dbAssistantBootstrapped = true;

  var DEBOUNCE_MS = 150;
  var MAX_QUERY_LENGTH = 80;
  var TEXTAREA_MAX_PX = 160;

  var mentions = []; // [{type, id, name}]
  var activeSlash = -1; // index of the `/` whose suggestions are open
  var dismissedSlash = -1; // a `/` closed with Esc or with no results
  var lastQuery = null;
  var timer = null;

  function byId(id) {
    return document.getElementById(id);
  }
  function input() {
    return byId("assistant_input");
  }
  function popup() {
    return byId("assistant_mentions_popup");
  }
  function list() {
    return byId("assistant_mentions");
  }
  function options() {
    var el = list();
    return el ? Array.prototype.slice.call(el.querySelectorAll("[role='option']")) : [];
  }
  function isOpen() {
    var p = popup();
    return !!p && !p.hidden;
  }

  // ---- Query under the caret ----

  // The `/` that starts a mention already picked is not a query.
  function startsPickedMention(text, slash) {
    return mentions.some(function (m) {
      return text.substr(slash + 1, m.name.length) === m.name;
    });
  }

  // {slash, query} for the `/` before the caret, or null.
  function queryAtCaret() {
    var el = input();
    if (!el || el.selectionStart !== el.selectionEnd) return null;
    var text = el.value;
    var caret = el.selectionStart;
    var slash = text.lastIndexOf("/", caret - 1);
    if (slash < 0) return null;
    var before = slash === 0 ? "" : text.charAt(slash - 1);
    if (slash > 0 && !/\s/.test(before)) return null;
    var query = text.slice(slash + 1, caret);
    if (query.indexOf("\n") >= 0 || query.length > MAX_QUERY_LENGTH) return null;
    if (startsPickedMention(text, slash)) return null;
    return { slash: slash, query: query };
  }

  // ---- Popup ----

  function open(slash) {
    var p = popup();
    if (!p) return;
    activeSlash = slash;
    p.hidden = false;
  }

  function close() {
    var p = popup();
    if (p) p.hidden = true;
    activeSlash = -1;
    lastQuery = null;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function fetchSuggestions(query) {
    if (query === lastQuery || !window.htmx) return;
    lastQuery = query;
    // The list carries hx-sync="this:replace": a newer request aborts the
    // previous one, so a late answer never paints over a newer query.
    window.htmx.ajax("GET", "/assistant/mentions?q=" + encodeURIComponent(query), {
      source: list(),
      target: "#assistant_mentions",
      swap: "innerHTML",
    });
  }

  function refresh() {
    var found = queryAtCaret();
    if (!found || found.slash === dismissedSlash) {
      if (isOpen()) close();
      return;
    }
    if (!isOpen()) open(found.slash);
    activeSlash = found.slash;
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () {
      timer = null;
      fetchSuggestions(found.query);
    }, DEBOUNCE_MS);
  }

  function selectedIndex() {
    var opts = options();
    for (var i = 0; i < opts.length; i += 1) {
      if (opts[i].getAttribute("aria-selected") === "true") return i;
    }
    return -1;
  }

  function select(index) {
    var opts = options();
    if (!opts.length) return;
    var next = (index + opts.length) % opts.length;
    opts.forEach(function (opt, i) {
      opt.setAttribute("aria-selected", i === next ? "true" : "false");
    });
    opts[next].scrollIntoView({ block: "nearest" });
    var el = input();
    if (el) el.setAttribute("aria-activedescendant", opts[next].id);
  }

  // ---- Mentions ----

  function syncHidden() {
    var hidden = byId("assistant_mentions_value");
    if (hidden) {
      hidden.value = JSON.stringify(
        mentions.map(function (m) {
          return { entry_type: m.type, entry_id: m.id };
        })
      );
    }
  }

  function renderChips() {
    var box = byId("assistant_mention_chips");
    if (!box) return;
    box.textContent = "";
    mentions.forEach(function (m, i) {
      var chip = document.createElement("span");
      chip.className =
        "inline-flex items-center gap-1 rounded-full bg-control border border-line pl-2.5 pr-1 py-0.5 text-xs text-gray-800 max-w-full";
      var label = document.createElement("span");
      label.className = "truncate";
      label.textContent = m.name;
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "shrink-0 h-5 w-5 rounded-full text-gray-500 hover:bg-line-soft cursor-pointer";
      remove.setAttribute("aria-label", "Remove " + m.name);
      remove.setAttribute("data-assistant-remove-mention", String(i));
      remove.textContent = "×";
      chip.appendChild(label);
      chip.appendChild(remove);
      box.appendChild(chip);
    });
    syncHidden();
  }

  function autoGrow() {
    var el = input();
    if (!el) return;
    el.style.height = "auto";
    // scrollHeight leaves out the border, which border-box sizing counts.
    var border = el.offsetHeight - el.clientHeight;
    el.style.height = Math.min(el.scrollHeight + border, TEXTAREA_MAX_PX) + "px";
  }

  function pick(option) {
    var el = input();
    if (!el || !option || activeSlash < 0) return;
    var name = option.getAttribute("data-mention-name") || "";
    var type = option.getAttribute("data-mention-type");
    var id = parseInt(option.getAttribute("data-mention-id"), 10);
    if (!name || !type || !id) return;
    var caret = el.selectionStart;
    var text = el.value;
    var inserted = "/" + name + " ";
    el.value = text.slice(0, activeSlash) + inserted + text.slice(caret);
    var position = activeSlash + inserted.length;
    el.setSelectionRange(position, position);
    var exists = mentions.some(function (m) {
      return m.type === type && m.id === id;
    });
    if (!exists) mentions.push({ type: type, id: id, name: name });
    close();
    renderChips();
    autoGrow();
  }

  // Deleting a `/Name` from the text drops its mention.
  function dropMissingMentions() {
    var el = input();
    if (!el) return;
    var before = mentions.length;
    mentions = mentions.filter(function (m) {
      return el.value.indexOf("/" + m.name) >= 0;
    });
    if (mentions.length !== before) renderChips();
  }

  function removeMention(index) {
    var m = mentions[index];
    var el = input();
    if (!m || !el) return;
    var token = "/" + m.name;
    var at = el.value.indexOf(token);
    if (at >= 0) {
      var end = at + token.length;
      if (el.value.charAt(end) === " ") end += 1;
      el.value = el.value.slice(0, at) + el.value.slice(end);
    }
    mentions.splice(index, 1);
    renderChips();
    autoGrow();
  }

  // ---- Events ----

  document.addEventListener("input", function (event) {
    if (event.target !== input()) return;
    // A `/` that was dismissed stops counting once it is deleted.
    var el = input();
    if (dismissedSlash >= 0 && el.value.charAt(dismissedSlash) !== "/") dismissedSlash = -1;
    dropMissingMentions();
    autoGrow();
    refresh();
  });

  document.addEventListener("keydown", function (event) {
    if (event.target !== input() || !isOpen()) return;
    var opts = options();
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!opts.length) return;
      event.preventDefault();
      select(selectedIndex() + (event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Tab" || event.key === "Enter") {
      if (!opts.length) return;
      event.preventDefault();
      pick(opts[Math.max(0, selectedIndex())]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      dismissedSlash = activeSlash;
      close();
    }
  });

  // Moving the caret out of the query (arrows, a tap elsewhere) closes it.
  document.addEventListener("selectionchange", function () {
    if (document.activeElement === input()) refresh();
  });

  document.addEventListener("click", function (event) {
    var option = event.target.closest && event.target.closest("#assistant_mentions [role='option']");
    if (option) {
      event.preventDefault();
      pick(option);
      var el = input();
      if (el) el.focus();
      return;
    }
    var remove = event.target.closest && event.target.closest("[data-assistant-remove-mention]");
    if (remove) {
      removeMention(parseInt(remove.getAttribute("data-assistant-remove-mention"), 10));
      return;
    }
    // A tap outside the composer closes the suggestions.
    if (isOpen() && !(event.target.closest && event.target.closest("#assistant_composer"))) close();
  });

  // Keep the focus in the text box when a row is pressed, so the phone
  // keyboard does not close and reopen.
  document.addEventListener("mousedown", function (event) {
    if (event.target.closest && event.target.closest("#assistant_mentions [role='option']")) event.preventDefault();
  });

  // After a query with a space stops matching, the `/` stays as plain text.
  document.addEventListener("htmx:afterSwap", function (event) {
    if (!event.detail || event.detail.target !== list()) return;
    var empty = !!list().querySelector("[data-mentions-empty='true']");
    var found = queryAtCaret();
    if (empty && found && /\s/.test(found.query)) {
      dismissedSlash = found.slash;
      close();
      return;
    }
    var el = input();
    var first = options()[0];
    if (el) {
      if (first) el.setAttribute("aria-activedescendant", first.id);
      else el.removeAttribute("aria-activedescendant");
    }
  });

  document.addEventListener("DOMContentLoaded", autoGrow);

  // A new page of the assistant starts with no mentions.
  document.addEventListener("htmx:load", function (event) {
    if (event.detail && event.detail.elt && event.detail.elt.querySelector && event.detail.elt.querySelector("#assistant_input")) {
      mentions = [];
      activeSlash = -1;
      dismissedSlash = -1;
      lastQuery = null;
      autoGrow();
    }
  });
})();
