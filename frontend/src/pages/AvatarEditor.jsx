/* Avatar Studio — Avatar muharriri (yaratish + barcha sozlamalar).
   Chapda tabli sozlamalar, o'ngda yopishqoq jonli ko'rinish. */
import { useState } from "react";
import { I } from "../lib/icons.jsx";
import { Btn, Field, Segmented, Range } from "../components/ui/index.jsx";
import { Topbar } from "../components/AdminShell.jsx";
import { VOICES, LANGUAGES } from "../data/constants.js";

const EDITOR_TABS = [
  { id: "portrait", label: "Portret", icon: "image" },
  { id: "voice", label: "Ovoz & Til", icon: "mic" },
  { id: "persona", label: "Personality", icon: "message" },
  { id: "motion", label: "Idle & Lip-sync", icon: "sliders" },
  { id: "sugg", label: "Tezkor javoblar", icon: "bolt" },
  { id: "brand", label: "Brending", icon: "palette" },
];

const GRADIENTS = [
  { from: "#1C3A5E", to: "#0F2540" }, { from: "#16624A", to: "#0C3A2C" },
  { from: "#2A6FDB", to: "#16407F" }, { from: "#A23B30", to: "#5E211A" },
  { from: "#6D4AA0", to: "#3B2566" }, { from: "#B07A2E", to: "#6E4715" },
];
const ACCENTS = ["#B98944", "#1F8A5B", "#2A6FDB", "#C0392B", "#6D4AA0", "#0F2540"];

export function AvatarEditor({ base, onSave, onDelete, onCancel, go }) {
  const isNew = !base;
  const [draft, setDraft] = useState(() => base ? { ...base } : {
    id: "new", name: "Yangi avatar", role: "Virtual yordamchi", brand: "O‘zbekiston Temir Yo‘llari",
    brandShort: "UTY", status: "draft", accent: "#B98944",
    portrait: { ...GRADIENTS[0], initials: "Y" },
    voice: "madina", language: "uz", extraMargin: 16, fps: 25,
    blinkRate: 4, headMotion: 0.45, persona: "", sessions: 0, avgLatency: 0, cacheRate: 0, csat: 0,
    suggestions: ["", "", ""], updated: "Bugun", respLen: "short", temperature: 0.4,
    speechRate: 0, hasPhoto: false,
  });
  const [tab, setTab] = useState("portrait");
  const set = (patch) => setDraft((d) => ({ ...d, ...patch }));
  const setP = (patch) => setDraft((d) => ({ ...d, portrait: { ...d.portrait, ...patch } }));

  return (
    <div className="ed">
      <Topbar
        title={isNew ? "Yangi avatar" : draft.name}
        sub={isNew ? "Sozlamalarni to‘ldiring va saqlang" : `${draft.brand} · ${draft.role}`}
        actions={<>
          <Btn kind="ghost" icon="back" onClick={onCancel}>Orqaga</Btn>
          {!isNew && onDelete && (
            <Btn kind="ghost" icon="x" onClick={() => { if (confirm(`"${draft.name}" o‘chirilsinmi?`)) onDelete(draft.id); }}>O‘chirish</Btn>
          )}
          <Btn kind="ghost" icon="eye" onClick={() => go({ screen: "preview", id: draft.id === "new" ? null : draft.id })}>Ko‘rish</Btn>
          <Btn kind="primary" icon="check" onClick={() => onSave(draft)}>Saqlash</Btn>
        </>} />

      <div className="ed-body">
        {/* left: tabs + form */}
        <div className="ed-main as-scroll">
          <div className="ed-tabs">
            {EDITOR_TABS.map((t) => {
              const Ico = I[t.icon];
              return (
                <button key={t.id} className={"ed-tab" + (tab === t.id ? " on" : "")} onClick={() => setTab(t.id)}>
                  <Ico size={15} />{t.label}
                </button>
              );
            })}
          </div>

          <div className="ed-form">
            {tab === "portrait" && <TabPortrait draft={draft} set={set} setP={setP} />}
            {tab === "voice"    && <TabVoice draft={draft} set={set} />}
            {tab === "persona"  && <TabPersona draft={draft} set={set} />}
            {tab === "motion"   && <TabMotion draft={draft} set={set} />}
            {tab === "sugg"     && <TabSugg draft={draft} set={set} />}
            {tab === "brand"    && <TabBrand draft={draft} set={set} setP={setP} />}
          </div>
        </div>

        {/* right: live preview */}
        <EditorPreview draft={draft} />
      </div>
    </div>
  );
}

