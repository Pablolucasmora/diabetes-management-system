(function () {
  var scannerState = null;
  var zxingScriptLoading = null;

  function byId(id) {
    return document.getElementById(id);
  }

  function ensureZxingBrowser() {
    if (window.ZXingBrowser && window.ZXingBrowser.BrowserMultiFormatReader) {
      return Promise.resolve();
    }
    if (zxingScriptLoading) return zxingScriptLoading;

    zxingScriptLoading = new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = "https://unpkg.com/@zxing/browser@0.1.5/umd/index.min.js";
      script.async = true;
      script.onload = function () { resolve(); };
      script.onerror = function () { reject(new Error("zxing load failed")); };
      document.head.appendChild(script);
    });
    return zxingScriptLoading;
  }

  async function getDetectorCtor() {
    if ("BarcodeDetector" in window) return window.BarcodeDetector;
    try {
      var mod = await import("https://esm.sh/barcode-detector/ponyfill");
      return mod && mod.BarcodeDetector ? mod.BarcodeDetector : null;
    } catch (_) {
      return null;
    }
  }

  function stopScanner() {
    if (!scannerState) return;
    scannerState.stopRequested = true;

    if (scannerState.rafId) {
      window.cancelAnimationFrame(scannerState.rafId);
      scannerState.rafId = 0;
    }
    if (scannerState.stream) {
      scannerState.stream.getTracks().forEach(function (track) { track.stop(); });
      scannerState.stream = null;
    }
    if (scannerState.zxingControls && typeof scannerState.zxingControls.stop === "function") {
      scannerState.zxingControls.stop();
      scannerState.zxingControls = null;
    }
    if (scannerState.zxingReader && typeof scannerState.zxingReader.reset === "function") {
      scannerState.zxingReader.reset();
      scannerState.zxingReader = null;
    }
    if (scannerState.modal) {
      scannerState.modal.classList.remove("opacity-100");
      scannerState.modal.classList.add("opacity-0", "invisible", "pointer-events-none");
    }
    scannerState = null;
  }

  function improveTrackForSafari(stream) {
    var tracks = stream ? stream.getVideoTracks() : [];
    if (!tracks || !tracks.length) return;
    var track = tracks[0];
    if (!track.getCapabilities || !track.applyConstraints) return;

    var caps = {};
    try {
      caps = track.getCapabilities() || {};
    } catch (_) {
      return;
    }

    var advanced = [];
    if (Array.isArray(caps.focusMode) && caps.focusMode.indexOf("continuous") !== -1) {
      advanced.push({ focusMode: "continuous" });
    }
    if (caps.zoom && typeof caps.zoom.max === "number") {
      var zoomTarget = Math.max(caps.zoom.min || 1, Math.min(caps.zoom.max, 2));
      advanced.push({ zoom: zoomTarget });
    }
    if (advanced.length) {
      track.applyConstraints({ advanced: advanced }).catch(function () {});
    }
  }

  function extractCode(item) {
    if (!item) return "";
    var raw = item.rawValue || item.value || item.text || item.data || "";
    return String(raw || "").trim();
  }

  async function initScannerIfPresent(root) {
    var scope = root && root.querySelector ? root : document;
    var video = scope.querySelector ? scope.querySelector("#scanner_video") : byId("scanner_video");
    if (!video) return;

    stopScanner();

    var output = byId("scanner_detected_code");
    var overlay = byId("scanner_border_overlay");
    var manualInput = byId("scanner_manual_input");
    var manualUseBtn = byId("scanner_manual_use_btn");
    var modal = byId("scanner_confirm_modal");
    var modalCode = byId("scanner_confirm_code");
    var modalYes = byId("scanner_confirm_yes");
    var modalNo = byId("scanner_confirm_no");
    var confirmForm = byId("scanner_confirm_form");
    var confirmBarcode = byId("scanner_confirm_barcode");

    if (!output || !overlay || !manualInput || !manualUseBtn || !modal || !modalCode || !modalYes || !modalNo || !confirmForm || !confirmBarcode) {
      return;
    }

    var state = {
      video: video,
      output: output,
      overlay: overlay,
      manualInput: manualInput,
      manualUseBtn: manualUseBtn,
      modal: modal,
      modalCode: modalCode,
      modalYes: modalYes,
      modalNo: modalNo,
      confirmForm: confirmForm,
      confirmBarcode: confirmBarcode,
      lastCode: "",
      lastSeenAt: 0,
      stream: null,
      rafId: 0,
      stopRequested: false,
      detector: null,
      zxingReader: null,
      zxingControls: null,
      zxingStarted: false,
      pendingConfirmCode: "",
      suppressUntil: 0,
      canvas: document.createElement("canvas"),
      ctx: null,
    };
    state.ctx = state.canvas.getContext("2d", { willReadFrequently: true });
    scannerState = state;
    window.__dbStopScanner = stopScanner;

    function showModal(code) {
      state.pendingConfirmCode = code;
      state.modalCode.textContent = code;
      state.modal.classList.remove("invisible", "opacity-0", "pointer-events-none");
      state.modal.classList.add("opacity-100");
      state.modalYes.disabled = false;
      state.modalNo.disabled = false;
    }

    function hideModal() {
      state.modal.classList.remove("opacity-100");
      state.modal.classList.add("opacity-0", "invisible", "pointer-events-none");
    }

    function requestConfirmation(code) {
      var clean = String(code || "").trim();
      if (!clean) return;
      if (Date.now() < state.suppressUntil) return;
      if (state.pendingConfirmCode === clean && state.modal.classList.contains("opacity-100")) return;
      showModal(clean);
    }

    function setFrameGreen() {
      state.lastSeenAt = Date.now();
      state.overlay.style.setProperty("border-color", "#22c55e", "important");
    }

    function borderDecayLoop() {
      if (state.stopRequested) return;
      if (state.lastSeenAt > 0 && Date.now() - state.lastSeenAt > 1000) {
        state.overlay.style.setProperty("border-color", "#ffffff", "important");
      }
      window.setTimeout(borderDecayLoop, 200);
    }

    function setCode(text) {
      if (!text) return;
      setFrameGreen();
      if (text !== state.lastCode) {
        state.lastCode = text;
        state.output.textContent = text;
      }
      requestConfirmation(text);
    }

    function startZXingFallback() {
      if (state.zxingStarted || state.stopRequested) return;
      state.zxingStarted = true;

      ensureZxingBrowser().then(function () {
        if (state.stopRequested) return;
        if (!(window.ZXingBrowser && window.ZXingBrowser.BrowserMultiFormatReader)) return;
        state.zxingReader = new window.ZXingBrowser.BrowserMultiFormatReader(undefined, { delayBetweenScanAttempts: 80 });
        state.zxingReader.decodeFromVideoDevice(undefined, state.video, function (result, _err, controls) {
          if (controls && !state.zxingControls) state.zxingControls = controls;
          if (result) {
            var txt = result.getText ? String(result.getText()) : extractCode(result);
            setCode(txt);
          }
        }).catch(function () {});
      }).catch(function () {});
    }

    function startDetectorLoop() {
      var lastRun = 0;
      var emptyReads = 0;

      var loop = function (ts) {
        if (state.stopRequested) return;
        state.rafId = window.requestAnimationFrame(loop);
        if (ts - lastRun < 150) return;
        lastRun = ts;
        if (!state.detector || state.video.readyState < 2) return;

        state.detector.detect(state.video).then(function (codes) {
          if (codes && codes.length) {
            emptyReads = 0;
            setCode(extractCode(codes[0]));
          } else {
            emptyReads += 1;
          }
        }).catch(function () {
          if (!state.ctx) return;
          var w = state.video.videoWidth || 0;
          var h = state.video.videoHeight || 0;
          if (w <= 0 || h <= 0) return;
          state.canvas.width = w;
          state.canvas.height = h;
          try {
            state.ctx.drawImage(state.video, 0, 0, w, h);
          } catch (_) {
            return;
          }
          state.detector.detect(state.canvas).then(function (codes) {
            if (codes && codes.length) {
              emptyReads = 0;
              setCode(extractCode(codes[0]));
            } else {
              emptyReads += 1;
            }
          }).catch(function () {
            emptyReads += 1;
          });
        });

        if (emptyReads > 30) {
          startZXingFallback();
          emptyReads = 0;
        }
      };
      state.rafId = window.requestAnimationFrame(loop);
    }

    state.manualUseBtn.addEventListener("click", function () {
      var typed = String(state.manualInput.value || "").trim();
      if (!typed) return;
      state.output.textContent = typed;
      setFrameGreen();
      requestConfirmation(typed);
    });

    state.modalNo.addEventListener("click", function () {
      hideModal();
      state.pendingConfirmCode = "";
      state.lastCode = "";
      state.suppressUntil = Date.now() + 250;
    });

    state.modalYes.addEventListener("click", function () {
      if (!state.pendingConfirmCode) return;
      state.modalYes.disabled = true;
      state.modalNo.disabled = true;
      var overlayLoading = byId("page_loading_overlay");
      if (overlayLoading) {
        overlayLoading.classList.remove("invisible", "opacity-0");
        overlayLoading.classList.add("opacity-100");
      }
      state.suppressUntil = Date.now() + 800;
      if (window.htmx && typeof window.htmx.ajax === "function") {
        window.htmx.ajax("POST", "/scanner/resolve", {
          target: "#scanner_confirm_feedback",
          swap: "innerHTML",
          values: { barcode: state.pendingConfirmCode },
        });
        return;
      }
      state.confirmBarcode.value = state.pendingConfirmCode;
      state.confirmForm.requestSubmit();
    });

    document.body.addEventListener("htmx:beforeSwap", function (event) {
      var target = event && event.detail ? event.detail.target : null;
      if (target && target.id === "main_content") {
        stopScanner();
      }
    }, { once: true });

    window.addEventListener("beforeunload", stopScanner, { once: true });

    var DetectorCtor = await getDetectorCtor();
    if (!DetectorCtor) {
      state.output.textContent = "Scanner unavailable on this browser";
      return;
    }

    state.output.textContent = "Starting scanner...";
    var wantedFormats = ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39", "itf", "codabar", "databar"];
    var supportedFormats = [];
    if (typeof DetectorCtor.getSupportedFormats === "function") {
      try {
        supportedFormats = await DetectorCtor.getSupportedFormats();
      } catch (_) {
        supportedFormats = [];
      }
    }
    var selectedFormats = supportedFormats.length
      ? wantedFormats.filter(function (f) { return supportedFormats.indexOf(f) !== -1; })
      : wantedFormats;

    try {
      state.detector = selectedFormats.length
        ? new DetectorCtor({ formats: selectedFormats })
        : new DetectorCtor();
    } catch (_) {
      try {
        state.detector = new DetectorCtor();
      } catch (_) {
        state.output.textContent = "Scanner unavailable on this browser";
        return;
      }
    }

    try {
      var stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1920, max: 3840 },
          height: { ideal: 1080, max: 2160 },
          frameRate: { ideal: 30, max: 60 },
        },
        audio: false,
      });
      if (state.stopRequested) {
        stream.getTracks().forEach(function (t) { t.stop(); });
        return;
      }
      state.stream = stream;
      state.video.srcObject = stream;
      state.video.setAttribute("playsinline", "true");
      state.video.setAttribute("webkit-playsinline", "true");
      state.video.play().catch(function () {});
      improveTrackForSafari(stream);
      state.output.textContent = "Scanning...";
      borderDecayLoop();
      startDetectorLoop();
    } catch (_) {
      state.output.textContent = "Camera permission denied or unavailable";
    }
  }

  function init() {
    initScannerIfPresent(document);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event && event.detail ? event.detail.target : null;
    if (!target || target.id !== "main_content") return;
    initScannerIfPresent(target);
  });
})();
