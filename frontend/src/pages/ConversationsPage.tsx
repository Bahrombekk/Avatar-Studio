/* Suhbatlar — saqlangan transkriptlar (master-detail). Chapda ro'yxat, o'ngda xabarlar. */
import { useEffect, useState } from "react";
import { API, type Conversation, type ConversationMessage } from "@/api/client";
import { useToast } from "@/context/ToastContext";

export function ConversationsPage() {
  const { toast } = useToast();
  const [items, setItems] = useState<Conversation[]>([]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.conversations()
      .then((c) => setItems(c))
      .catch((e) => toast(e.message || "yuklanmadi", "error"))
      .finally(() => setLoading(false));
  }, [toast]);

  const open = (id: number) => {
    setOpenId(id);
    setMessages([]);
    API.conversation(id)
      .then((d) => setMessages(d.messages))
      .catch((e) => toast(e.message || "yuklanmadi", "error"));
  };

  return (
    <div className="conv-page" style={{ display: "flex", gap: 16, padding: 16, height: "100%" }}>
      <div className="conv-list" style={{ flex: "0 0 320px", overflow: "auto" }}>
        <h2 style={{ marginTop: 0 }}>Suhbatlar</h2>
        {loading && <p>Yuklanmoqda…</p>}
        {!loading && !items.length && <p>Hozircha suhbat yo‘q.</p>}
        {items.map((c) => (
          <button
            key={c.id}
            onClick={() => open(c.id)}
            className={"conv-item" + (openId === c.id ? " on" : "")}
            style={{
              display: "block", width: "100%", textAlign: "left", padding: "10px 12px",
              marginBottom: 6, border: "1px solid var(--line)", borderRadius: "var(--radius)",
              background: openId === c.id ? "var(--card)" : "transparent", cursor: "pointer",
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 13 }}>
              {c.avatar_id || c.session_key.slice(0, 12)}
            </div>
            <div style={{ fontSize: 12, opacity: 0.7, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {c.last_text || "—"}
            </div>
            <div style={{ fontSize: 11, opacity: 0.5 }}>
              {c.msg_count} xabar · {new Date(c.updated).toLocaleString()}
            </div>
          </button>
        ))}
      </div>

      <div className="conv-detail" style={{ flex: 1, overflow: "auto" }}>
        {openId === null && <p style={{ opacity: 0.6 }}>Transkriptni ko‘rish uchun suhbatni tanlang.</p>}
        {openId !== null && !messages.length && <p>Yuklanmoqda…</p>}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              marginBottom: 10, padding: "8px 12px", borderRadius: "var(--radius)",
              background: m.role === "user" ? "var(--card)" : "var(--panel)",
              borderLeft: `3px solid ${m.role === "user" ? "var(--navy)" : "var(--brass)"}`,
            }}
          >
            <div style={{ fontSize: 11, opacity: 0.6, marginBottom: 2 }}>
              {m.role === "user" ? "Foydalanuvchi" : "Avatar"} · {new Date(m.ts).toLocaleTimeString()}
            </div>
            <div style={{ fontSize: 14 }}>{m.text}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
