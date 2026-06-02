/* Studio jonli sozlamalar paneli (tema, shrift, modul bayroqlari). */
import {
  TweaksPanel,
  TweakSection,
  TweakSelect,
  TweakToggle,
} from "@/components/tweaks/TweaksPanel";
import { THEMES, FONT_SETS } from "@/lib/theme";
import { useTweaksCtx } from "@/context/TweaksContext";

export function StudioTweaks() {
  const { t, setTweak } = useTweaksCtx();
  return (
    <TweaksPanel>
      <TweakSection label="Ko‘rinish" />
      <TweakSelect
        label="Tema"
        value={t.theme}
        options={Object.keys(THEMES).map((k) => ({
          value: k,
          label: THEMES[k as keyof typeof THEMES].label,
        }))}
        onChange={(v: string) => setTweak("theme", v)}
      />
      <TweakSelect
        label="Shrift"
        value={t.fontSet}
        options={Object.keys(FONT_SETS).map((k) => ({
          value: k,
          label: FONT_SETS[k as keyof typeof FONT_SETS].label,
        }))}
        onChange={(v: string) => setTweak("fontSet", v)}
      />
      <TweakSection label="Chat ekrani" />
      <TweakToggle
        label="Latency ko‘rsatkichi"
        value={t.showTiming}
        onChange={(v: boolean) => setTweak("showTiming", v)}
      />
      <TweakToggle
        label="Tezkor javoblar"
        value={t.showSuggestions}
        onChange={(v: boolean) => setTweak("showSuggestions", v)}
      />
      <TweakSection label="Admin modullari" />
      <TweakToggle
        label="Suhbatlar bo‘limi"
        value={t.secConversations}
        onChange={(v: boolean) => setTweak("secConversations", v)}
      />
      <TweakToggle
        label="Foydalanuvchilar bo‘limi"
        value={t.secUsers}
        onChange={(v: boolean) => setTweak("secUsers", v)}
      />
      <TweakToggle
        label="Sozlamalar bo‘limi"
        value={t.secSettings}
        onChange={(v: boolean) => setTweak("secSettings", v)}
      />
    </TweaksPanel>
  );
}
