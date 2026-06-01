/* Avatar Studio — umumiy UI primitivlari.
   Barcha vizual tokenlar applyTheme() o'rnatgan CSS-vars'dan keladi.
   Modul import qilinganida bir marta stylesheet inject qilinadi. */
import { I } from "../../lib/icons.jsx";

(function injectUIStyles() {
  if (document.getElementById("as-ui-styles")) return;
  const css = `
  .as-btn{ font-family:var(--font-mono); font-size:11px; font-weight:500;
    text-transform:uppercase; letter-spacing:1.4px; cursor:pointer;
    border-radius:var(--radius); display:inline-flex; align-items:center; gap:8px;
    padding:11px 18px; border:1px solid transparent; transition:.15s; white-space:nowrap; }
  .as-btn.primary{ background:var(--navy); color:var(--on-navy); }
  .as-btn.primary:hover{ background:var(--brass); }
  .as-btn.ghost{ background:transparent; color:var(--ink); border-color:var(--line); }
  .as-btn.ghost:hover{ border-color:var(--brass); color:var(--brass); }
  .as-btn.solid{ background:var(--brass); color:var(--on-navy); }
  .as-btn.solid:hover{ filter:brightness(1.06); }
  .as-btn:disabled{ opacity:.4; cursor:not-allowed; }
  .as-btn svg{ width:14px; height:14px; }

  .as-badge{ font-family:var(--font-mono); font-size:9px; font-weight:500;
    text-transform:uppercase; letter-spacing:1.3px; padding:4px 9px;
    border-radius:20px; display:inline-flex; align-items:center; gap:6px;
    border:1px solid var(--line); color:var(--ink-2); }
  .as-badge .dot{ width:6px; height:6px; border-radius:50%; }

  .as-card{ background:var(--card); border:1px solid var(--line);
    border-radius:var(--radius-lg); }

  .as-label{ font-family:var(--font-mono); font-size:9.5px; font-weight:500;
    text-transform:uppercase; letter-spacing:1.5px; color:var(--ink-2); }

  .as-field{ width:100%; background:var(--bg); border:1px solid var(--line);
    border-radius:var(--radius); padding:11px 13px; font-family:var(--font-body);
    font-size:14px; color:var(--ink); outline:none; transition:.15s; }
  .as-field:focus{ border-color:var(--brass); box-shadow:0 0 0 3px color-mix(in srgb, var(--brass) 16%, transparent); }
  .as-field::placeholder{ color:var(--ink-3); }
  textarea.as-field{ resize:vertical; line-height:1.5; }

  .as-toggle{ width:42px; height:24px; border-radius:20px; background:var(--line);
    position:relative; cursor:pointer; transition:.18s; flex:none; border:1px solid var(--line); }
  .as-toggle.on{ background:var(--brass); border-color:var(--brass); }
  .as-toggle .knob{ position:absolute; top:2px; left:2px; width:18px; height:18px;
    border-radius:50%; background:#fff; transition:.18s; box-shadow:0 1px 3px rgba(0,0,0,.3); }
  .as-toggle.on .knob{ transform:translateX(18px); }

  .as-seg{ display:inline-flex; background:var(--panel-2); border:1px solid var(--line);
    border-radius:var(--radius); padding:3px; gap:3px; }
  .as-seg button{ font-family:var(--font-mono); font-size:10px; font-weight:500;
    text-transform:uppercase; letter-spacing:1px; padding:7px 13px; border:0;
    background:transparent; color:var(--ink-2); cursor:pointer; border-radius:calc(var(--radius) - 1px); transition:.12s; }
  .as-seg button.on{ background:var(--card); color:var(--ink); box-shadow:var(--shadow-sm); }

  .as-range{ -webkit-appearance:none; appearance:none; width:100%; height:3px;
    background:var(--line); border-radius:3px; outline:none; }
  .as-range::-webkit-slider-thumb{ -webkit-appearance:none; width:16px; height:16px;
    border-radius:50%; background:var(--brass); cursor:pointer; border:2px solid var(--card); box-shadow:var(--shadow-sm); }
  .as-range::-moz-range-thumb{ width:16px; height:16px; border-radius:50%;
    background:var(--brass); cursor:pointer; border:2px solid var(--card); }

  .as-scroll::-webkit-scrollbar{ width:6px; height:6px; }
  .as-scroll::-webkit-scrollbar-thumb{ background:var(--line); border-radius:4px; }
  .as-scroll::-webkit-scrollbar-track{ background:transparent; }
  `;
  const el = document.createElement("style");
  el.id = "as-ui-styles";
  el.textContent = css;
  document.head.appendChild(el);
})();

export const STATUS = {
  live:   { label: "Faol",    color: "var(--ok)" },
  draft:  { label: "Qoralama",color: "var(--ink-3)" },
  paused: { label: "To‘xtatilgan", color: "var(--warn)" },
};

export function Btn({ kind = "ghost", icon, children, ...rest }) {
  const Ico = icon ? I[icon] : null;
  return (
    <button className={"as-btn " + kind} {...rest}>
      {Ico && <Ico />}{children}
    </button>
  );
}

export function Badge({ color, children }) {
  return (
    <span className="as-badge">
      {color && <span className="dot" style={{ background: color }} />}
      {children}
    </span>
  );
}

export function StatusBadge({ status }) {
  const s = STATUS[status] || STATUS.draft;
  return <Badge color={s.color}>{s.label}</Badge>;
}

export function Card({ style, className = "", children, ...rest }) {
  return <div className={"as-card " + className} style={style} {...rest}>{children}</div>;
}

export function Field({ label, hint, children }) {
  return (
    <label style={{ display: "block" }}>
      {label && <div className="as-label" style={{ marginBottom: 8 }}>{label}</div>}
      {children}
      {hint && <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-3)", marginTop: 7, letterSpacing: ".3px" }}>{hint}</div>}
    </label>
  );
}

export function Toggle({ on, onChange }) {
  return (
    <div className={"as-toggle" + (on ? " on" : "")} onClick={() => onChange(!on)}>
      <div className="knob" />
    </div>
  );
}

export function Segmented({ value, options, onChange }) {
  return (
    <div className="as-seg">
      {options.map((o) => {
        const val = typeof o === "string" ? o : o.value;
        const lab = typeof o === "string" ? o : o.label;
        return (
          <button key={val} className={value === val ? "on" : ""} onClick={() => onChange(val)}>{lab}</button>
        );
      })}
    </div>
  );
}

export function Range({ value, min, max, step = 1, onChange }) {
  return (
    <input type="range" className="as-range" value={value} min={min} max={max} step={step}
      onChange={(e) => onChange(parseFloat(e.target.value))} />
  );
}

// Bosh harflari bilan gradient portret — real avatar foto uchun placeholder.
export function Portrait({ avatar, size = 48, radius = "var(--radius)", live = false }) {
  const p = avatar.portrait;
  return (
    <div style={{
      width: size, height: size, borderRadius: radius, flex: "none",
      background: `linear-gradient(150deg, ${p.from}, ${p.to})`,
      display: "flex", alignItems: "center", justifyContent: "center",
      color: "rgba(255,255,255,.92)", fontFamily: "var(--font-display)",
      fontSize: size * 0.42, fontStyle: "italic", position: "relative",
      boxShadow: "inset 0 1px 0 rgba(255,255,255,.15)",
    }}>
      {p.initials}
      {live && <span style={{ position: "absolute", right: size*0.06, bottom: size*0.06, width: Math.max(7,size*0.13), height: Math.max(7,size*0.13), borderRadius: "50%", background: "var(--ok)", border: "2px solid var(--card)" }} />}
    </div>
  );
}
