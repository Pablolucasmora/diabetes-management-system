(function () {
  if (window.__dbSmartMacrosBootstrapped) {
    if (typeof window.dbSmartMacrosBindAll === "function") {
      window.dbSmartMacrosBindAll();
    }
    return;
  }
  window.__dbSmartMacrosBootstrapped = true;

  function normalizeToken(token) {
    return String(token || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z]/g, "");
  }

  var macroFamilies = [
    {
      field: "calories_100g",
      aliases: ["kcal", "kca", "caloria", "calorias", "calorie", "calories", "cal", "energia", "ener", "ene"]
    },
    {
      field: "carbs_100g",
      aliases: ["hc", "ch", "hidrato", "hidratos", "carbo", "carbos", "carbohidrato", "carbohidratos", "carb", "carbs"]
    },
    {
      field: "sugars_100g",
      aliases: ["az", "azu", "azuc", "azuca", "azucar", "azucare", "azucares", "sugar", "sugars"]
    },
    {
      field: "proteins_100g",
      aliases: ["pr", "pro", "prot", "prote", "protein", "protei", "proteina", "proteinas", "proteins"]
    },
    {
      field: "fats_100g",
      aliases: ["gr", "gra", "gras", "grasa", "grasas", "fat", "fats", "lipido", "lipidos"]
    },
    {
      field: "saturated_100g",
      aliases: ["sat", "satu", "satur", "satura", "saturada", "saturadas", "st", "gs"]
    },
    {
      field: "fiber_100g",
      aliases: ["fb", "fib", "fibr", "fibra", "fiber"]
    }
  ];

  var defaultValues = {
    calories_100g: 0,
    carbs_100g: 0,
    sugars_100g: 0,
    proteins_100g: 0,
    fats_100g: 0,
    saturated_100g: 0,
    fiber_100g: 0
  };

  var prettyName = {
    calories_100g: "Kcal",
    carbs_100g: "HC",
    sugars_100g: "Azucar",
    proteins_100g: "Proteinas",
    fats_100g: "Grasas",
    saturated_100g: "Sat.",
    fiber_100g: "Fibra"
  };

  var pillColor = {
    calories_100g: "#111827",
    carbs_100g: "#3b82f6",
    sugars_100g: "#8b5cf6",
    proteins_100g: "#10b981",
    fats_100g: "#f59e0b",
    saturated_100g: "#ef4444",
    fiber_100g: "#6b7280"
  };
  var defaultKeys = Object.keys(defaultValues);
  var regexNumberFirst = /(\d+(?:[.,]\d+)?)\s*(?:g|gr|gramos|ml)?\s*([a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)/g;
  var regexWordFirst = /([a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)\s*(\d+(?:[.,]\d+)?)/g;

  function resolveField(rawToken) {
    var token = normalizeToken(rawToken);
    if (!token) return null;
    for (var i = 0; i < macroFamilies.length; i += 1) {
      var family = macroFamilies[i];
      for (var j = 0; j < family.aliases.length; j += 1) {
        var alias = family.aliases[j];
        if (alias.indexOf(token) === 0 || token.indexOf(alias) === 0) {
          return family.field;
        }
      }
    }
    return null;
  }

  function parseSmartMacros(text) {
    var result = {
      calories_100g: 0,
      carbs_100g: 0,
      sugars_100g: 0,
      proteins_100g: 0,
      fats_100g: 0,
      saturated_100g: 0,
      fiber_100g: 0
    };

    if (!text) return result;

    var raw = String(text).toLowerCase();
    regexNumberFirst.lastIndex = 0;
    regexWordFirst.lastIndex = 0;

    function applyMatch(amountRaw, macroRaw) {
      var field = resolveField(macroRaw);
      if (!field) return;
      var amount = Number(String(amountRaw).replace(",", "."));
      if (Number.isNaN(amount)) return;
      result[field] = amount;
    }

    var match;
    while ((match = regexNumberFirst.exec(raw)) !== null) {
      applyMatch(match[1], match[2]);
    }
    while ((match = regexWordFirst.exec(raw)) !== null) {
      applyMatch(match[2], match[1]);
    }

    return result;
  }

  function fillHidden(prefix, values) {
    for (var i = 0; i < defaultKeys.length; i += 1) {
      var key = defaultKeys[i];
      var hidden = document.getElementById(prefix + "_" + key);
      if (!hidden) continue;
      hidden.value = String(values[key] != null ? values[key] : defaultValues[key]);
    }
  }

  function renderPreview(outputEl, values) {
    if (!outputEl) return;
    var chips = [];
    var keys = Object.keys(values);
    for (var i = 0; i < keys.length; i += 1) {
      var key = keys[i];
      var val = Number(values[key] || 0);
      if (val > 0) {
        chips.push(
          '<span style="display:inline-block;padding:2px 8px;border-radius:999px;color:#fff;font-size:11px;margin:2px 4px 2px 0;background:' +
            pillColor[key] +
            ';">' +
            prettyName[key] +
            ": " +
            val +
            "g</span>"
        );
      }
    }

    if (!chips.length) {
      outputEl.textContent = "Formato no reconocido aun.";
      return;
    }
    outputEl.innerHTML = '<span style="font-size:11px;color:#4b5563;">Detectado: </span>' + chips.join("");
  }

  function syncInput(input) {
    if (!input) return;
    var prefix = input.dataset ? input.dataset.smartMacrosPrefix : null;
    if (!prefix && input.id && input.id.indexOf("_smart_macros_input") > 0) {
      prefix = input.id.replace("_smart_macros_input", "");
    }

    var outputSelector = input.dataset ? input.dataset.smartMacrosOutput : null;
    var outputEl = outputSelector ? document.querySelector(outputSelector) : null;
    if (!outputEl && prefix) {
      outputEl = document.getElementById(prefix + "_smart_macros_output");
    }
    if (!outputEl && input.nextElementSibling) {
      outputEl = input.nextElementSibling;
    }

    var parsed = parseSmartMacros(input.value || "");
    if (prefix) fillHidden(prefix, parsed);
    renderPreview(outputEl, parsed);
  }

  function bindOne(input) {
    if (!input || input.dataset.smartMacrosBound === "1") return;
    input.dataset.smartMacrosBound = "1";

    function sync() {
      syncInput(input);
    }

    input.addEventListener("input", sync);
    input.addEventListener("change", sync);
    sync();
  }

  function bindAll() {
    var nodes = document.querySelectorAll("[data-smart-macros='true'], [id$='_smart_macros_input']");
    for (var i = 0; i < nodes.length; i += 1) {
      bindOne(nodes[i]);
    }
  }
  window.dbSmartMacrosBindAll = bindAll;

  window.dbSmartMacrosSync = function (inputOrId) {
    if (!inputOrId) return;
    var input = inputOrId;
    if (typeof inputOrId === "string") {
      input = document.getElementById(inputOrId);
    }
    syncInput(input);
  };

  function attachSwapListener() {
    if (!document.body) return;
    document.body.addEventListener("htmx:afterSwap", bindAll);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindAll();
      attachSwapListener();
    });
  } else {
    bindAll();
    attachSwapListener();
  }
})();
