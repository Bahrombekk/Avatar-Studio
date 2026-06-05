/* Avatar Studio — Avatar muharriri (yaratish + barcha sozlamalar).
   Chapda tabli sozlamalar, o'ngda yopishqoq jonli ko'rinish. */
import { useState, useEffect, useRef } from "react";
import { I } from "../lib/icons";
import { Btn, Field, Segmented, Range } from "../components/ui/index.jsx";
import { Topbar } from "../components/AdminShell.jsx";
import { VOICES, LANGUAGES } from "../data/constants";
import { API } from "../api/client";

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
    voice: "madina", language: "uz", extraMargin: 16, fps: 25, maxDim: 1280,
    blinkRate: 4, headMotion: 0.45, persona: "", sessions: 0, avgLatency: 0, cacheRate: 0, csat: 0,
    suggestions: ["", "", ""], updated: "Bugun", respLen: "short", temperature: 0.4,
    speechRate: 0, hasPhoto: false,
  });
  const [tab, setTab] = useState("portrait");
  const set = (patch) => setDraft((d) => ({ ...d, ...patch }));
  const setP = (patch) => setDraft((d) => ({ ...d, portrait: { ...d.portrait, ...patch } }));

  // Rasm yuklash holati. Yangi (saqlanmagan) avatar uchun id yo'q — avval saqlash kerak.
  const savedId = base && draft.id && draft.id !== "new" ? draft.id : null;
  const [uploading, setUploading] = useState(false);
  const [photoErr, setPhotoErr] = useState("");
  const [photoVer, setPhotoVer] = useState(0);
  async function handlePhoto(fileList) {
    const file = fileList && fileList[0];
    if (!file || !savedId) return;
    setUploading(true); setPhotoErr("");
    try {
      await API.uploadPhoto(savedId, file);
      set({ hasPhoto: true });
      setPhotoVer((v) => v + 1);
    } catch (e) {
      setPhotoErr(e.message || "Rasm yuklanmadi");
    } finally {
      setUploading(false);
    }
  }

  // Idle generatsiya holati + polling (build.state: idle|processing|done|error).
  const [build, setBuild] = useState(() => (base && base.build) || null);
  const [idleVer, setIdleVer] = useState(0);
  const [buildErr, setBuildErr] = useState("");
  const pollRef = useRef(null);
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  async function pollBuild() {
    if (!savedId) return;
    try {
      const st = await API.buildStatus(savedId);
      setBuild(st);
      if (!st.running && (st.state === "done" || st.state === "error")) {
        clearInterval(pollRef.current); pollRef.current = null;
        if (st.state === "done") {
          if (st.stage === "musetalk_prep") set({ hasArtifact: true });
          else if (st.stage === "motion") set({ hasMotion: true });
          else setIdleVer((v) => v + 1);
        }
        if (st.state === "error") setBuildErr(st.error || "Generatsiya xatosi");
      }
    } catch { /* ignore poll xatolari */ }
  }
  async function startBuildIdle() {
    if (!savedId) return;
    setBuildErr("");
    try {
      await API.buildIdle(savedId);
      setBuild({ state: "processing", stage: "idle_gen", running: true });
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(pollBuild, 2500);
    } catch (e) {
      setBuildErr(e.message || "Idle yaratib bo'lmadi");
    }
  }
  async function startBuildMusetalk() {
    if (!savedId) return;
    setBuildErr("");
    try {
      await API.buildMusetalk(savedId);
      setBuild({ state: "processing", stage: "musetalk_prep", running: true });
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(pollBuild, 2500);
    } catch (e) {
      setBuildErr(e.message || "Artefakt yaratib bo'lmadi");
    }
  }
  async function startBuildMotion() {
    if (!savedId) return;
    setBuildErr("");
    try {
      await API.buildMotion(savedId);
      setBuild({ state: "processing", stage: "motion", running: true });
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(pollBuild, 2500);
    } catch (e) {
      setBuildErr(e.message || "Harakat yaratib bo'lmadi");
    }
  }

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
            {tab === "portrait" && <TabPortrait draft={draft} set={set} setP={setP}
              savedId={savedId} uploading={uploading} photoErr={photoErr} photoVer={photoVer}
              onPhoto={handlePhoto} />}
            {tab === "voice"    && <TabVoice draft={draft} set={set} />}
            {tab === "persona"  && <TabPersona draft={draft} set={set} />}
            {tab === "motion"   && <TabMotion draft={draft} set={set}
              savedId={savedId} build={build} idleVer={idleVer} buildErr={buildErr}
              onBuildIdle={startBuildIdle} onBuildMusetalk={startBuildMusetalk}
              onBuildMotion={startBuildMotion} />}
            {tab === "sugg"     && <TabSugg draft={draft} set={set} />}
            {tab === "brand"    && <TabBrand draft={draft} set={set} setP={setP} />}
          </div>
        </div>

        {/* right: live preview */}
        <EditorPreview draft={draft} savedId={savedId} photoVer={photoVer} />
      </div>
    </div>
  );
}

