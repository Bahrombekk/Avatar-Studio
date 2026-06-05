/* Suzuvchi "Render jarayoni" paneli (Tweaks uslubida, o'ng-pastda) — chiroyli:
   nafas oluvchi avatar, shimmer progress, ovoz to'lqini, bosqichlar ro'yxati,
   aylanuvchi maslahat. Backend opaque → vaqt bo'yicha taxmin. Kichrayadi. */
import { useEffect, useRef, useState } from "react";

export interface ProgItem { id: string; title: string; photo?: string; }

const STAGES = ["Matn tahlil", "Ovoz tayyorlash", "Avatar yuzi", "Lab sinxron", "Video yig'ish"];
const STAGE_T = [4, 11, 16, 26, 9999];
const EST = 28;
const TIPS = [
  "Sonlar va sanalar avtomatik so'z bilan o'qiladi.",
  "Qisqa, aniq jumlalar ravonroq talaffuz beradi.",
  "HD sifat tabiiyroq lab harakatini beradi.",
  "Avatar sanab o'tganda bosh tabiiy nod qiladi.",
  "Urg'uli gaplarda avatar biroz oldinga egiladi.",
];

export function RenderProgress({ items }: { items: ProgItem[] }) {
  const [, tick] = useState(0);
  const [tip, setTip] = useState(0);
  const [min, setMin] = useState(false);
  const starts = useRef<Record<string, number>>({});

  useEffect(() => {
    if (items.length === 0) return;
    const t = window.setInterval(() => tick((x) => x + 1), 1000);
    const f = window.setInterval(() => setTip((i) => (i + 1) % TIPS.length), 4500);
    return () => { window.clearInterval(t); window.clearInterval(f); };
  }, [items.length]);

  const now = Date.now();
  for (const it of items) if (!starts.current[it.id]) starts.current[it.id] = now;
  for (const id of Object.keys(starts.current)) if (!items.find((i) => i.id === id)) delete starts.current[id];

  if (items.length === 0) return null;

  if (min) {
    return (
      <div className="vss-prog min">
        <div className="vss-prog-pill" onClick={() => setMin(false)}>
          <span className="vss-prog-spin" />
          <span className="vss-prog-name">{items.length} ta render…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="vss-prog">
      <div className="vss-prog-head">
        <span className="vss-prog-wave" aria-hidden="true">
          {[0, 1, 2, 3].map((i) => <i key={i} style={{ animationDelay: i * 0.12 + "s" }} />)}
        </span>
        <span className="t">Render jarayoni · {items.length}</span>
        <button className="mini" onClick={() => setMin(true)} title="Kichraytirish">—</button>
      </div>
      <div className="vss-prog-body">
        {items.map((it) => {
          const el = (now - (starts.current[it.id] || now)) / 1000;
          const passed = STAGE_T.filter((t) => el >= t).length;
          const activeIdx = Math.min(passed, STAGES.length - 1);
          const pct = Math.min(94, Math.round((el / EST) * 100));
          return (
            <div className="vss-prog-item" key={it.id}>
              <div className="vss-prog-row">
                {it.photo ? <img className="vss-prog-av" src={it.photo} alt="" /> : <span className="vss-prog-spin" />}
                <span className="vss-prog-name">{it.title || "Nomsiz"}</span>
                <span className="vss-prog-pct">{pct}%</span>
              </div>
              <div className="vss-prog-bar"><div className="vss-prog-fill" style={{ width: pct + "%" }} /></div>
              <ul className="vss-prog-steps">
                {STAGES.map((s, si) => {
                  const st = si < activeIdx ? "done" : si === activeIdx ? "active" : "pending";
                  return (<li className={"vss-prog-step " + st} key={si}><span className="ic">{st === "done" ? "✓" : ""}</span>{s}</li>);
                })}
              </ul>
            </div>
          );
        })}
      </div>
      <div className="vss-prog-tip" key={tip}>{TIPS[tip]}</div>
    </div>
  );
}
