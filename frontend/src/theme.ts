import { useCallback, useEffect, useState } from "react";

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "unifi-wifi-theme";

const LIGHT_QUERY = "(prefers-color-scheme: light)";

export function isThemePreference(value: string | null): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

function systemTheme(): ResolvedTheme {
  if (typeof window === "undefined" || !window.matchMedia) return "dark";
  return window.matchMedia(LIGHT_QUERY).matches ? "light" : "dark";
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  return preference === "system" ? systemTheme() : preference;
}

function readPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

function applyTheme(preference: ThemePreference, resolved: ResolvedTheme): void {
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.dataset.themePreference = preference;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content", resolved === "light" ? "#f3f6fb" : "#0b1120");
  }
}

export function useTheme() {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    typeof window === "undefined" ? "system" : readPreference(),
  );
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() =>
    resolveTheme(typeof window === "undefined" ? "system" : readPreference()),
  );

  useEffect(() => {
    const media = window.matchMedia(LIGHT_QUERY);
    const sync = () => {
      const next = preference === "system" ? (media.matches ? "light" : "dark") : preference;
      applyTheme(preference, next);
      setResolvedTheme(next);
    };

    sync();
    if (preference === "system") {
      media.addEventListener("change", sync);
      return () => media.removeEventListener("change", sync);
    }
    return undefined;
  }, [preference]);

  const setPreference = useCallback((next: ThemePreference) => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Storage can be unavailable in private modes; the theme still applies.
    }
    setPreferenceState(next);
  }, []);

  return { preference, resolvedTheme, setPreference };
}