/* ── Preview pane ── */
function EditorPreview({ draft }) {
  const [speaking, setSpeaking] = useState(false);
  const voice = VOICES.find((v) => v.id === draft.voice) || VOICES[0];
  const lang = LANGUAGES.find((l) => l.code === draft.language) || LANGUAGES[0];
  return (
    <aside className="ed-preview">
      <div className="as-label" style={{ marginBottom: 14 }}>Jonli ko‘rinish</div>
      <div className={"ed-pv-card" + (speaking ? " speaking" : "")}>
        <div className="ed-pv-img" style={{ background: `linear-gradient(155deg, ${draft.portrait.from}, ${draft.portrait.to})` }}>
          <span className="ed-pv-initials">{draft.portrait.initials || draft.name[0]}</span>
          {speaking && <div className="cs-eq"><span/><span/><span/><span/><span/></div>}
        </div>
        <div className="cs-frame" />
        <div className="cs-overlay">
          <div>
            <div className="cs-pname" style={{ fontSize: 24 }}>{draft.name}</div>
            <div className="cs-prole">{draft.role}</div>
          </div>
          <div className="cs-pill"><span className="cs-pill-dot" style={{ background: speaking ? "var(--brass)" : "var(--ok)" }} />{speaking ? "Gapirmoqda" : "Tayyor"}</div>
        </div>
      </div>

      <button className="ed-pv-test" onClick={() => { setSpeaking(true); setTimeout(() => setSpeaking(false), 2600); }}>
        {speaking ? <I.pause size={14} /> : <I.play size={14} />} {speaking ? "To‘xtatish" : "Sinab ko‘rish"}
      </button>

      <div className="ed-pv-meta">
        <div className="ed-pv-row"><span className="as-label">Ovoz</span><span className="ed-pv-val">{voice.name} · {voice.tag}</span></div>
        <div className="ed-pv-row"><span className="as-label">Til</span><span className="ed-pv-val">{lang.native}</span></div>
        <div className="ed-pv-row"><span className="as-label">FPS</span><span className="ed-pv-val">{draft.fps}</span></div>
        <div className="ed-pv-row"><span className="as-label">Extra margin</span><span className="ed-pv-val">{draft.extraMargin}px</span></div>
      </div>
    </aside>
  );
}

/* ── Tab: Portrait ── */
function TabPortrait({ draft, set, setP }) {
  return (
    <Section title="Portret va identifikatsiya" desc="Avatar yuzini yuklang yoki vaqtincha gradient placeholder ishlating.">
      <div className="ed-drop" onClick={() => set({ hasPhoto: !draft.hasPhoto })}>
        {draft.hasPhoto ? (
          <div className="ed-drop-filled" style={{ background: `linear-gradient(155deg, ${draft.portrait.from}, ${draft.portrait.to})` }}>
            <I.check size={20} /><span>Portret yuklandi</span><small>almashtirish uchun bosing</small>
          </div>
        ) : (
          <><div className="ed-drop-ico"><I.upload size={22} /></div>
          <div className="ed-drop-t">Portret rasmini yuklang</div>
          <div className="ed-drop-s">JPG yoki PNG · kamida 512×512 · old tomondan, yorug‘ fon</div></>
        )}
      </div>

      <Row2>
        <Field label="Avatar nomi"><input className="as-field" value={draft.name} onChange={(e) => set({ name: e.target.value })} /></Field>
        <Field label="Rol / lavozim"><input className="as-field" value={draft.role} onChange={(e) => set({ role: e.target.value })} /></Field>
      </Row2>

      <Field label="Placeholder gradienti" hint="Real portret yuklanmaganda ko‘rinadi.">
        <div className="ed-swatches">
          {GRADIENTS.map((g, i) => (
            <button key={i} className={"ed-swatch" + (draft.portrait.from === g.from ? " on" : "")}
              style={{ background: `linear-gradient(150deg, ${g.from}, ${g.to})` }}
              onClick={() => setP(g)} />
          ))}
        </div>
      </Field>

      <Field label="Bosh harflar" hint="Gradient ustida ko‘rsatiladigan monogramma.">
        <input className="as-field" style={{ maxWidth: 90, textAlign: "center" }} maxLength={2}
          value={draft.portrait.initials} onChange={(e) => setP({ initials: e.target.value.toUpperCase() })} />
      </Field>
    </Section>
  );
}

