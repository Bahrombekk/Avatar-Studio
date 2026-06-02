/* Tema va shrift tiplari (lib/theme.ts bilan birga ishlatiladi). */

export type ThemeKey = "editorial" | "midnight" | "daylight";
export type FontKey = "editorial" | "modern" | "grotesk";

/** :root ga qo'llaniladigan CSS custom-property xaritasi. */
export interface ThemeTokens {
  label: string;
  [token: `--${string}`]: string;
}

/** Shrift juftligi — display / body / mono CSS font-family stack'lari. */
export interface FontSet {
  label: string;
  display: string;
  body: string;
  mono: string;
}

export type ThemesMap = Record<ThemeKey, ThemeTokens>;
export type FontSetsMap = Record<FontKey, FontSet>;
