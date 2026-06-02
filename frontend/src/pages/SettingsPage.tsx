/* Sozlamalar route — platforma modullarini yoqish/o'chirish. */
import { Topbar } from "@/components/AdminShell";
import { Card, Toggle } from "@/components/ui";
import { useTweaksCtx } from "@/context/TweaksContext";

const ROWS = [
  {
    k: "secConversations",
    label: "Suhbatlar bo‘limi",
    desc: "Yon menyuda suhbatlar tarixini ko‘rsatish.",
  },
  {
    k: "secUsers",
    label: "Foydalanuvchilar bo‘limi",
    desc: "Jamoa va ruxsatlar boshqaruvi.",
  },
  {
    k: "showTiming",
    label: "Latency ko‘rsatkichi",
    desc: "Chat ekranida javob vaqtini ko‘rsatish.",
  },
  {
    k: "showSuggestions",
    label: "Tezkor javoblar",
    desc: "Chat boshida tavsiya tugmalari.",
  },
];

export function SettingsPage() {
  const { t, setTweak } = useTweaksCtx();
  return (
    <div className="pg as-scroll">
      <Topbar
        title="Sozlamalar"
        sub="Platforma modullarini yoqing yoki o‘chiring"
      />
      <div className="pg-body">
        <Card style={{ maxWidth: 640 }}>
          {ROWS.map((r, i) => (
            <div
              key={r.k}
              className="set-row"
              style={{ borderTop: i ? "1px solid var(--line)" : "none" }}
            >
              <div>
                <div className="set-row-t">{r.label}</div>
                <div className="set-row-d">{r.desc}</div>
              </div>
              <Toggle
                on={Boolean(t[r.k])}
                onChange={(v: boolean) => setTweak(r.k, v)}
              />
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}