/* ── Tab: Voice & Language ── */
function TabVoice({ draft, set }) {
  return (
    <Section title="Ovoz va til" desc="TTS ovozini va asosiy tilni tanlang.">
      <Field label="Til">
        <div className="ed-lang">
          {LANGUAGES.map((l) => (
            <button key={l.code} className={"ed-lang-btn" + (draft.language === l.code ? " on" : "")} onClick={() => set({ language: l.code })}>
              <span className="ed-lang-flag">{l.flag}</span><span>{l.native}</span>
            </button>
          ))}
        </div>
      </Field>

      <Field label="Ovoz">
        <div className="ed-voices">
          {VOICES.filter((v) => !draft.language || v.lang === (LANGUAGES.find(l=>l.code===draft.language)||{}).native ? true : true)
            .filter((v) => langMatch(v, draft.language)).map((v) => (
            <button key={v.id} className={"ed-voice" + (draft.voice === v.id ? " on" : "")} onClick={() => set({ voice: v.id })}>
              <div className="ed-voice-av" style={{ background: v.gender === "Ayol" || v.gender==="Friendly" ? "var(--brass)" : "var(--navy)" }}>{v.name[0]}</div>
              <div className="ed-voice-meta">
                <div className="ed-voice-name">{v.name}</div>
                <div className="ed-voice-sub">{v.gender} · {v.tag}</div>
              </div>
              <div className="ed-voice-play"><I.play size={12} /></div>
            </button>
          ))}
        </div>
      </Field>

      <Field label={`Nutq tezligi · ${draft.speechRate > 0 ? "+" : ""}${draft.speechRate}%`} hint="Manfiy = sekinroq, musbat = tezroq.">
        <Range value={draft.speechRate} min={-30} max={30} step={5} onChange={(v) => set({ speechRate: v })} />
      </Field>
    </Section>
  );
}
function langMatch(v, code) {
  const map = { uz: "O‘zbek", ru: "Русский", en: "English" };
  if (!map[code]) return true;
  return v.lang === map[code];
}

/* ── Tab: Persona ── */
function TabPersona({ draft, set }) {
  return (
    <Section title="Personality va javob uslubi" desc="GPT tizim prompti va javob xulqi.">
      <Field label="Tizim prompti" hint="Avatar qanday gapirishini belgilaydi. Qisqa javob = tezroq video.">
        <textarea className="as-field" rows={6} value={draft.persona}
          placeholder="Siz O‘zbekiston Temir Yo‘llari yordamchisisiz. Iliq, qisqa va aniq javob bering…"
          onChange={(e) => set({ persona: e.target.value })} />
      </Field>
      <Row2>
        <Field label="Javob uzunligi" hint="Qisqa javob real-time video uchun tavsiya etiladi.">
          <Segmented value={draft.respLen} onChange={(v) => set({ respLen: v })}
            options={[{value:"short",label:"Qisqa"},{value:"medium",label:"O‘rta"},{value:"long",label:"Uzun"}]} />
        </Field>
        <Field label={`Ijodkorlik · ${draft.temperature.toFixed(1)}`} hint="Past = aniq, yuqori = erkin.">
          <Range value={draft.temperature} min={0} max={1} step={0.1} onChange={(v) => set({ temperature: v })} />
        </Field>
      </Row2>
    </Section>
  );
}

