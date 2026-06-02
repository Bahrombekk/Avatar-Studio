/* Avatar Studio — Design System (tokens + applyTheme).
   Navy / brass / cream, IBM Plex + Newsreader. Uchta almashtiriladigan tema. */

import type {
  ThemesMap,
  FontSetsMap,
  ThemeKey,
  FontKey,
} from "@/types/theme";

// Har bir tema — :root ga CSS custom-property sifatida qo'llaniladigan token xaritasi.
export const THEMES: ThemesMap = {
  editorial: {
    label: "Editorial",
    "--bg": "#FAF7F0",
    "--panel": "#F4EFE3",
    "--panel-2": "#EFE8D8",
    "--card": "#FFFFFF",
    "--line": "rgba(15,37,64,.10)",
    "--line-soft": "rgba(15,37,64,.06)",
    "--ink": "#1A1410",
    "--ink-2": "#6B5E4D",
    "--ink-3": "#9C8D78",
    "--navy": "#0F2540",
    "--navy-2": "#1C3A5E",
    "--brass": "#B98944",
    "--brass-2": "#D7A85B",
    "--on-navy": "#F4EFE3",
    "--ok": "#5E8C56",
    "--ok-soft": "#8FB58A",
    "--warn": "#B98944",
    "--err": "#C0392B",
    "--err-soft": "#8B2A1F",
    "--sidebar": "#0F2540",
    "--sidebar-ink": "#C9D4E2",
    "--sidebar-active": "rgba(185,137,68,.18)",
    "--shadow": "0 24px 48px -16px rgba(15,37,64,.20)",
    "--shadow-sm": "0 2px 8px rgba(15,37,64,.08)",
    "--radius": "4px",
    "--radius-lg": "8px",
  },
  midnight: {
    label: "Midnight",
    "--bg": "#0C1118",
    "--panel": "#121925",
    "--panel-2": "#0F1620",
    "--card": "#161F2D",
    "--line": "rgba(201,212,226,.12)",
    "--line-soft": "rgba(201,212,226,.07)",
    "--ink": "#ECF1F8",
    "--ink-2": "#90A0B6",
    "--ink-3": "#5E6E84",
    "--navy": "#E7C27D",
    "--navy-2": "#D7A85B",
    "--brass": "#E7C27D",
    "--brass-2": "#F0D49A",
    "--on-navy": "#0C1118",
    "--ok": "#6FCF97",
    "--ok-soft": "#6FCF97",
    "--warn": "#E7C27D",
    "--err": "#E27D6B",
    "--err-soft": "#E27D6B",
    "--sidebar": "#0A0F16",
    "--sidebar-ink": "#90A0B6",
    "--sidebar-active": "rgba(231,194,125,.16)",
    "--shadow": "0 24px 60px -16px rgba(0,0,0,.6)",
    "--shadow-sm": "0 2px 10px rgba(0,0,0,.4)",
    "--radius": "6px",
    "--radius-lg": "10px",
  },
  daylight: {
    label: "Daylight",
    "--bg": "#F6F8FB",
    "--panel": "#FFFFFF",
    "--panel-2": "#EEF2F8",
    "--card": "#FFFFFF",
    "--line": "rgba(20,40,70,.10)",
    "--line-soft": "rgba(20,40,70,.05)",
    "--ink": "#15263B",
    "--ink-2": "#5A6B82",
    "--ink-3": "#93A2B8",
    "--navy": "#13366B",
    "--navy-2": "#1E4C92",
    "--brass": "#1E4C92",
    "--brass-2": "#3A6FC4",
    "--on-navy": "#FFFFFF",
    "--ok": "#1F8A5B",
    "--ok-soft": "#3FB37F",
    "--warn": "#C77A1E",
    "--err": "#D14343",
    "--err-soft": "#B23636",
    "--sidebar": "#FFFFFF",
    "--sidebar-ink": "#5A6B82",
    "--sidebar-active": "rgba(30,76,146,.10)",
    "--shadow": "0 20px 44px -18px rgba(20,40,70,.22)",
    "--shadow-sm": "0 2px 8px rgba(20,40,70,.07)",
    "--radius": "8px",
    "--radius-lg": "12px",
  },
};

// Shrift juftliklari (label -> {display, body, mono} CSS font-family stack'lari)
export const FONT_SETS: FontSetsMap = {
  editorial: {
    label: "Editorial",
    display: '"Newsreader", Georgia, serif',
    body: '"IBM Plex Sans", system-ui, sans-serif',
    mono: '"IBM Plex Mono", ui-monospace, monospace',
  },
  modern: {
    label: "Modern",
    display: '"Fraunces", Georgia, serif',
    body: '"Geist", system-ui, sans-serif',
    mono: '"Geist Mono", ui-monospace, monospace',
  },
  grotesk: {
    label: "Grotesk",
    display: '"Space Grotesk", system-ui, sans-serif',
    body: '"Inter Tight", system-ui, sans-serif',
    mono: '"IBM Plex Mono", ui-monospace, monospace',
  },
};

export function applyTheme(themeKey: string, fontKey: string): void {
  const t = THEMES[themeKey as ThemeKey] || THEMES.editorial;
  const root = document.documentElement;
  Object.entries(t).forEach(([k, v]) => {
    if (k.startsWith("--")) root.style.setProperty(k, v);
  });
  const f = FONT_SETS[fontKey as FontKey] || FONT_SETS.editorial;
  root.style.setProperty("--font-display", f.display);
  root.style.setProperty("--font-body", f.body);
  root.style.setProperty("--font-mono", f.mono);
  root.setAttribute("data-theme", themeKey);
}
