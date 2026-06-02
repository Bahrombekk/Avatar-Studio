/* Avatar Studio — backend ko'prigi (real lp_musetalk API, port 8100).
   Prod'da bir xil origin (/studio), dev'da Vite proksisi orqali. */
import type { Avatar, AvatarDraft, BuildStatus } from "@/types/avatar";
import type { Voice, ChatStreamHandler } from "@/types/chat";
import type { Analytics } from "@/types/analytics";

/** Xato javobidan `detail` xabarini ajratib oladi (bo'lmasa fallback). */
async function errorDetail(r: Response, fallback: string): Promise<string> {
  try {
    const e = (await r.json()) as { detail?: string };
    if (e.detail) return e.detail;
  } catch {
    /* ignore */
  }
  return fallback;
}

export const API = {
  async listAvatars(): Promise<Avatar[]> {
    const r = await fetch("/api/avatars");
    if (!r.ok) throw new Error("avatars yuklanmadi");
    return ((await r.json()) as { avatars: Avatar[] }).avatars;
  },

  async createAvatar(data: AvatarDraft): Promise<Avatar> {
    const r = await fetch("/api/avatars", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!r.ok) throw new Error("yaratilmadi");
    return (await r.json()) as Avatar;
  },

  async updateAvatar(id: string, data: Partial<Avatar>): Promise<Avatar> {
    const r = await fetch("/api/avatars/" + encodeURIComponent(id), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!r.ok) throw new Error("yangilanmadi");
    return (await r.json()) as Avatar;
  },

  async deleteAvatar(id: string): Promise<{ ok: boolean }> {
    const r = await fetch("/api/avatars/" + encodeURIComponent(id), {
      method: "DELETE",
    });
    if (!r.ok) throw new Error("o'chirilmadi");
    return (await r.json()) as { ok: boolean };
  },

  // Portret rasmini yuklash (multipart). Backend yuzni tekshiradi.
  async uploadPhoto(id: string, file: File): Promise<Avatar> {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/avatars/" + encodeURIComponent(id) + "/photo", {
      method: "POST",
      body: fd,
    });
    if (!r.ok) throw new Error(await errorDetail(r, "rasm yuklanmadi"));
    return (await r.json()) as Avatar;
  },

  // Saqlangan portret URL'i (cache buzish uchun versiya bilan).
  photoUrl(id: string, ver?: number): string {
    return "/api/avatars/" + encodeURIComponent(id) + "/photo?v=" + (ver || 0);
  },

  // Idle (blink) video generatsiyani boshlash (fon job).
  async buildIdle(id: string): Promise<{ ok: boolean; state: string }> {
    const r = await fetch(
      "/api/avatars/" + encodeURIComponent(id) + "/build-idle",
      { method: "POST" },
    );
    if (!r.ok) throw new Error(await errorDetail(r, "idle yaratilmadi"));
    return (await r.json()) as { ok: boolean; state: string };
  },

  // MuseTalk artefakt (latents/coords/mask) generatsiyani boshlash (fon job).
  async buildMusetalk(
    id: string,
  ): Promise<{ ok: boolean; state: string; stage: string }> {
    const r = await fetch(
      "/api/avatars/" + encodeURIComponent(id) + "/build-musetalk",
      { method: "POST" },
    );
    if (!r.ok) throw new Error(await errorDetail(r, "artefakt yaratilmadi"));
    return (await r.json()) as { ok: boolean; state: string; stage: string };
  },

  // Generatsiya holati (polling).
  async buildStatus(id: string): Promise<BuildStatus> {
    const r = await fetch("/api/avatars/" + encodeURIComponent(id) + "/build");
    if (!r.ok) throw new Error("holat olinmadi");
    return (await r.json()) as BuildStatus;
  },

  // Generatsiya qilingan idle video URL'i.
  idleUrl(id: string, ver?: number): string {
    return "/api/avatars/" + encodeURIComponent(id) + "/idle?v=" + (ver || 0);
  },

  async analytics(): Promise<Analytics> {
    const r = await fetch("/api/analytics");
    if (!r.ok) throw new Error("analitika yuklanmadi");
    return (await r.json()) as Analytics;
  },

  async voices(): Promise<Voice[]> {
    const r = await fetch("/voices");
    if (!r.ok) throw new Error("ovozlar yuklanmadi");
    return (await r.json()) as Voice[];
  },

  // Real pipeline: SSE oqimi. onEvent(type, data) chaqiriladi.
  chatStream(
    message: string,
    avatarId: string,
    voice: string,
    onEvent: ChatStreamHandler,
  ): Promise<void> {
    return fetch("/chat-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, avatar_id: avatarId, voice }),
    }).then(async (resp) => {
      if (!resp.body) throw new Error("oqim ochilmadi");
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            const obj = JSON.parse(line.slice(5).trim());
            onEvent(obj.type, obj);
          } catch {
            /* ignore */
          }
        }
      }
    });
  },
};
