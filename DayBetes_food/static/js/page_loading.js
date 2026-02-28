(function () {
  function byId(id) {
    return document.getElementById(id);
  }

  function setLoading(active) {
    var overlay = byId("page_loading_overlay");
    var main = byId("main_content");
    if (!overlay || !main) return;

    if (active) {
      overlay.classList.remove("invisible", "opacity-0");
      window.requestAnimationFrame(function () {
        overlay.classList.add("opacity-100");
      });
      main.style.opacity = "0.28";
      main.style.filter = "blur(1.2px)";
      return;
    }

    overlay.classList.remove("opacity-100");
    overlay.classList.add("opacity-0");
    window.setTimeout(function () {
      if (overlay.classList.contains("opacity-0")) {
        overlay.classList.add("invisible");
      }
    }, 260);
    window.requestAnimationFrame(function () {
      main.style.opacity = "1";
      main.style.filter = "none";
    });
  }

  function bindListeners() {
    document.body.addEventListener("htmx:beforeRequest", function (event) {
      var target = event && event.detail ? event.detail.target : null;
      if (target && target.id === "main_content") setLoading(true);
    });

    document.body.addEventListener("htmx:afterSwap", function (event) {
      var target = event && event.detail ? event.detail.target : null;
      if (target && target.id === "main_content") setLoading(false);
    });

    document.body.addEventListener("htmx:responseError", function () {
      setLoading(false);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindListeners);
  } else {
    bindListeners();
  }
})();
