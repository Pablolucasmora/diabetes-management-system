from fasthtml.common import *


def scanner_main():
    return Main(
        Div(
            Button(
                "Back",
                type="button",
                cls="web_button self-start px-3 py-1.5 text-sm",
                hx_get="/menu",
                hx_target="#main_content",
                hx_push_url="true",
                **{"hx-on:click": "if(window.__dbStopScanner){window.__dbStopScanner();}"},
            ),
            Div(
                Video(
                    id="scanner_video",
                    autoplay=True,
                    playsinline=True,
                    muted=True,
                    cls="w-full h-full object-cover rounded-2xl bg-black",
                ),
                id="scanner_camera_frame",
                cls="web_container w-full aspect-[4/3] p-2 overflow-hidden border-[6px] border-white transition-colors duration-150",
            ),
            Div(
                P("Detected barcode", cls="text-xs font-semibold uppercase tracking-wide text-gray-600"),
                P("-", id="scanner_detected_code", cls="text-base font-semibold text-gray-900 break-all"),
                id="scanner_result",
                cls="web_container w-full p-3 rounded-2xl flex flex-col gap-1",
            ),
            Div(
                Label("Manual barcode", cls="text-xs font-semibold uppercase tracking-wide text-gray-600"),
                Div(
                    Input(
                        type="text",
                        name="barcode_manual",
                        placeholder="Enter barcode",
                        inputmode="numeric",
                        autocomplete="off",
                        cls="web_input w-full text-sm",
                    ),
                    Button("Use", type="button", cls="web_button px-3 py-1.5 text-sm shrink-0"),
                    cls="w-full flex items-center gap-2.5",
                ),
                cls="web_container w-full p-3 rounded-2xl flex flex-col gap-2.5",
            ),
            cls="""
                min-h-screen
                flex flex-col items-center
                md:mt-7 lg:mt-7 mt-2
                md:w-md lg:w-md w-xs
                w-full mx-auto
                px-2 py-3
                gap-4
            """,
            data_hide_cart="true",
        ),
        Script(
            """
            (async function(){
              var video = document.getElementById('scanner_video');
              var output = document.getElementById('scanner_detected_code');
              var frame = document.getElementById('scanner_camera_frame');
              if(!video || !output || !frame) return;
              var lastCode = "";
              var stream = null;
              var rafId = 0;
              var stopRequested = false;
              var detector = null;

              var setCode = function(text){
                if(!text) return;
                if(text === lastCode) return;
                lastCode = text;
                output.textContent = text;
                frame.style.borderColor = "#22c55e";
              };

              var getDetectorCtor = async function(){
                if("BarcodeDetector" in window){
                  return window.BarcodeDetector;
                }
                try {
                  var mod = await import("https://esm.sh/barcode-detector/ponyfill");
                  return mod && mod.BarcodeDetector ? mod.BarcodeDetector : null;
                } catch(_) {
                  return null;
                }
              };

              var startDetectorLoop = function(){
                var lastRun = 0;
                var loop = function(ts){
                  if(stopRequested) return;
                  rafId = window.requestAnimationFrame(loop);
                  if(ts - lastRun < 150) return;
                  lastRun = ts;
                  if(!detector || video.readyState < 2) return;
                  detector.detect(video).then(function(codes){
                    if(codes && codes.length){
                      setCode(String(codes[0].rawValue || ""));
                    }
                  }).catch(function(){});
                };
                rafId = window.requestAnimationFrame(loop);
              };

              var improveTrackForSafari = function(s){
                var tracks = s ? s.getVideoTracks() : [];
                if(!tracks || !tracks.length) return;
                var track = tracks[0];
                if(!track.getCapabilities || !track.applyConstraints) return;
                var caps = {};
                try { caps = track.getCapabilities() || {}; } catch(_) { return; }
                var advanced = [];
                if(Array.isArray(caps.focusMode) && caps.focusMode.indexOf("continuous") !== -1){
                  advanced.push({ focusMode: "continuous" });
                }
                if(caps.zoom && typeof caps.zoom.max === "number"){
                  var zoomTarget = Math.max(caps.zoom.min || 1, Math.min(caps.zoom.max, 2));
                  advanced.push({ zoom: zoomTarget });
                }
                if(advanced.length){
                  track.applyConstraints({ advanced: advanced }).catch(function(){});
                }
              };

              var DetectorCtor = await getDetectorCtor();
              if(!DetectorCtor){
                output.textContent = "Scanner unavailable on this browser";
                return;
              }
              output.textContent = "Starting scanner...";
              var wantedFormats = ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39", "itf", "codabar", "databar"];
              var supportedFormats = [];
              if(typeof DetectorCtor.getSupportedFormats === "function"){
                try {
                  supportedFormats = await DetectorCtor.getSupportedFormats();
                } catch (_) {
                  supportedFormats = [];
                }
              }
              var selectedFormats = supportedFormats.length
                ? wantedFormats.filter(function(f){ return supportedFormats.indexOf(f) !== -1; })
                : wantedFormats;
              try {
                detector = selectedFormats.length
                  ? new DetectorCtor({ formats: selectedFormats })
                  : new DetectorCtor();
              } catch (_) {
                try {
                  detector = new DetectorCtor();
                } catch (_) {
                  output.textContent = "Scanner unavailable on this browser";
                  return;
                }
              }

              navigator.mediaDevices.getUserMedia({
                video: {
                  facingMode: { ideal: "environment" },
                  width: { ideal: 1920, max: 3840 },
                  height: { ideal: 1080, max: 2160 },
                  frameRate: { ideal: 30, max: 60 }
                },
                audio: false
              }).then(function(s){
                stream = s;
                video.srcObject = s;
                video.setAttribute("playsinline", "true");
                video.setAttribute("webkit-playsinline", "true");
                video.play().catch(function(){});
                improveTrackForSafari(s);
                output.textContent = "Scanning...";
                startDetectorLoop();
              }).catch(function(){
                output.textContent = "Camera permission denied or unavailable";
              });

              var stop = function(){
                stopRequested = true;
                if(rafId){
                  window.cancelAnimationFrame(rafId);
                  rafId = 0;
                }
                if(stream){
                  stream.getTracks().forEach(function(track){ track.stop(); });
                  stream = null;
                }
              };
              window.__dbStopScanner = stop;
              document.body.addEventListener("htmx:beforeSwap", function(event){
                var target = event && event.detail ? event.detail.target : null;
                if(target && target.id === "main_content"){
                  stop();
                }
              }, { once: true });
              window.addEventListener("beforeunload", stop, { once: true });
            })();
            """
            ,
            type="module"
        ),
    )
