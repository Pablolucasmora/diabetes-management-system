// Search of the guide page (frontend_conventions.md §9.12). It filters in the
// page: a value matches by its name, its meaning or the title of its topic.
// The contents list, under each topic, the values that match; with a single
// result the contents hide and the result keeps the title of its topic.
(function () {
  if (window.__dbGuideBootstrapped) return;
  window.__dbGuideBootstrapped = true;

  function normalize(text) {
    return String(text || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .trim();
  }

  function scrollTo(id) {
    var el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function matchLink(value, topicTitle) {
    var li = document.createElement("li");
    var button = document.createElement("button");
    button.type = "button";
    button.className = "text-left text-xs text-gray-600 hover:text-ink cursor-pointer";
    var label = value.querySelector("[data-guide-label]");
    button.textContent = label ? label.textContent : topicTitle;
    button.addEventListener("click", function () { scrollTo(value.id); });
    li.appendChild(button);
    return li;
  }

  function apply(page, query) {
    var words = normalize(query).split(/\s+/).filter(Boolean);
    var sections = page.querySelectorAll("[data-guide-topic]");
    var total = 0;
    var topicsWithResults = [];

    sections.forEach(function (section) {
      var title = section.getAttribute("data-guide-title") || "";
      var titleText = normalize(title);
      var matched = [];
      section.querySelectorAll("[data-guide-value]").forEach(function (value) {
        var text = titleText + " " + normalize(value.textContent);
        var hit = words.every(function (word) { return text.indexOf(word) !== -1; });
        value.hidden = words.length > 0 && !hit;
        if (words.length && hit) matched.push(value);
      });
      section.hidden = words.length > 0 && matched.length === 0;
      if (matched.length) topicsWithResults.push(section.getAttribute("data-guide-topic"));
      total += matched.length;

      var entry = page.querySelector('[data-guide-entry="' + section.getAttribute("data-guide-topic") + '"]');
      if (!entry) return;
      entry.hidden = words.length > 0 && matched.length === 0;
      var count = entry.querySelector("[data-guide-count]");
      var all = section.querySelectorAll("[data-guide-value]").length;
      if (count) count.textContent = String(words.length ? matched.length : all);
      var list = entry.querySelector("[data-guide-matches]");
      if (!list) return;
      list.textContent = "";
      matched.forEach(function (value) { list.appendChild(matchLink(value, title)); });
      list.classList.toggle("hidden", !matched.length);
      list.classList.toggle("flex", matched.length > 0);
    });

    var single = words.length > 0 && total === 1;
    var contents = document.getElementById("guide_contents");
    if (contents) contents.hidden = single || (words.length > 0 && total === 0);
    page.querySelectorAll("[data-guide-to-contents]").forEach(function (button) {
      button.hidden = single || (words.length > 0 && total === 0);
    });
    var empty = document.getElementById("guide_empty");
    if (empty) empty.hidden = !(words.length > 0 && total === 0);

    var status = document.getElementById("guide_status");
    if (status) {
      if (!words.length) status.textContent = "";
      else if (!total) status.textContent = "No results";
      else if (single) {
        var section = page.querySelector('[data-guide-topic="' + topicsWithResults[0] + '"]');
        status.textContent = "1 result in " + (section ? section.getAttribute("data-guide-title") : "");
      } else {
        status.textContent = total + " results in " + topicsWithResults.length +
          (topicsWithResults.length === 1 ? " section" : " sections");
      }
    }
  }

  document.addEventListener("input", function (event) {
    if (!event.target || event.target.id !== "guide_search") return;
    var page = document.getElementById("guide_page");
    if (page) apply(page, event.target.value);
  });

  // Enter with results goes to the first one.
  document.addEventListener("keydown", function (event) {
    if (!event.target || event.target.id !== "guide_search" || event.key !== "Enter") return;
    event.preventDefault();
    var first = document.querySelector("#guide_page [data-guide-value]:not([hidden])");
    var section = first && first.closest("[data-guide-topic]");
    if (section && !section.hidden) scrollTo(first.id);
  });
})();
