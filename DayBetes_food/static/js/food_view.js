// The view of the Food page lives in its URL (frontend_conventions.md §5), so
// that Back comes back to the pill, tab and filters that were showing.
//
// Every request of the list replaces the URL of the current history entry with
// the header's state (it adds no entry). The page has no saved copy
// (hx-history="false"), so coming back asks /food for that URL again.
//
// The search text is health data and does not go in the URL: it is kept in
// sessionStorage with the URL it belongs to, and given back only when that
// entry is reached again with Back (popstate). Opening Food anew starts empty.
(function () {
  if (window.__dbFoodView) return;
  window.__dbFoodView = true;

  var STORAGE_KEY = "dbFoodSearch";
  var VIEW_FIELDS = [
    ["food_filter", "filter"],
    ["food_search_mode", "search_mode"],
    ["food_food_mode", "food_mode"],
    ["food_favs_mode", "favs_mode"],
    ["food_recipes_mode", "recipes_mode"],
    ["food_recipes_meal", "meal_type"],
  ];
  var cameBack = false;

  function byId(id) {
    return document.getElementById(id);
  }

  function readStored() {
    try {
      return JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || "null");
    } catch (_) {
      return null;
    }
  }

  function store(url, text) {
    try {
      if (text) {
        window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ url: url, text: text }));
      } else {
        window.sessionStorage.removeItem(STORAGE_KEY);
      }
    } catch (_) {}
  }

  function viewUrl() {
    var params = new URLSearchParams();
    VIEW_FIELDS.forEach(function (pair) {
      var field = byId(pair[0]);
      if (field && field.value) params.set(pair[1], field.value);
    });
    return "/food?" + params.toString();
  }

  function isFoodListRequest(event) {
    var path = event.detail.path || "";
    return path.indexOf("/food/list") === 0 && path.indexOf("/food/list/external") !== 0;
  }

  window.addEventListener("popstate", function () {
    cameBack = true;
  });

  document.addEventListener("htmx:configRequest", function (event) {
    if (!isFoodListRequest(event) || !document.querySelector("[data-food-view]")) return;
    var input = byId("food_search_input");

    if (event.detail.elt && event.detail.elt.id === "food-list") {
      // The first load of the page: the search comes back only after Back.
      var stored = readStored();
      var here = window.location.pathname + window.location.search;
      if (cameBack && stored && stored.url === here && input) {
        input.value = stored.text;
        event.detail.parameters.search = stored.text;
      } else if (!cameBack) {
        store("", "");
      }
      cameBack = false;
      return;
    }

    var url = viewUrl();
    if (window.location.pathname + window.location.search !== url) {
      // Keeps history.state: it carries dbDepth (navigation.js) and htmx's mark.
      window.history.replaceState(window.history.state, "", url);
    }
    store(url, input ? input.value : "");
  });
})();
