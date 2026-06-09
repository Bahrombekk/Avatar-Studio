/* Studio "tweaks" (jonli sozlamalar) tiplari. */

export interface Tweaks {
  theme: string;
  fontSet: string;
  uiLang: string; // interfeys tili: "uz" | "ru" | "en"
  secConversations: boolean;
  secUsers: boolean;
  secSettings: boolean;
  showTiming: boolean;
  showSuggestions: boolean;
  [key: string]: string | boolean;
}

export type SetTweak = (key: string, value: string | boolean) => void;
