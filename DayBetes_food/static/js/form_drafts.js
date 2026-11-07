// Drafts of the forms with `data-draft-key` (frontend_conventions.md §7.14, §9.1):
// what is typed is kept in this browser and comes back after a reload, until the
// form is saved. Presentation only: the server never reads it.
(function () {
  if (window.__dbFormDraftsBootstrapped) return;
  window.__dbFormDraftsBootstrapped = true;

  function byName(form, name) {
    var all = form.querySelectorAll("input[name], select[name], textarea[name]");
    var result = [];
    for (var i = 0; i < all.length; i += 1) {
      if (all[i].name === name) result.push(all[i]);
    }
    return result;
  }

  function saveForm(form) {
    var key = form.getAttribute("data-draft-key");
    if (!key || !window.localStorage) return;
    var fields = form.querySelectorAll("input[name], select[name], textarea[name]");
    var payload = {};
    for (var i = 0; i < fields.length; i += 1) {
      var el = fields[i];
      if (!el || el.disabled) continue;
      var type = (el.type || "").toLowerCase();
      if (type === "submit" || type === "button" || type === "reset" || type === "file" || type === "image") continue;
      var name = el.name;
      // The CSRF token is the session's, never part of a draft (csrf.js adds it).
      if (!name || name === "csrf_token") continue;
      if (type === "checkbox" && byName(form, name).length > 1) {
        // Several boxes with one name: the values that are on.
        if (!Array.isArray(payload[name])) payload[name] = [];
        if (el.checked) payload[name].push(el.value);
      } else if (type === "checkbox") {
        payload[name] = !!el.checked;
      } else if (type === "radio") {
        if (el.checked) payload[name] = el.value;
      } else {
        payload[name] = el.value;
      }
    }
    try {
      window.localStorage.setItem(key, JSON.stringify(payload));
    } catch (_) {}
  }

  function restoreForm(form) {
    var key = form.getAttribute("data-draft-key");
    if (!key || !window.localStorage) return;
    var raw = null;
    try { raw = window.localStorage.getItem(key); } catch (_) {}
    if (!raw) return;
    var data = null;
    try { data = JSON.parse(raw); } catch (_) { return; }
    if (!data || typeof data !== "object") return;

    var names = Object.keys(data);
    for (var i = 0; i < names.length; i += 1) {
      var name = names[i];
      var value = data[name];
      var fields = byName(form, name);
      for (var j = 0; j < fields.length; j += 1) {
        var el = fields[j];
        if (!el || el.disabled) continue;
        var type = (el.type || "").toLowerCase();
        if (type === "checkbox" && Array.isArray(value)) {
          if (!el.checked) el.checked = value.indexOf(el.value) !== -1;
        } else if (type === "checkbox") {
          el.checked = !!value;
        } else if (type === "radio") {
          if (!el.checked) el.checked = String(el.value) === String(value);
        } else if (value != null) {
          if (!String(el.value || "").trim()) {
            el.value = String(value);
          }
        }
      }
    }
  }

  function bindForm(form) {
    if (!form || form.dataset.draftBound === "1") return;
    form.dataset.draftBound = "1";
    restoreForm(form);
    form.addEventListener("focusout", function () { saveForm(form); });
    form.addEventListener("change", function () { saveForm(form); });
    form.addEventListener("input", function () { saveForm(form); });
    form.addEventListener("submit", function () { saveForm(form); });
    // Saved: the draft is done, or it would fill a field emptied on purpose
    // the next time the form opens. A validation error keeps it. Success is a
    // redirect or, for a form that stays on the page (the cart), the event its
    // route sends, named in `data-draft-done-event`.
    form.addEventListener("htmx:beforeOnLoad", function (event) {
      var xhr = event && event.detail ? event.detail.xhr : null;
      if (!xhr || xhr.status >= 400) return;
      var doneEvent = form.getAttribute("data-draft-done-event");
      var trigger = xhr.getResponseHeader("HX-Trigger") || "";
      var done = !!xhr.getResponseHeader("HX-Redirect") || (!!doneEvent && trigger.indexOf(doneEvent) !== -1);
      if (!done) return;
      try { window.localStorage.removeItem(form.getAttribute("data-draft-key")); } catch (_) {}
    });
  }

  function bindAll(scope) {
    var root = scope || document;
    var forms = root.querySelectorAll("form[data-draft-key]");
    for (var i = 0; i < forms.length; i += 1) bindForm(forms[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { bindAll(document); });
  } else {
    bindAll(document);
  }
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event && event.detail ? event.detail.target : null;
    bindAll(target || document);
  });
})();
