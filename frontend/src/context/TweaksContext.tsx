/* Studio tweaks (tema, shrift, modul bayroqlari) — global kontekst.
   useTweaks() hook'i TweaksPanel.jsx'dan keladi (localStorage'da saqlanadi). */
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useTweaks } from "@/components/tweaks/TweaksPanel";
import { applyTheme } from "@/lib/theme";
import type { Avatar } from "@/types/avatar";
import type { Tweaks, SetTweak } from "@/types/tweaks";

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/ {
  theme: "editorial",
  fontSet: "editorial",
  secConversations: true,
  secUsers: true,
  secSettings: true,
  showTiming: true,
  showSuggestions: true,
} /*EDITMODE-END*/;

interface TweaksContextValue {
  t: Tweaks;
  setTweak: SetTweak;
}

const TweaksContext = createContext<TweaksContextValue | null>(null);

export function TweaksProvider({ children }: { children: ReactNode }) {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS) as [Tweaks, SetTweak];

  useEffect(() => {
    applyTheme(t.theme, t.fontSet);
  }, [t.theme, t.fontSet]);

  return (
    <TweaksContext.Provider value={{ t, setTweak }}>
      {children}
    </TweaksContext.Provider>
  );
}

export function useTweaksCtx(): TweaksContextValue {
  const ctx = useContext(TweaksContext);
  if (!ctx) {
    throw new Error("useTweaksCtx TweaksProvider ichida ishlatilishi kerak");
  }
  return ctx;
}

/** Chat'ga ta'sir qiluvchi tweaklarni avatarga qo'llaydi (tavsiyalar toggle). */
export function applyTweaksToAvatar(
  av: Avatar | null | undefined,
  t: Tweaks,
): Avatar | null | undefined {
  if (!av) return av;
  return { ...av, suggestions: t.showSuggestions ? av.suggestions : [] };
}
