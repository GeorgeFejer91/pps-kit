const THEME_KEY = "ppsDesigner.theme";

export function initializeTheme(toggle) {
  const root = document.documentElement;
  const system = matchMedia("(prefers-color-scheme: dark)");
  const themeColor = document.querySelector('meta[name="theme-color"]');
  let preference;

  function applyTheme() {
    const theme = preference || (system.matches ? "dark" : "light");
    root.dataset.theme = theme;
    toggle.setAttribute("aria-pressed", String(theme === "dark"));
    toggle.title = theme === "dark" ? "Use light theme" : "Use dark theme";
    if (themeColor) themeColor.content = getComputedStyle(root).backgroundColor;
  }

  function restoreTheme() {
    try {
      const stored = localStorage.getItem(THEME_KEY);
      preference = stored === "light" || stored === "dark" ? stored : null;
    } catch {
      // Storage can be disabled. The control still works for this page.
    }
    applyTheme();
  }

  toggle.addEventListener("click", () => {
    preference = root.dataset.theme === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(THEME_KEY, preference);
    } catch {
      // Keep the current page's choice if storage is unavailable.
    }
    applyTheme();
  });
  system.addEventListener("change", applyTheme);
  window.addEventListener("storage", (event) => {
    if (event.key === THEME_KEY || event.key === null) restoreTheme();
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) restoreTheme();
  });
  restoreTheme();
}
