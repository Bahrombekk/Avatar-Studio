/* Sozlamalar route — platforma modullarini yoqish/o'chirish. */
import { useEffect, useState } from "react";
import { Topbar } from "@/components/AdminShell";
import { Card, Toggle } from "@/components/ui";
import { useTweaksCtx } from "@/context/TweaksContext";
import { API } from "@/api/client";

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
  const [perf, setPerf] = useState<string>("");
  const [perfBusy, setPerfBusy] = useState(false);
  const [perfErr, setPerfErr] = useState<string>("");

  useEffect(() => {
    API.getPerf()
      .then((p) => setPerf(p.preset))
      .catch(() => setPerf(""));
  }, []);

  async function changePerf(preset: "light" | "heavy") {
    if (perfBusy || perf === preset) return;
    setPerfBusy(true);
    setPerfErr("");
    try {
      const r = await API.setPerf(preset);
      setPerf(r.preset);
    } catch (e) {
      setPerfErr(e instanceof Error ? e.message : "xato");
    } finally {
      setPerfBusy(false);
    }
  }

  const PERF = [
    { k: "heavy", label: "Og‘ir (yuqori sifat)", desc: "To‘liq rezolyutsiya — RTX 5090 kabi kuchli GPU uchun." },
    { k: "light", label: "Yengil (tez)", desc: "Past rezolyutsiya — zaif GPU / DGX Spark uchun ravon." },
  ] as const;

  return (
    <div className="pg as-scroll">
      <Topbar
        title="Sozlamalar"
        sub="Platforma modullarini yoqing yoki o‘chiring"
      />
      <div className="pg-body">
        <Card style={{ maxWidth: 640, marginBottom: 16 }}>
          <div className="set-row" style={{ borderTop: "none" }}>
            <div>
              <div className="set-row-t">Ishlash rejimi</div>
              <div className="set-row-d">
                Apparatga qarab yuk darajasini tanlang (sifat-model o‘zgarmaydi).
                {perfErr && <span style={{ color: "#c0392b" }}> — {perfErr}</span>}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, padding: "0 4px 4px" }}>
            {PERF.map((p) => (
              <button
                key={p.k}
                onClick={() => changePerf(p.k)}
                disabled={perfBusy}
                title={p.desc}
                style={{
                  flex: 1,
                  padding: "10px 12px",
                  borderRadius: 8,
                  cursor: perfBusy ? "wait" : "pointer",
                  textAlign: "left",
                  border: perf === p.k ? "2px solid var(--accent, #0F2540)" : "1px solid var(--line)",
                  background: perf === p.k ? "var(--accent-soft, #eef3fb)" : "transparent",
                  fontWeight: perf === p.k ? 600 : 400,
                }}
              >
                <div>{p.label}</div>
                <div style={{ fontSize: 12, opacity: 0.7, marginTop: 2 }}>{p.desc}</div>
              </button>
            ))}
          </div>
        </Card>
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
