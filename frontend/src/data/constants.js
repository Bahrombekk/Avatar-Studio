/* Avatar Studio — ko'p-avatarli platforma konstantalari.
   Avatarlar backend'dan (/api/avatars) yuklanadi; bu yerda statik reestrlar. */

// Real backend ovozlari — id to'g'ridan-to'g'ri /chat-stream ga uzatiladi
// (backend VOICES kalitlari bilan bir xil: madina/sardor/nigora/yulduz).
export const VOICES = [
  { id: "madina", name: "Madina", lang: "O‘zbek", gender: "Ayol",  tag: "Edge",   provider: "edge" },
  { id: "sardor", name: "Sardor", lang: "O‘zbek", gender: "Erkak", tag: "Edge",   provider: "edge" },
  { id: "nigora", name: "Nigora", lang: "O‘zbek", gender: "Ayol",  tag: "Yandex", provider: "yandex" },
  { id: "yulduz", name: "Yulduz", lang: "O‘zbek", gender: "Ayol",  tag: "Yandex", provider: "yandex_v3" },
];

export const LANGUAGES = [
  { code: "uz", label: "O‘zbek",  native: "O‘zbekcha", flag: "UZ" },
  { code: "ru", label: "Rus",     native: "Русский",   flag: "RU" },
  { code: "en", label: "Ingliz",  native: "English",   flag: "EN" },
  { code: "kk", label: "Qozoq",   native: "Қазақша",   flag: "KZ" },
];

// Suhbat preview ekrani uchun namuna boshlang'ich xabar.
export const SAMPLE_THREAD = [
  { role: "bot",  text: "Assalomu alaykum. Men Madina — O‘zbekiston Temir Yo‘llari virtual yordamchisi. Poyezdlar, chiptalar yoki sayohat haqida savolingiz bormi?", time: "09:41" },
];

export const BOT_REPLIES = {
  "Chipta narxi qancha?": "Narx yo‘nalish va vagon turiga qarab farq qiladi. Aniq yo‘nalishni ayting.",
  "Toshkent–Samarqand poyezdi": "Afrosiyob kuniga bir necha marta qatnaydi, yo‘lda ~2 soat.",
  "Bagaj qoidalari": "Har yo‘lovchiga 35 kg bepul. Ortig‘i alohida rasmiylashtiriladi.",
  "__default": "Savolingizni qabul qildim. Yo‘nalish yoki sanani aniqlashtirsangiz, aniqroq aytaman.",
};

// Analitika fallback'i (backend /api/analytics yuklanmaguncha ko'rsatiladi).
export const ANALYTICS = {
  totals: { sessions: 30770, avgLatency: 2.4, cacheRate: 38, csat: 4.6, uptime: 99.7 },
  latencyBreakdown: [
    { stage: "GPT",   value: 0.6, color: "var(--brass)" },
    { stage: "Ovoz",  value: 0.7, color: "var(--brass-2)" },
    { stage: "Video", value: 1.1, color: "var(--navy)" },
  ],
  daily: [
    { d: "01", sessions: 1820, latency: 2.7 },
    { d: "02", sessions: 2010, latency: 2.6 },
    { d: "03", sessions: 1760, latency: 2.5 },
    { d: "04", sessions: 2230, latency: 2.4 },
    { d: "05", sessions: 2580, latency: 2.5 },
    { d: "06", sessions: 2910, latency: 2.3 },
    { d: "07", sessions: 2440, latency: 2.2 },
    { d: "08", sessions: 2120, latency: 2.4 },
    { d: "09", sessions: 2360, latency: 2.3 },
    { d: "10", sessions: 2680, latency: 2.2 },
    { d: "11", sessions: 2890, latency: 2.1 },
    { d: "12", sessions: 3050, latency: 2.3 },
    { d: "13", sessions: 2770, latency: 2.4 },
    { d: "14", sessions: 2150, latency: 2.4 },
  ],
  topQueries: [
    { q: "Chipta narxi qancha?", n: 4120, cached: true },
    { q: "Toshkent–Samarqand poyezdi", n: 3380, cached: true },
    { q: "Bagaj qoidalari qanday?", n: 2240, cached: true },
    { q: "Poyezd jadvali", n: 1980, cached: false },
    { q: "Chiptani qaytarish", n: 1510, cached: false },
  ],
};
