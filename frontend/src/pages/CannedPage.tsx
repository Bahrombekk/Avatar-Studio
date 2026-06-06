/* Tayyor javoblar — Video Studiya dizaynida (vstudio). Composer (nom + savol
   variantlari + javob) + kutubxona + modal (pleyer + savollar + skript).
   Real-time'da savol mos kelsa shu video o'ynaladi. */
import { useEffect, useMemo, useRef, useState } from "react";
import "@/styles/vstudio.css";
import { API, type Canned } from "@/api/client";
import { useAvatars } from "@/context/AvatarsContext";
import { useToast } from "@/context/ToastContext";
import { RenderProgress } from "@/components/RenderProgress";
import type { Voice } from "@/types/chat";

const MAX = 2000;

const Ico = {
  play: (p: any) => (<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" {...p}><path d="M8 5.5v13l11-6.5z" /></svg>),
  search: (p: any) => (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...p}><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>),
  download: (p: any) => (<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...p}><path d="M12 3v12M7 11l5 4 5-4M4 21h16" /></svg>),
  trash: (p: any) => (<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...p}><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>),
  mic: (p: any) => (<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" {...p}><rect x="9" y="2.5" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" /></svg>),
  avatars: (p: any) => (<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" {...p}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></svg>),
  chat: (p: any) => (<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" {...p}><path d="M21 11.5a8.38 8.38 0 0 1-9 8.3A9 9 0 1 1 21 11.5z" /></svg>),
  spark: (p: any) => (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" {...p}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /></svg>),
  close: (p: any) => (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...p}><path d="M6 6l12 12M18 6L6 18" /></svg>),
  plus: (p: any) => (<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" {...p}><path d="M12 5v14M5 12h14" /></svg>),
  x: (p: any) => (<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...p}><path d="M6 6l12 12M18 6L6 18" /></svg>),
};

export function CannedPage() {
  const { avatars } = useAvatars();
  const { toast } = useToast();
  const ready = useMemo(() => avatars.filter((a) => a.real), [avatars]);

  const [avatarId, setAvatarId] = useState("");
  const [mode, setMode] = useState<"script" | "gpt">("script");
  const [title, setTitle] = useState("");
  const [questions, setQuestions] = useState<string[]>([""]);
  const [text, setText] = useState("");
  const [voice, setVoice] = useState("");
  const [busy, setBusy] = useState(false);

  const [voices, setVoices] = useState<Voice[]>([]);
  const [items, setItems] = useState<Canned[]>([]);
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const pollRef = useRef<number>(0);

  const avatar = useMemo(() => ready.find((a) => a.id === avatarId) || ready[0], [ready, avatarId]);
  const open = items.find((c) => c.id === openId) || null;
  const confirmItem = items.find((c) => c.id === confirmId) || null;
  const voiceName = (id: string) => voices.find((v) => v.id === id)?.label || id;

  useEffect(() => {
    API.voices().then(setVoices).catch(() => {});
    void load();
    const t = window.setInterval(load, 4000);
    return () => { window.clearInterval(t); window.clearInterval(pollRef.current); };
  }, []);
  useEffect(() => { if (avatar && !voice) setVoice(avatar.voice || ""); }, [avatar, voice]);

  async function load() { try { setItems(await API.cannedList()); } catch (e) { console.error(e); } }

  function cycleAvatar() {
    if (ready.length < 2) return;
    const i = ready.findIndex((a) => a.id === avatar?.id);
    setAvatarId(ready[(i + 1) % ready.length].id);
  }
  function setQv(i: number, v: string) { setQuestions((qs) => qs.map((x, j) => (j === i ? v : x))); }

  async function generate() {
    if (!avatar) { toast("Avval tayyor avatar tanlang", "error"); return; }
    const qs = questions.map((x) => x.trim()).filter(Boolean);
    if (!qs.length) { toast("Kamida bitta savol varianti yozing", "error"); return; }
    if (!text.trim()) { toast(mode === "gpt" ? "Mavzu yozing" : "Javob matnini yozing", "error"); return; }
    setBusy(true);
    try {
      await API.cannedCreate({
        avatar_id: avatar.id, questions: qs, mode,
        text: mode === "script" ? text : "", prompt: mode === "gpt" ? text : "",
        voice: voice || avatar.voice || null, title,
      });
      toast("Tayyor javob render navbatiga qo'shildi", "success");
      setTitle(""); setQuestions([""]); setText("");
      await load();
    } catch (e) { toast((e as Error).message, "error"); }
    finally { setBusy(false); }
  }

  async function remove(id: string) {
    try { await API.cannedDelete(id); setOpenId((o) => (o === id ? null : o)); await load(); toast("O'chirildi", "success"); }
    catch (e) { toast((e as Error).message, "error"); }
  }

  const shown = useMemo(() => items.filter((c) =>
    (c.title || "").toLowerCase().includes(q.toLowerCase()) ||
    (c.questions || []).some((x) => x.toLowerCase().includes(q.toLowerCase()))
  ), [items, q]);
  const near = text.length > MAX * 0.9;

  return (
    <div className="vstudio as-scroll" style={{ height: "100%", overflow: "auto" }}>
      <header className="vs-top">
        <div>
          <h1 className="title-h serif">Tayyor javoblar</h1>
          <div className="title-sub">Savollarga oldindan video javob · real-time'da darrov o'ynaladi</div>
        </div>
      </header>

      {ready.length === 0 ? (
        <div className="layout"><div className="empty"><span className="serif">Tayyor avatar yo'q</span>Tayyor javob uchun modeli qurilgan avatar kerak.</div></div>
      ) : (
        <div className="layout">
          {/* ── Composer ── */}
          <section className="composer">
            <div className="composer-head">
              <h2 className="serif">Yangi tayyor javob</h2>
              <p>Savol variantlari + javob. Foydalanuvchi shunday so'rasa — shu video o'ynaladi.</p>
            </div>
            <div className="composer-body">
              <div className="field">
                <span className="eyebrow">Avatar</span>
                <div className="avatar-pick" onClick={cycleAvatar} title={ready.length > 1 ? "Almashtirish uchun bosing" : ""}>
                  <img className="avatar-thumb" src={API.photoUrl(avatar!.id)} alt="" />
                  <div className="avatar-meta"><div className="nm">{avatar!.name}</div><div className="rl">{avatar!.role}</div></div>
                </div>
              </div>

              <div className="field">
                <span className="eyebrow">Nom</span>
                <input className="inp" placeholder="Masalan: Ish vaqti" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>

              <div className="field">
                <span className="eyebrow">Savol variantlari</span>
                {questions.map((qq, i) => (
                  <div key={i} style={{ display: "flex", gap: 7, alignItems: "center" }}>
                    <input className="inp" style={{ flex: 1 }} value={qq}
                      placeholder={`Savol ${i + 1}`} onChange={(e) => setQv(i, e.target.value)} />
                    {questions.length > 1 && (
                      <button className="act del" style={{ padding: 6 }} onClick={() => setQuestions((qs) => qs.filter((_, j) => j !== i))}><Ico.x /></button>
                    )}
                  </div>
                ))}
                <button className="act dl" style={{ alignSelf: "flex-start", padding: "4px 0" }} onClick={() => setQuestions((qs) => [...qs, ""])}><Ico.plus /> Yana variant</button>
              </div>

              <div className="field">
                <span className="eyebrow">Javob manbasi</span>
                <div className="seg">
                  <button className={mode === "script" ? "on" : ""} onClick={() => setMode("script")}>Matn yozish</button>
                  <button className={mode === "gpt" ? "on" : ""} onClick={() => setMode("gpt")}>GPT'dan</button>
                </div>
              </div>

              <div className="field">
                <div className="field-label">
                  <span className="eyebrow">{mode === "gpt" ? "GPT uchun mavzu" : "Javob matni"}</span>
                  <span className={"counter" + (near ? " near" : "")}>{text.length} / {MAX}</span>
                </div>
                <textarea className="txta" maxLength={MAX}
                  placeholder={mode === "gpt" ? "Mavzuni yozing…" : "Avatar aytadigan javob…"}
                  value={text} onChange={(e) => setText(e.target.value)} />
              </div>

              <div className="field">
                <span className="eyebrow">Ovoz</span>
                <select className="sel" value={voice} onChange={(e) => setVoice(e.target.value)}>
                  {voices.map((v) => <option key={v.id} value={v.id}>{v.label || v.name || v.id}</option>)}
                </select>
              </div>

              <button className="btn-primary" disabled={busy} onClick={generate}>
                {busy ? <>Yuborilmoqda…</> : mode === "gpt" ? <><Ico.spark /> GPT bilan yaratish</> : <><Ico.play style={{ width: 15, height: 15 }} /> Tayyor javob yaratish</>}
              </button>
            </div>
          </section>

          {/* ── Library ── */}
          <section className="library">
            <div className="lib-head">
              <div className="lib-title"><h2 className="serif">Javoblar</h2><span className="lib-count">{shown.length} / {items.length} ta</span></div>
              <div className="lib-tools">
                <div className="search"><Ico.search /><input placeholder="Savol yoki nom…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
              </div>
            </div>
            <div className="grid">
              {shown.length === 0 ? (
                <div className="empty"><span className="serif">Hali tayyor javob yo'q</span>Chapdan birinchi javobni yarating.</div>
              ) : shown.map((c, i) => {
                const ok = c.state === "done";
                return (
                  <article className="vcard" key={c.id} style={{ animationDelay: Math.min(i * 28, 360) + "ms" }}>
                    <div className={"thumb" + (ok ? " clickable" : "")} onClick={ok ? () => setOpenId(c.id) : undefined}>
                      {c.state === "processing" ? (
                        <div className="proc-overlay"><div className="proc-shimmer" /><div className="proc-spin" /><div className="proc-txt">Yaratilmoqda…</div></div>
                      ) : c.state === "error" ? (
                        <div className="err-overlay"><div className="et">Xatolik</div></div>
                      ) : (
                        <>
                          <video className="thumb-vid" src={API.cannedVideoUrl(c.id) + "#t=0.7"} muted preload="metadata" playsInline
                            onLoadedMetadata={(e) => { try { e.currentTarget.currentTime = 0.7; } catch { /* */ } }} />
                          <div className="thumb-grad-overlay" />
                          <span className="badge ready"><span className="bdot" />Tayyor</span>
                          <button className="play"><Ico.play /></button>
                        </>
                      )}
                      {c.state === "processing" && <span className="badge proc"><span className="bdot" />Render</span>}
                    </div>
                    <div className="card-body">
                      <div className="card-title" title={c.title} onClick={ok ? () => setOpenId(c.id) : undefined} style={ok ? { cursor: "pointer" } : undefined}>{c.title}</div>
                      <div className="card-meta">
                        <span className="chip"><Ico.avatars />{c.avatar_name}</span>
                        <span className="chip"><Ico.chat />{(c.questions || []).length} savol</span>
                      </div>
                      <div className="card-actions">
                        <span className="act" style={{ cursor: "default" }}><Ico.mic />{voiceName(c.voice)}</span>
                        <button className="act del" onClick={() => setConfirmId(c.id)} title="O'chirish"><Ico.trash /></button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </div>
      )}

      {open && <CannedModal item={open} voiceName={voiceName} onClose={() => setOpenId(null)}
        onDelete={() => setConfirmId(open.id)} onSaved={load} toast={toast} />}

      {confirmItem && (
        <div className="vstudio-confirm-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setConfirmId(null); }}>
          <div className="vstudio-confirm" role="alertdialog">
            <div className="ic"><Ico.trash /></div>
            <div className="ct">Tayyor javobni o'chirasizmi?</div>
            <div className="cm"><b>"{confirmItem.title}"</b> butunlay o'chiriladi.</div>
            <div className="ca">
              <button className="cf-cancel" onClick={() => setConfirmId(null)}>Bekor qilish</button>
              <button className="cf-delete" autoFocus onClick={() => { const id = confirmId!; setConfirmId(null); remove(id); }}>O'chirish</button>
            </div>
          </div>
        </div>
      )}

      <RenderProgress items={items.filter((c) => c.state === "processing").map((c) => ({ id: c.id, title: c.title, photo: API.photoUrl(c.avatar_id) }))} />
    </div>
  );
}

/* ── Modal: pleyer + savollar (tahrirlanadigan) + skript ── */
function CannedModal({ item, voiceName, onClose, onDelete, onSaved, toast }: any) {
  const [qs, setQs] = useState<string[]>(item.questions || []);
  const [add, setAdd] = useState("");
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(qs) !== JSON.stringify(item.questions || []);

  async function save() {
    setSaving(true);
    try { await API.cannedUpdateQuestions(item.id, qs.map((s) => s.trim()).filter(Boolean)); toast("Savollar saqlandi", "success"); await onSaved(); }
    catch (e) { toast((e as Error).message, "error"); }
    finally { setSaving(false); }
  }

  return (
    <div className="vstudio-modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="vstudio-modal">
        <button className="modal-close" onClick={onClose}><Ico.close /></button>
        <div className="player"><video src={API.cannedVideoUrl(item.id)} controls autoPlay playsInline /></div>
        <div className="modal-side">
          <div className="ms-title">{item.title}</div>
          <div className="ms-meta">
            <span className="ms-pill"><Ico.avatars />{item.avatar_name}</span>
            <span className="ms-pill"><Ico.mic />{voiceName(item.voice)}</span>
          </div>

          <div className="field" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="ms-script-label">
              <span className="eyebrow">Javob beradigan savollar ({qs.length})</span>
              {dirty && <button className="act dl" style={{ padding: 0 }} disabled={saving} onClick={save}>{saving ? "Saqlanyapti…" : "Saqlash"}</button>}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 200, overflow: "auto" }}>
              {qs.map((qq, i) => (
                <div key={i} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input className="inp" style={{ flex: 1, padding: "8px 10px", fontSize: 12.5 }} value={qq}
                    onChange={(e) => setQs((a) => a.map((x, j) => (j === i ? e.target.value : x)))} />
                  <button className="act del" style={{ padding: 5 }} onClick={() => setQs((a) => a.filter((_, j) => j !== i))}><Ico.x /></button>
                </div>
              ))}
              <div style={{ display: "flex", gap: 6 }}>
                <input className="inp" style={{ flex: 1, padding: "8px 10px", fontSize: 12.5 }} placeholder="Yangi savol varianti…"
                  value={add} onChange={(e) => setAdd(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && add.trim()) { setQs((a) => [...a, add.trim()]); setAdd(""); } }} />
                <button className="act dl" style={{ padding: 5 }} disabled={!add.trim()} onClick={() => { setQs((a) => [...a, add.trim()]); setAdd(""); }}><Ico.plus /></button>
              </div>
            </div>

            <span className="eyebrow" style={{ marginTop: 6 }}>Skript (javob matni)</span>
            <div className="ms-script" style={{ maxHeight: 140 }}>{item.text || "—"}</div>
          </div>

          <div className="ms-actions">
            <a className="ms-btn primary" href={API.cannedVideoUrl(item.id)} download={`${item.title || item.id}.mp4`}><Ico.download /> Yuklab olish</a>
            <button className="ms-btn danger" onClick={onDelete}><Ico.trash /></button>
          </div>
        </div>
      </div>
    </div>
  );
}
