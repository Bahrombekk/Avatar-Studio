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
