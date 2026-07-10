"use client";

import { useCallback, useEffect, useState } from "react";

export type ThemePreference = "light" | "dark" | "system";

const STORAGE_KEY = "ce-theme";

/** The inline script that sets the theme class BEFORE first paint (no flash). */
export const themeInitScript = `
(function () {
  try {
    var stored = localStorage.getItem('${STORAGE_KEY}');
    var mql = window.matchMedia('(prefers-color-scheme: dark)');
    var dark = stored === 'dark' || ((!stored || stored === 'system') && mql.matches);
    document.documentElement.classList.toggle('dark', dark);
  } catch (e) {}
})();
`;

function resolveIsDark(pref: ThemePreference): boolean {
  if (pref === "dark") return true;
  if (pref === "light") return false;
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

function applyTheme(pref: ThemePreference): void {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", resolveIsDark(pref));
}

/**
 * Read/update the theme preference. Pure client concern — persisted to
 * localStorage, NEVER sent to the server or added to any schema.
 */
export function useTheme(): {
  theme: ThemePreference;
  setTheme: (pref: ThemePreference) => void;
} {
  const [theme, setThemeState] = useState<ThemePreference>("system");

  useEffect(() => {
    const stored = (localStorage.getItem(STORAGE_KEY) as ThemePreference | null) ?? "system";
    setThemeState(stored);
    applyTheme(stored);

    // Keep "system" reactive to OS changes.
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (): void => {
      if ((localStorage.getItem(STORAGE_KEY) ?? "system") === "system") {
        applyTheme("system");
      }
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  const setTheme = useCallback((pref: ThemePreference) => {
    localStorage.setItem(STORAGE_KEY, pref);
    setThemeState(pref);
    applyTheme(pref);
  }, []);

  return { theme, setTheme };
}
