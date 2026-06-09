/* Yengil i18n — tashqi kutubxonasiz. `useT()` joriy tilni TweaksContext'dan oladi
   (uiLang tweak, localStorage'da saqlanadi). Kalit topilmasa uz'ga, so'ng kalitning
   o'ziga qaytadi — bosqichma-bosqich tarjima qo'shish xavfsiz.

   Yangi string qo'shish: DICTS.uz/ru/en ga kalit qo'shing va useT()("kalit") ishlating. */
import { useTweaksCtx } from "@/context/TweaksContext";

export type Lang = "uz" | "ru" | "en";

export const LANGS: { id: Lang; label: string }[] = [
  { id: "uz", label: "O‘zbekcha" },
  { id: "ru", label: "Русский" },
  { id: "en", label: "English" },
];

type Dict = Record<string, string>;

const uz: Dict = {
  "app.live": "Jonli suhbat",
  "conn.connected": "Ulangan",
  "conn.connecting": "Ulanmoqda…",
  "rt.needReady": "Ovozli suhbat uchun modeli tayyor avatar kerak.",
  "rt.needReadySub": "Avatar yarating → Idle + Artefakt quring.",
  "rt.hint": "Mikrofon tugmasini bosib gapiring — gapirib bo'lgach o'zi to'xtaydi.",
  "rt.listening": "Tinglanmoqda…",
  "rt.thinking": "O'ylanmoqda…",
  "rt.preparing": "Javob tayyorlanmoqda…",
  "rt.listeningShort": "Tinglayapman…",
  "rt.thinkingShort": "O'ylayapman…",
  "rt.speak": "Gapirish",
  "rt.stop": "Tinglanmoqda… (to'xtatish)",
  "rt.noSpeech": "Nutq aniqlanmadi — qaytadan gapiring",
  "rt.micDenied": "Mikrofon ruxsati berilmadi",
  "rt.noConn": "Aloqa yo'q — sahifani yangilang",
  "you": "Siz",
};

const ru: Dict = {
  "app.live": "Живой диалог",
  "conn.connected": "Подключено",
  "conn.connecting": "Подключение…",
  "rt.needReady": "Для голосового диалога нужен готовый аватар.",
  "rt.needReadySub": "Создайте аватар → Idle + Артефакт.",
  "rt.hint": "Нажмите кнопку микрофона и говорите — остановится сам.",
  "rt.listening": "Слушаю…",
  "rt.thinking": "Думаю…",
  "rt.preparing": "Готовлю ответ…",
  "rt.listeningShort": "Слушаю…",
  "rt.thinkingShort": "Думаю…",
  "rt.speak": "Говорить",
  "rt.stop": "Слушаю… (остановить)",
  "rt.noSpeech": "Речь не распознана — повторите",
  "rt.micDenied": "Доступ к микрофону запрещён",
  "rt.noConn": "Нет связи — обновите страницу",
  "you": "Вы",
};

const en: Dict = {
  "app.live": "Live conversation",
  "conn.connected": "Connected",
  "conn.connecting": "Connecting…",
  "rt.needReady": "Voice chat needs an avatar with a built model.",
  "rt.needReadySub": "Create an avatar → build Idle + Artifact.",
  "rt.hint": "Press the mic button and speak — it stops automatically.",
  "rt.listening": "Listening…",
  "rt.thinking": "Thinking…",
  "rt.preparing": "Preparing answer…",
  "rt.listeningShort": "Listening…",
  "rt.thinkingShort": "Thinking…",
  "rt.speak": "Speak",
  "rt.stop": "Listening… (stop)",
  "rt.noSpeech": "No speech detected — try again",
  "rt.micDenied": "Microphone access denied",
  "rt.noConn": "No connection — refresh the page",
  "you": "You",
};

const DICTS: Record<Lang, Dict> = { uz, ru, en };

export type TFunc = (key: string, fallback?: string) => string;

export function translate(lang: Lang, key: string, fallback?: string): string {
  return DICTS[lang]?.[key] ?? DICTS.uz[key] ?? fallback ?? key;
}

/** Joriy tilga bog'langan tarjima funksiyasi (TweaksContext ichida). */
export function useT(): TFunc {
  const { t } = useTweaksCtx();
  const lang = (t.uiLang as Lang) in DICTS ? (t.uiLang as Lang) : "uz";
  return (key, fallback) => translate(lang, key, fallback);
}