/* ── Preview pane ── */
function EditorPreview({ draft, savedId, photoVer }) {
  const [speaking, setSpeaking] = useState(false);
  const voice = VOICES.find((v) => v.id === draft.voice) || VOICES[0];
  const lang = LANGUAGES.find((l) => l.code === draft.language) || LANGUAGES[0];
  const photoSrc = savedId && draft.hasPhoto ? API.photoUrl(savedId, photoVer) : null;
  const imgStyle = photoSrc
    ? { backgroundImage: `url(${photoSrc})`, backgroundSize: "cover", backgroundPosition: "center top" }
    : { background: `linear-gradient(155deg, ${draft.portrait.from}, ${draft.portrait.to})` };
  return (
    <aside className="ed-preview">
      <div className="as-label" style={{ marginBottom: 14 }}>Jonli ko‘rinish</div>
      <div className={"ed-pv-card" + (speaking ? " speaking" : "")}>
        <div className="ed-pv-img" style={imgStyle}>
          {!photoSrc && <span className="ed-pv-initials">{draft.portrait.initials || draft.name[0]}</span>}
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
function TabPortrait({ draft, set, setP, savedId, uploading, photoErr, photoVer, onPhoto }) {
  const inputId = "ed-photo-input";
  const photoSrc = savedId && draft.hasPhoto ? API.photoUrl(savedId, photoVer) : null;
  const pick = () => { if (savedId && !uploading) document.getElementById(inputId)?.click(); };
  return (
    <Section title="Portret va identifikatsiya" desc="Avatar yuzini yuklang yoki vaqtincha gradient placeholder ishlating.">
      <input id={inputId} type="file" accept="image/jpeg,image/png,image/webp" hidden
        onChange={(e) => { onPhoto(e.target.files); e.target.value = ""; }} />

      <div className={"ed-drop" + (savedId ? "" : " disabled")} onClick={pick}
        style={savedId ? undefined : { cursor: "not-allowed", opacity: 0.6 }}>
        {uploading ? (
          <><div className="ed-drop-ico"><I.upload size={22} /></div>
          <div className="ed-drop-t">Yuklanmoqda va yuz tekshirilmoqda…</div></>
        ) : photoSrc ? (
          <><div className="ed-drop-ico"><I.check size={22} /></div>
          <div className="ed-drop-t">Portret yuklandi</div>
          <div className="ed-drop-s">almashtirish uchun bosing · jonli ko‘rinish yon tomonda</div></>
        ) : (
          <><div className="ed-drop-ico"><I.upload size={22} /></div>
          <div className="ed-drop-t">Portret rasmini yuklang</div>
          <div className="ed-drop-s">JPG, PNG yoki WebP · kamida 512×512 · old tomondan, yorug‘ fon</div></>
        )}
      </div>
      {!savedId && (
        <div className="ed-note"><I.bolt size={14} /><span>Rasm yuklash uchun avatarni avval <b>saqlang</b>. Saqlangach bu yerga qaytib portret yuklaysiz.</span></div>
      )}
      {photoErr && (
        <div className="ed-note" style={{ borderColor: "var(--err, #C0392B)" }}><I.x size={14} /><span>{photoErr}</span></div>
      )}

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
  // Til o'zgarganda joriy ovoz o'sha tilga mos bo'lmasa, birinchi mos ovozni tanlaymiz.
  const pickLang = (code) => {
    const cur = VOICES.find((v) => v.id === draft.voice);
    if (cur && cur.langCode === code) { set({ language: code }); return; }
    const first = VOICES.find((v) => v.langCode === code);
    set(first ? { language: code, voice: first.id } : { language: code });
  };
  return (
    <Section title="Ovoz va til" desc="TTS ovozini va asosiy tilni tanlang.">
      <Field label="Til">
        <div className="ed-lang">
          {LANGUAGES.map((l) => (
            <button key={l.code} className={"ed-lang-btn" + (draft.language === l.code ? " on" : "")} onClick={() => pickLang(l.code)}>
              <span className="ed-lang-flag">{l.flag}</span><span>{l.native}</span>
            </button>
          ))}
        </div>
      </Field>

      <Field label="Ovoz">
        <div className="ed-voices">
          {VOICES.filter((v) => langMatch(v, draft.language)).map((v) => (
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
  if (!code) return true;
  return v.langCode === code;
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
function TabMotion({ draft, set, savedId, build, idleVer, buildErr, onBuildIdle, onBuildMusetalk, onBuildMotion }) {
  const state = build && build.state;
  const stage = build && build.stage;
  const processing = !!(build && (build.running || state === "processing"));
  const idleProcessing = processing && stage === "idle_gen";
  const mtProcessing = processing && stage === "musetalk_prep";
  const motionProcessing = processing && stage === "motion";
  const motionDone = !!draft.hasMotion;
  const canBuildMotion = savedId && !!draft.hasArtifact && !processing;
  // Idle tayyor: shu sessiyada yasaldi, yoki artefakt mavjud (idle undan oldin shart edi).
  const idleDone = (stage === "idle_gen" && state === "done") || stage === "musetalk_prep" || !!draft.hasArtifact;
  const mtDone = !!draft.hasArtifact;
  const canBuild = savedId && draft.hasPhoto && !processing;
  const canBuildMt = savedId && idleDone && !processing;
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

      <Field label="Sifat / Tezlik" hint="720p = tezroq (real-time suhbat uchun); 1080p = tiniqroq (Video Studiya uchun, lekin sekinroq). O‘zgartirsangiz Idle + Model qayta qurilsin.">
        <Segmented value={String(draft.maxDim || 1280)} onChange={(v) => set({ maxDim: parseInt(v) })}
          options={[{value:"1280",label:"Tez · 720p"},{value:"1920",label:"Sifat · 1080p"}]} />
      </Field>

      <Field label="1-qadam · Idle video" hint="Portretdan blink animatsiyasi yaratadi. Parametrlarni o‘zgartirsangiz qayta yarating.">
        <div className="ed-idle">
          {idleDone && savedId && (
            <video className="ed-idle-pv" src={API.idleUrl(savedId, idleVer)} muted loop autoPlay playsInline />
          )}
          <Btn kind={idleDone ? "ghost" : "primary"} icon="bolt"
            onClick={onBuildIdle} disabled={!canBuild}>
            {idleProcessing ? "Yaratilmoqda…" : idleDone ? "Qayta yaratish" : "Idle yaratish"}
          </Btn>
          {idleProcessing && <span className="ed-idle-st">LivePortrait ishlamoqda, ~15–30s…</span>}
          {idleDone && !idleProcessing && <span className="ed-idle-st ok">Tayyor</span>}
        </div>
        {idleProcessing && <div className="ed-progress"><div className="ed-progress-bar" /></div>}
      </Field>

      <Field label="2-qadam · MuseTalk artefakt" hint="Idle videodan lip-sync uchun latents/coords/mask tayyorlaydi. Idle qayta yaratilsa, buni ham qayta yarating.">
        <div className="ed-idle">
          <Btn kind={mtDone ? "ghost" : "primary"} icon="bolt"
            onClick={onBuildMusetalk} disabled={!canBuildMt}>
            {mtProcessing ? "Tayyorlanmoqda…" : mtDone ? "Qayta yaratish" : "Artefakt yaratish"}
          </Btn>
          {mtProcessing && <span className="ed-idle-st">MuseTalk preprocessing, ~1–3 daqiqa…</span>}
          {mtDone && !mtProcessing && <span className="ed-idle-st ok">Tayyor — avatar lip-sync uchun shay</span>}
        </div>
        {mtProcessing && <div className="ed-progress"><div className="ed-progress-bar" /></div>}
      </Field>

      <Field label="3-qadam · Bosh harakati (Video Studiya)" hint="GPT rejasi bo'yicha bosh harakati (nod/tilt/turn/lean) primitivlarini quradi. Video Studiya'da gapirganda bosh tabiiy harakatlanadi. Bir marta quriladi.">
        <div className="ed-idle">
          <Btn kind={motionDone ? "ghost" : "primary"} icon="bolt"
            onClick={onBuildMotion} disabled={!canBuildMotion}>
            {motionProcessing ? "Qurilmoqda…" : motionDone ? "Qayta qurish" : "Harakat qurish"}
          </Btn>
          {motionProcessing && <span className="ed-idle-st">Primitivlar (7 ta) yaratilmoqda, ~3–6 daqiqa…</span>}
          {motionDone && !motionProcessing && <span className="ed-idle-st ok">Tayyor — bosh harakati yoqilgan</span>}
        </div>
        {motionProcessing && <div className="ed-progress"><div className="ed-progress-bar" /></div>}
      </Field>

      {!savedId && (
        <div className="ed-note"><I.bolt size={14} /><span>Idle yaratish uchun avatarni <b>saqlang</b> va portret yuklang.</span></div>
      )}
      {savedId && !draft.hasPhoto && (
        <div className="ed-note"><I.bolt size={14} /><span>Avval <b>Portret</b> tabida rasm yuklang.</span></div>
      )}
      {savedId && draft.hasPhoto && !idleDone && (
        <div className="ed-note"><I.bolt size={14} /><span>MuseTalk artefakt uchun avval <b>1-qadam</b> (idle video)ni yarating.</span></div>
      )}
      {buildErr && (
        <div className="ed-note" style={{ borderColor: "var(--err, #C0392B)" }}><I.x size={14} /><span>{buildErr}</span></div>
      )}
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
