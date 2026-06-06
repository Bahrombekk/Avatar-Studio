/* Suhbat, ovoz va til tiplari. */

export type VoiceProvider = "edge" | "yandex" | "yandex_v3" | string;

export interface Voice {
  id: string;
  label?: string;          // /voices runtime maydoni (ko'rsatish uchun)
  name?: string;
  lang?: string;
  langCode?: string;
  gender?: string;
  tag?: string;
  provider: VoiceProvider;
}

export interface Language {
  code: string;
  label: string;
  native: string;
  flag: string;
}

export type ChatRole = "bot" | "user";

export interface ChatMessage {
  role: ChatRole;
  text: string;
  time?: string;
}

/** /chat-stream SSE hodisasi. `type` maydoni hodisa turini bildiradi. */
export interface ChatStreamEvent {
  type: string;
  [key: string]: unknown;
}

export type ChatStreamHandler = (type: string, data: ChatStreamEvent) => void;
