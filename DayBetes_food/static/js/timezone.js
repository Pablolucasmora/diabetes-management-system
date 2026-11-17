// Zone of this browser for the server (measurement_conventions.md §9, decision
// of 2026-11-17): typed times are read in it, times are shown in it and new
// events store it as timezone_at_event. It is kept in the `daybetes_tz` cookie
// (the name is repeated in time_utils.py); the server checks it against the
// list of IANA zones and uses Europe/Madrid without it. It only changes when the
// browser's zone changes, for example on a trip.
(function () {
  var NAME = "daybetes_tz";
  var zone = "";
  try {
    zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch (_) {
    return;
  }
  if (!zone) return;
  var current = document.cookie.split("; ").find(function (part) {
    return part.indexOf(NAME + "=") === 0;
  });
  if (current && decodeURIComponent(current.slice(NAME.length + 1)) === zone) return;
  document.cookie =
    NAME + "=" + encodeURIComponent(zone) + "; path=/; max-age=31536000; SameSite=Lax" +
    (window.location.protocol === "https:" ? "; Secure" : "");
})();
