/* Avatar Studio — Admin chrome (sidebar + topbar) va Dashboard. */
import { useState } from "react";
import { I } from "../lib/icons";
import { Btn, Card, Segmented, Portrait, StatusBadge } from "./ui/index.jsx";
import { useAuth } from "@/context/AuthContext";

const NAV = [
  { id: "dashboard", label: "Avatarlar", icon: "grid" },
  { id: "studio", label: "Video Studiya", icon: "play" },
  { id: "analytics", label: "Analitika", icon: "chart" },
  { id: "conversations", label: "Suhbatlar", icon: "chat", flag: "conversations" },
  { id: "users", label: "Foydalanuvchilar", icon: "users", flag: "users" },
  { id: "settings", label: "Sozlamalar", icon: "settings", flag: "settings" },
];

export function Sidebar({ route, go, flags }) {
  const { logout } = useAuth();
  return (
    <aside className="sb">
      <div className="sb-brand">
        <div className="sb-logo"><I.layers size={17} /></div>
        <div>
          <div className="sb-logo-name">Avatar Studio</div>
          <div className="sb-logo-sub">UTY · Platforma</div>
        </div>
      </div>

      <div className="sb-section">Boshqaruv</div>
      <nav className="sb-nav">
        {NAV.filter((n) => !n.flag || flags[n.flag]).map((n) => {
          const Ico = I[n.icon];
          const active = route.screen === n.id || (n.id === "dashboard" && route.screen === "editor");
          return (
            <button key={n.id} className={"sb-item" + (active ? " on" : "")} onClick={() => go({ screen: n.id })}>
              <Ico size={17} />{n.label}
            </button>
          );
        })}
      </nav>

      <div className="sb-spacer" />

      <button className="sb-preview" onClick={() => go({ screen: "preview" })}>
        <I.eye size={15} /> Jonli ko‘rinish
      </button>
      <a className="sb-preview" href="/" style={{ marginTop: 8, textDecoration: "none" }}>
        <I.mic size={15} /> User sahifa
      </a>

      <div className="sb-foot">
        <div className="sb-acct">
          <div className="sb-acct-av">A</div>
          <div>
            <div className="sb-acct-name">Admin</div>
            <div className="sb-acct-mail">studio@uty.uz</div>
          </div>
          <button className="sb-logout" title="Chiqish" onClick={logout}>
            <I.x size={15} />
          </button>
        </div>
      </div>
    </aside>
  );
}

/** @param {{ title?: any, sub?: any, actions?: any }} props */
export function Topbar({ title, sub, actions }) {
  return (
    <header className="tb">
      <div>
        <div className="tb-title">{title}</div>
        {sub && <div className="tb-sub">{sub}</div>}
      </div>
      <div className="tb-actions">{actions}</div>
    </header>
  );
}

/* ── Dashboard ─────────────────────────────────────── */
export function Dashboard({ avatars, go }) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const list = avatars.filter((a) => {
    if (filter !== "all" && a.status !== filter) return false;
    if (q && !(a.name + a.brand + a.role).toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });

  const totals = {
    live: avatars.filter((a) => a.status === "live").length,
    sessions: avatars.reduce((s, a) => s + a.sessions, 0),
    brands: new Set(avatars.map((a) => a.brand)).size,
  };

  return (
    <div className="pg as-scroll">
      <Topbar title="Avatarlar" sub={`${avatars.length} ta avatar · ${totals.brands} brend`}
        actions={<Btn kind="primary" icon="plus" onClick={() => go({ screen: "editor", id: "new" })}>Yangi avatar</Btn>} />

      <div className="pg-body">
        <div className="dash-stats">
          {[
            { k: "Faol avatarlar", v: totals.live, ico: "dot", c: "var(--ok)" },
            { k: "Jami sessiyalar", v: totals.sessions.toLocaleString("ru"), ico: "chat", c: "var(--brass)" },
            { k: "Brendlar", v: totals.brands, ico: "layers", c: "var(--navy)" },
            { k: "O‘rtacha latency", v: "2.4s", ico: "bolt", c: "var(--brass-2)" },
          ].map((s) => {
            const Ico = I[s.ico];
            return (
              <Card key={s.k} className="dash-stat">
                <div className="dash-stat-ico" style={{ color: s.c }}><Ico size={16} /></div>
                <div className="dash-stat-v">{s.v}</div>
                <div className="as-label">{s.k}</div>
              </Card>
            );
          })}
        </div>

        <div className="dash-toolbar">
          <div className="dash-search">
            <I.search size={15} />
            <input placeholder="Avatar yoki brend qidirish…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Segmented value={filter} onChange={setFilter}
            options={[{value:"all",label:"Hammasi"},{value:"live",label:"Faol"},{value:"draft",label:"Qoralama"},{value:"paused",label:"To‘xtab"}]} />
        </div>

        <div className="dash-grid">
          {list.map((a) => <AvatarCard key={a.id} a={a} go={go} />)}
          <button className="dash-add" onClick={() => go({ screen: "editor", id: "new" })}>
            <div className="dash-add-ico"><I.plus size={22} /></div>
            <div className="dash-add-t">Yangi avatar yaratish</div>
            <div className="dash-add-s">Rasm · ovoz · til · personality</div>
          </button>
        </div>
      </div>
    </div>
  );
}

function AvatarCard({ a, go }) {
  return (
    <Card className="av-card" onClick={() => go({ screen: "editor", id: a.id })}>
      <div className="av-card-top">
        <Portrait avatar={a} size={52} radius="10px" live={a.status === "live"} />
        <div className="av-card-top-r">
          <StatusBadge status={a.status} />
          <span className={"av-card-model" + (a.real ? " on" : "")}
            title={a.real ? "Avatar modeli tayyor (o‘z yuzi bilan lip-sync)" : "Model yo‘q — Idle + Artefakt yarating"}>
            {a.real ? <I.check size={11} /> : <I.bolt size={11} />}
            {a.real ? "Model tayyor" : "Model yo‘q"}
          </span>
        </div>
      </div>
      <div className="av-card-name">{a.name}</div>
      <div className="av-card-role">{a.role}</div>
      <div className="av-card-brand"><span style={{ width:6,height:6,borderRadius:"50%",background:a.accent,display:"inline-block" }} />{a.brand}</div>
      <div className="av-card-stats">
        <div><div className="av-card-stat-v">{a.sessions ? a.sessions.toLocaleString("ru") : "—"}</div><div className="as-label" style={{fontSize:8}}>sessiya</div></div>
        <div><div className="av-card-stat-v">{a.csat ? a.csat.toFixed(1) : "—"}</div><div className="as-label" style={{fontSize:8}}>CSAT</div></div>
        <div><div className="av-card-stat-v">{a.avgLatency ? a.avgLatency+"s" : "—"}</div><div className="as-label" style={{fontSize:8}}>latency</div></div>
      </div>
      <div className="av-card-foot">
        <span className="av-card-upd">Yangilangan {a.updated}</span>
        <span className="av-card-go">Ochish <I.chevron size={13} /></span>
      </div>
    </Card>
  );
}
