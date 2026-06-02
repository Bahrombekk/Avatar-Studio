/* Avatar Studio — backend ko'prigi (real lp_musetalk API, port 8100).
   Prod'da bir xil origin (/studio), dev'da Vite proksisi orqali. */
export const API = {
  async listAvatars() {
    const r = await fetch("/api/avatars");
    if (!r.ok) throw new Error("avatars yuklanmadi");
    return (await r.json()).avatars;
  },
  async createAvatar(data) {
    const r = await fetch("/api/avatars", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!r.ok) throw new Error("yaratilmadi");
    return await r.json();
  },
  async updateAvatar(id, data) {
    const r = await fetch("/api/avatars/" + encodeURIComponent(id), {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!r.ok) throw new Error("yangilanmadi");
    return await r.json();
  },
  async deleteAvatar(id) {
    const r = await fetch("/api/avatars/" + encodeURIComponent(id), { method: "DELETE" });
    if (!r.ok) throw new Error("o'chirilmadi");
    return await r.json();
  },
  // Portret rasmini yuklash (multipart). Backend yuzni tekshiradi.
  async uploadPhoto(id, file) {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch("/api/avatars/" + encodeURIComponent(id) + "/photo", {
      method: "POST", body: fd,
    });
    if (!r.ok) {
      let msg = "rasm yuklanmadi";
      try { const e = await r.json(); if (e.detail) msg = e.detail; } catch { /* ignore */ }
      throw new Error(msg);
    }
    return await r.json();
  },
  // Saqlangan portret URL'i (cache buzish uchun versiya bilan).
  photoUrl(id, ver) {
    return "/api/avatars/" + encodeURIComponent(id) + "/photo?v=" + (ver || 0);
  },
  // Idle (blink) video generatsiyani boshlash (fon job).
  async buildIdle(id) {
    const r = await fetch("/api/avatars/" + encodeURIComponent(id) + "/build-idle", { method: "POST" });
    if (!r.ok) {
      let msg = "idle yaratilmadi";
      try { const e = await r.json(); if (e.detail) msg = e.detail; } catch { /* ignore */ }
      throw new Error(msg);
    }
    return await r.json();
  },
  // MuseTalk artefakt (latents/coords/mask) generatsiyani boshlash (fon job).
  async buildMusetalk(id) {
    const r = await fetch("/api/avatars/" + encodeURIComponent(id) + "/build-musetalk", { method: "POST" });
    if (!r.ok) {
      let msg = "artefakt yaratilmadi";
      try { const e = await r.json(); if (e.detail) msg = e.detail; } catch { /* ignore */ }
      throw new Error(msg);
    }
    return await r.json();
  },
  // Generatsiya holati (polling).
  async buildStatus(id) {
    const r = await fetch("/api/avatars/" + encodeURIComponent(id) + "/build");
    if (!r.ok) throw new Error("holat olinmadi");
    return await r.json();
  },
  // Generatsiya qilingan idle video URL'i.
  idleUrl(id, ver) {
    return "/api/avatars/" + encodeURIComponent(id) + "/idle?v=" + (ver || 0);
  },
  async analytics() {
    const r = await fetch("/api/analytics");
    if (!r.ok) throw new Error("analitika yuklanmadi");
    return await r.json();
  },
  async voices() {
    const r = await fetch("/voices");
    if (!r.ok) throw new Error("ovozlar yuklanmadi");
    return await r.json();
  },
  // Real pipeline: SSE oqimi. onEvent(type, data) chaqiriladi.
  chatStream(message, avatarId, voice, onEvent) {
    return fetch("/chat-stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, avatar_id: avatarId, voice }),
    }).then(async (resp) => {
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop();
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            const obj = JSON.parse(line.slice(5).trim());
            onEvent(obj.type, obj);
          } catch (e) { /* ignore */ }
        }
      }
    });
  },
};
