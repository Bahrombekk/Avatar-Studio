/* Avatar Studio — App router + Tweaks. */
import { useState, useEffect } from "react";
import {
  useTweaks, TweaksPanel, TweakSection, TweakSelect, TweakToggle,
} from "./components/tweaks/TweaksPanel.jsx";
import { applyTheme, THEMES, FONT_SETS } from "./lib/theme.js";
import { API } from "./api/client.js";
import { I } from "./lib/icons.jsx";
import { Sidebar, Topbar, Dashboard } from "./components/AdminShell.jsx";
import { Analytics } from "./pages/Analytics.jsx";
import { AvatarEditor } from "./pages/AvatarEditor.jsx";
import { ChatScreen } from "./pages/ChatScreen.jsx";
import { Card, Toggle, Badge } from "./components/ui/index.jsx";

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "editorial",
  "fontSet": "editorial",
  "secConversations": true,
  "secUsers": true,
  "secSettings": true,
  "showTiming": true,
  "showSuggestions": true
}/*EDITMODE-END*/;

export default function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [avatars, setAvatars] = useState([]);
  const [route, setRoute] = useState({ screen: "dashboard" });
  const go = (r) => setRoute(r);

  useEffect(() => { applyTheme(t.theme, t.fontSet); }, [t.theme, t.fontSet]);

  // Avatarlarni real backend'dan yuklash.
  const reload = () => API.listAvatars().then(setAvatars).catch((e) => console.error(e));
  useEffect(() => { reload(); }, []);

  const flags = { conversations: t.secConversations, users: t.secUsers, settings: t.secSettings };

  async function saveAvatar(draft) {
    try {
      const isNew = !draft.id || draft.id === "new";
      if (isNew) {
        const { id, ...payload } = draft;
        await API.createAvatar(payload);
      } else {
        await API.updateAvatar(draft.id, draft);
      }
      await reload();
    } catch (e) { console.error(e); alert("Saqlashda xatolik: " + e.message); }
    setRoute({ screen: "dashboard" });
  }

  async function deleteAvatar(id) {
    try { await API.deleteAvatar(id); await reload(); }
    catch (e) { console.error(e); alert("O'chirishda xatolik: " + e.message); }
    setRoute({ screen: "dashboard" });
  }

  const editing = route.screen === "editor"
    ? (route.id === "new" ? null : avatars.find((a) => a.id === route.id))
    : null;
  const previewAvatar = route.id ? avatars.find((a) => a.id === route.id) : avatars.find((a) => a.status === "live") || avatars[0];

  // Preview = standalone full-bleed chat (no admin chrome)
  if (route.screen === "preview") {
    return (
      <>
        <div className="pv-wrap">
          <button className="pv-back" onClick={() => go({ screen: "dashboard" })}><I.back size={15} /> Studiyaga qaytish</button>
          <div className="pv-stage">
            <ChatScreen avatar={withTweaks(previewAvatar, t)} embedded />
          </div>
        </div>
        <StudioTweaks t={t} setTweak={setTweak} />
      </>
    );
  }

  return (
    <div className="app">
      <Sidebar route={route} go={go} flags={flags} />
      <div className="app-main">
        {route.screen === "dashboard" && <Dashboard avatars={avatars} go={go} />}
        {route.screen === "analytics" && <Analytics avatars={avatars} />}
        {route.screen === "editor"    && <AvatarEditor base={editing} onSave={saveAvatar} onDelete={deleteAvatar} onCancel={() => go({ screen: "dashboard" })} go={go} />}
        {route.screen === "conversations" && <Placeholder icon="chat" title="Suhbatlar" desc="Barcha avatarlar bo‘yicha suhbatlar tarixi va transkriptlar shu yerda bo‘ladi." />}
        {route.screen === "users"     && <Placeholder icon="users" title="Foydalanuvchilar" desc="Jamoa a’zolari, rollar va ruxsatlar boshqaruvi." />}
        {route.screen === "settings"  && <SettingsScreen t={t} setTweak={setTweak} />}
      </div>
      <StudioTweaks t={t} setTweak={setTweak} />
    </div>
  );
}

// Apply visual tweaks that affect the chat (suggestions toggle).
function withTweaks(av, t) {
  if (!av) return av;
  return { ...av, suggestions: t.showSuggestions ? av.suggestions : [] };
}

function Placeholder({ icon, title, desc }) {
  const Ico = I[icon];
  return (
    <div className="pg">
      <Topbar title={title} />
      <div className="ph">
        <div className="ph-ico"><Ico size={30} /></div>
        <div className="ph-t">{title}</div>
        <div className="ph-d">{desc}</div>
        <Badge color="var(--ink-3)">Tez orada</Badge>
      </div>
    </div>
  );
}

function SettingsScreen({ t, setTweak }) {
  const rows = [
    { k: "secConversations", label: "Suhbatlar bo‘limi", desc: "Yon menyuda suhbatlar tarixini ko‘rsatish." },
    { k: "secUsers", label: "Foydalanuvchilar bo‘limi", desc: "Jamoa va ruxsatlar boshqaruvi." },
    { k: "showTiming", label: "Latency ko‘rsatkichi", desc: "Chat ekranida javob vaqtini ko‘rsatish." },
    { k: "showSuggestions", label: "Tezkor javoblar", desc: "Chat boshida tavsiya tugmalari." },
  ];
  return (
    <div className="pg as-scroll">
      <Topbar title="Sozlamalar" sub="Platforma moduллarini yoqing yoki o‘chiring" />
      <div className="pg-body">
        <Card style={{ maxWidth: 640 }}>
          {rows.map((r, i) => (
            <div key={r.k} className="set-row" style={{ borderTop: i ? "1px solid var(--line)" : "none" }}>
              <div>
                <div className="set-row-t">{r.label}</div>
                <div className="set-row-d">{r.desc}</div>
              </div>
              <Toggle on={t[r.k]} onChange={(v) => setTweak(r.k, v)} />
            </div>
          ))}
        </Card>
      </div>
    </div>
  );
}

/* ── Tweaks panel ── */
function StudioTweaks({ t, setTweak }) {
  return (
    <TweaksPanel>
      <TweakSection label="Ko‘rinish" />
      <TweakSelect label="Tema" value={t.theme}
        options={Object.keys(THEMES).map((k) => ({ value: k, label: THEMES[k].label }))}
        onChange={(v) => setTweak("theme", v)} />
      <TweakSelect label="Shrift" value={t.fontSet}
        options={Object.keys(FONT_SETS).map((k) => ({ value: k, label: FONT_SETS[k].label }))}
        onChange={(v) => setTweak("fontSet", v)} />
      <TweakSection label="Chat ekrani" />
      <TweakToggle label="Latency ko‘rsatkichi" value={t.showTiming} onChange={(v) => setTweak("showTiming", v)} />
      <TweakToggle label="Tezkor javoblar" value={t.showSuggestions} onChange={(v) => setTweak("showSuggestions", v)} />
      <TweakSection label="Admin modullari" />
      <TweakToggle label="Suhbatlar bo‘limi" value={t.secConversations} onChange={(v) => setTweak("secConversations", v)} />
      <TweakToggle label="Foydalanuvchilar bo‘limi" value={t.secUsers} onChange={(v) => setTweak("secUsers", v)} />
      <TweakToggle label="Sozlamalar bo‘limi" value={t.secSettings} onChange={(v) => setTweak("secSettings", v)} />
    </TweaksPanel>
  );
}
