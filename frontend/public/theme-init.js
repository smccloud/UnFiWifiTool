/* Apply the saved theme before the app renders to avoid a flash. */
(function () {
  var key = "unifi-wifi-theme";
  var preference = "system";
  try {
    var stored = window.localStorage.getItem(key);
    if (stored === "light" || stored === "dark" || stored === "system") {
      preference = stored;
    }
  } catch (error) {
    /* localStorage can be unavailable; fall back to the system preference. */
  }

  var resolved = preference;
  if (preference === "system") {
    resolved =
      window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark";
  }

  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themePreference = preference;

  var meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content", resolved === "light" ? "#f3f6fb" : "#0b1120");
  }
})();
