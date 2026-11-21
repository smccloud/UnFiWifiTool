/* Apply the saved theme before the app renders to avoid a flash. */
(function () {
  const key = "unifi-wifi-theme";
  let preference = "system";
  try {
    const stored = window.localStorage.getItem(key);
    if (stored === "light" || stored === "dark" || stored === "system") {
      preference = stored;
    }
  } catch {
    /* localStorage can be unavailable; fall back to the system preference. */
  }

  const prefersLight =
    window.matchMedia?.("(prefers-color-scheme: light)")?.matches ?? false;
  const resolved =
    preference === "system" ? (prefersLight ? "light" : "dark") : preference;

  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themePreference = preference;

  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content", resolved === "light" ? "#f3f6fb" : "#0b1120");
  }
})();