/* ── Tab: Motion / Lip-sync ── */
function TabMotion({ draft, set }) {
  return (
    <Section title="Idle harakat va lip-sync" desc="LivePortrait idle + MuseTalk parametrlari.">
      <Field label={`Ko‘z pirpiratish chastotasi · har ${draft.blinkRate}s`} hint="LivePortrait idle blink intervali.">
        <Range value={draft.blinkRate} min={2} max={8} step={1} onChange={(v) => set({ blinkRate: v })} />
      </Field>
      <Field label={`Bosh harakati · ${Math.round(draft.headMotion * 100)}%`} hint="Idle paytidagi tabiiy bosh tebranishi.">
        <Range value={draft.headMotion} min={0} max={1} step={0.05} onChange={(v) => set({ headMotion: v })} />
      </Field>
      <Row2>
        <Field label={`Extra margin · ${draft.extraMargin}px`} hint="Lab/jag‘ artikulyatsiyasi (MuseTalk v15).">
          <Range value={draft.extraMargin} min={0} max={32} step={2} onChange={(v) => set({ extraMargin: v })} />
        </Field>
        <Field label="Kadrlar (FPS)" hint="25 = standart, 30 = silliqroq, sekinroq.">
          <Segmented value={String(draft.fps)} onChange={(v) => set({ fps: parseInt(v) })}
            options={[{value:"20",label:"20"},{value:"25",label:"25"},{value:"30",label:"30"}]} />
        </Field>
      </Row2>
      <div className="ed-note"><I.bolt size={14} /><span><b>Eslatma:</b> v15 da <code>bbox_shift</code> ishlamaydi (qattiq 0). Lab artikulyatsiyasini faqat <code>extra_margin</code> boshqaradi.</span></div>
    </Section>
  );
}

/* ── Tab: Suggestions ── */
function TabSugg({ draft, set }) {
  const items = draft.suggestions.length ? draft.suggestions : ["", "", ""];
  const update = (i, v) => { const a = [...items]; a[i] = v; set({ suggestions: a }); };
  const add = () => set({ suggestions: [...items, ""] });
  const rm = (i) => set({ suggestions: items.filter((_, x) => x !== i) });
  return (
    <Section title="Tezkor javoblar" desc="Suhbat boshida ko‘rinadigan tavsiya tugmalari.">
      <div className="ed-sugg-list">
        {items.map((s, i) => (
          <div key={i} className="ed-sugg-row">
            <span className="ed-sugg-num">{String(i+1).padStart(2,"0")}</span>
            <input className="as-field" value={s} placeholder="Tavsiya matni…" onChange={(e) => update(i, e.target.value)} />
            <button className="ed-sugg-rm" onClick={() => rm(i)}><I.x size={15} /></button>
          </div>
        ))}
      </div>
      <Btn kind="ghost" icon="plus" onClick={add}>Tavsiya qo‘shish</Btn>
    </Section>
  );
}

/* ── Tab: Branding ── */
function TabBrand({ draft, set, setP }) {
  return (
    <Section title="Brending" desc="Brend nomi, rang va logotip.">
      <Row2>
        <Field label="Brend nomi"><input className="as-field" value={draft.brand} onChange={(e) => set({ brand: e.target.value })} /></Field>
        <Field label="Qisqa kod"><input className="as-field" value={draft.brandShort} maxLength={5} onChange={(e) => set({ brandShort: e.target.value.toUpperCase() })} /></Field>
      </Row2>
      <Field label="Brend rangi (accent)">
        <div className="ed-swatches">
          {ACCENTS.map((c) => (
            <button key={c} className={"ed-swatch round" + (draft.accent === c ? " on" : "")} style={{ background: c }} onClick={() => set({ accent: c })} />
          ))}
        </div>
      </Field>
      <Field label="Holat">
        <Segmented value={draft.status} onChange={(v) => set({ status: v })}
          options={[{value:"live",label:"Faol"},{value:"draft",label:"Qoralama"},{value:"paused",label:"To‘xtatilgan"}]} />
      </Field>
    </Section>
  );
}

/* ── helpers ── */
function Section({ title, desc, children }) {
  return (
    <div className="ed-section">
      <div className="ed-section-head">
        <div className="ed-section-title">{title}</div>
        {desc && <div className="ed-section-desc">{desc}</div>}
      </div>
      <div className="ed-section-body">{children}</div>
    </div>
  );
}
function Row2({ children }) { return <div className="ed-row2">{children}</div>; }
