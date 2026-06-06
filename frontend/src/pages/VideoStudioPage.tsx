/* Video Studiya — Claude Design (Spectral + IBM Plex, paper/gold).
   Composer + kutubxona + video kartalar + modal pleyer + qidiruv/filtr + o'chirish dialogi.
   Haqiqiy API'ga ulangan (studioRender / studioRenders / studioVideoUrl). */
import { useEffect, useMemo, useRef, useState } from "react";
import "@/styles/vstudio.css";
import { API, type Render } from "@/api/client";
import { useAvatars } from "@/context/AvatarsContext";
import { useToast } from "@/context/ToastContext";
import { RenderProgress } from "@/components/RenderProgress";
import type { Voice } from "@/types/chat";

const MAX = 2000;

/* Kerakli ikonkalar (dizayn uslubida) */
const Ico = {
  play: (p: any) => (<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" {...p}><path d="M8 5.5v13l11-6.5z" /></svg>),
  search: (p: any) => (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...p}><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>),
  download: (p: any) => (<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...p}><path d="M12 3v12M7 11l5 4 5-4M4 21h16" /></svg>),
  trash: (p: any) => (<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...p}><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>),
  mic: (p: any) => (<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" {...p}><rect x="9" y="2.5" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" /></svg>),
  avatars: (p: any) => (<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" {...p}><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></svg>),
  spark: (p: any) => (<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" {...p}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /></svg>),
  close: (p: any) => (<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" {...p}><path d="M6 6l12 12M18 6L6 18" /></svg>),
  alert: (p: any) => (<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" {...p}><path d="M10.3 3.2 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.2a2 2 0 0 0-3.4 0z" /><path d="M12 9v5M12 17.5v.01" strokeWidth="2" /></svg>),
};

const FILTERS = [
  { id: "all", label: "Hammasi" }, { id: "done", label: "Tayyor" },
  { id: "processing", label: "Render" }, { id: "error", label: "Xato" },
];

export function VideoStudioPage() {
  const { avatars } = useAvatars();
  const { toast } = useToast();
  const ready = useMemo(() => avatars.filter((a) => a.real), [avatars]);

  const [avatarId, setAvatarId] = useState("");
  const [mode, setMode] = useState<"script" | "gpt">("script");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [voice, setVoice] = useState("");
  const [hd, setHd] = useState(true);
  const [busy, setBusy] = useState(false);

  const [voices, setVoices] = useState<Voice[]>([]);
  const [renders, setRenders] = useState<Render[]>([]);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const pollRef = useRef<number>(0);

  const avatar = useMemo(() => ready.find((a) => a.id === avatarId) || ready[0], [ready, avatarId]);

  useEffect(() => {
    API.voices().then(setVoices).catch(() => {});
    void loadRenders();
    // Render holatlari yangilanib turishi uchun (processing → done).
    const t = window.setInterval(loadRenders, 4000);
    return () => { window.clearInterval(t); window.clearInterval(pollRef.current); };
  }, []);

  useEffect(() => { if (avatar && !voice) setVoice(avatar.voice || ""); }, [avatar, voice]);

  async function loadRenders() {
    try { setRenders(await API.studioRenders()); } catch (e) { console.error(e); }
  }

  function cycleAvatar() {
    if (ready.length < 2) return;
    const i = ready.findIndex((a) => a.id === (avatar?.id));
    setAvatarId(ready[(i + 1) % ready.length].id);
  }

  async function generate() {
    if (!avatar) { toast("Avval tayyor avatar tanlang", "error"); return; }
    if (!text.trim()) { toast(mode === "gpt" ? "Mavzu yozing" : "Matn yozing", "error"); return; }
    setBusy(true);
    try {
      await API.studioRender({
        avatar_id: avatar.id, mode,
        text: mode === "script" ? text : "",
        prompt: mode === "gpt" ? text : "",
        voice: voice || avatar.voice || null, hd, title,
      });
      toast("Video render navbatiga qo'shildi", "success");
      setText(""); setTitle("");
      await loadRenders();
    } catch (e) { toast((e as Error).message, "error"); }
    finally { setBusy(false); }
  }

  async function remove(id: string) {
    try { await API.studioDeleteRender(id); setOpenId((o) => (o === id ? null : o)); await loadRenders(); toast("O'chirildi", "success"); }
    catch (e) { toast((e as Error).message, "error"); }
  }

  const shown = useMemo(() => renders.filter((r) =>
    (filter === "all" || r.state === filter) &&
    (r.title || "").toLowerCase().includes(q.toLowerCase())
  ), [renders, filter, q]);

  const near = text.length > MAX * 0.9;
  const openVideo = renders.find((r) => r.id === openId) || null;
  const confirmVideo = renders.find((r) => r.id === confirmId) || null;
  const voiceName = (id: string) => voices.find((v) => v.id === id)?.label || id;

  return (
    <div className="vstudio as-scroll" style={{ height: "100%", overflow: "auto" }}>
      <header className="vs-top">
        <div>
          <h1 className="title-h serif">Video Studiya</h1>
          <div className="title-sub">Offline video generatsiya · skript yoki GPT · kutubxonaga saqlanadi</div>
        </div>
      </header>

      {ready.length === 0 ? (
        <div className="layout"><div className="empty"><span className="serif">Tayyor avatar yo'q</span>Video uchun modeli qurilgan avatar kerak.</div></div>
      ) : (
        <div className="layout">
          {/* ── Composer ── */}
          <section className="composer">
            <div className="composer-head">
              <h2 className="serif">Yangi video</h2>
              <p>Avatar matnni o'qiydi va sahnaga chiqaradi. Skript yozing yoki GPT yordamida yarating.</p>
            </div>
            <div className="composer-body">
              <div className="field">
                <span className="eyebrow">Avatar</span>
                <div className="avatar-pick" onClick={cycleAvatar} title={ready.length > 1 ? "Almashtirish uchun bosing" : ""}>
                  <img className="avatar-thumb" src={API.photoUrl(avatar!.id)} alt="" />
                  <div className="avatar-meta">
                    <div className="nm">{avatar!.name}</div>
                    <div className="rl">{avatar!.role}</div>
                  </div>
                </div>
              </div>

              <div className="field">
                <span className="eyebrow">Manba</span>
                <div className="seg">
                  <button className={mode === "script" ? "on" : ""} onClick={() => setMode("script")}>Skript yozish</button>
                  <button className={mode === "gpt" ? "on" : ""} onClick={() => setMode("gpt")}>GPT'dan</button>
                </div>
              </div>

              <div className="field">
                <span className="eyebrow">Sarlavha</span>
                <input className="inp" placeholder="Masalan: Salomlashuv videosi" value={title} onChange={(e) => setTitle(e.target.value)} />
              </div>

              <div className="field">
                <div className="field-label">
                  <span className="eyebrow">{mode === "gpt" ? "GPT uchun mavzu" : "Matn — avatar shuni gapiradi"}</span>
                  <span className={"counter" + (near ? " near" : "")}>{text.length} / {MAX}</span>
                </div>
                <textarea className="txta" maxLength={MAX}
                  placeholder={mode === "gpt" ? "Mavzuni yozing, GPT skript tayyorlaydi…" : "Aytiladigan matnni yozing…"}
                  value={text} onChange={(e) => setText(e.target.value)} />
              </div>

              <div className="field">
                <span className="eyebrow">Ovoz</span>
                <div className="row-2">
                  <select className="sel" value={voice} onChange={(e) => setVoice(e.target.value)}>
                    {voices.map((v) => <option key={v.id} value={v.id}>{v.label || v.name || v.id}</option>)}
                  </select>
                  <label className={"toggle" + (hd ? " on" : "")} onClick={() => setHd(!hd)}>
                    <span className="track"><span className="knob" /></span>
                    <span className="lbl">HD sifat</span>
                  </label>
                </div>
              </div>

              <button className="btn-primary" disabled={busy} onClick={generate}>
                {busy ? <>Yuborilmoqda…</> : mode === "gpt" ? <><Ico.spark /> GPT bilan yaratish</> : <><Ico.play style={{ width: 15, height: 15 }} /> Video yaratish</>}
              </button>
            </div>
          </section>

          {/* ── Library ── */}
          <section className="library">
            <div className="lib-head">
              <div className="lib-title">
                <h2 className="serif">Kutubxona</h2>
                <span className="lib-count">{shown.length} / {renders.length} ta</span>
              </div>
              <div className="lib-tools">
                <div className="search">
                  <Ico.search />
                  <input placeholder="Qidirish…" value={q} onChange={(e) => setQ(e.target.value)} />
                </div>
                <div className="filter-tabs">
                  {FILTERS.map((f) => <button key={f.id} className={filter === f.id ? "on" : ""} onClick={() => setFilter(f.id)}>{f.label}</button>)}
                </div>
              </div>
            </div>

            <div className="grid">
              {shown.length === 0 ? (
                <div className="empty"><span className="serif">Hech narsa topilmadi</span>Boshqa filtr yoki qidiruv so'zini sinab ko'ring.</div>
              ) : shown.map((r, i) => {
                const ok = r.state === "done";
                return (
                  <article className="vcard" key={r.id} style={{ animationDelay: Math.min(i * 28, 360) + "ms" }}>
                    <div className={"thumb" + (ok ? " clickable" : "")} onClick={ok ? () => setOpenId(r.id) : undefined}>
                      {r.state === "processing" ? (
                        <div className="proc-overlay"><div className="proc-shimmer" /><div className="proc-spin" /><div className="proc-txt">Yaratilmoqda…</div></div>
                      ) : r.state === "error" ? (
                        <div className="err-overlay"><div className="et">Xatolik yuz berdi</div></div>
                      ) : (
                        <>
                          <video className="thumb-vid" src={API.studioVideoUrl(r.id) + "#t=0.7"} muted preload="metadata" playsInline
                            onLoadedMetadata={(e) => { try { e.currentTarget.currentTime = 0.7; } catch { /* */ } }} />
                          <div className="thumb-grad-overlay" />
                          <span className="badge ready"><span className="bdot" />Tayyor</span>
                          <button className="play"><Ico.play /></button>
                        </>
                      )}
                      {r.state === "processing" && <span className="badge proc"><span className="bdot" />Render</span>}
                      {r.state === "error" && <span className="badge err"><span className="bdot" />Xato</span>}
                    </div>
                    <div className="card-body">
                      <div className="card-title" title={r.title} onClick={ok ? () => setOpenId(r.id) : undefined} style={ok ? { cursor: "pointer" } : undefined}>{r.title}</div>
                      <div className="card-meta">
                        <span className="chip"><Ico.avatars />{r.avatar_name}</span>
                        <span className="chip"><Ico.mic />{voiceName(r.voice)}</span>
                        {r.hd && <span className="hd-chip">HD</span>}
                      </div>
                      <div className="card-actions">
                        <a className="act dl" href={ok ? API.studioVideoUrl(r.id) : undefined} download={`${r.title || r.id}.mp4`}
                          style={!ok ? { opacity: .4, pointerEvents: "none" } : undefined}><Ico.download /> Yuklab olish</a>
                        <button className="act del" onClick={() => setConfirmId(r.id)} title="O'chirish"><Ico.trash /></button>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        </div>
      )}

      {/* ── Modal pleyer ── */}
      {openVideo && (
        <div className="vstudio-modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setOpenId(null); }}>
          <div className="vstudio-modal">
            <button className="modal-close" onClick={() => setOpenId(null)}><Ico.close /></button>
            <div className="player">
              <video src={API.studioVideoUrl(openVideo.id)} controls autoPlay playsInline />
            </div>
            <div className="modal-side">
              <div className="ms-title">{openVideo.title}</div>
              <div className="ms-meta">
                <span className="ms-pill"><Ico.avatars />{openVideo.avatar_name}</span>
                <span className="ms-pill"><Ico.mic />{voiceName(openVideo.voice)}</span>
                {openVideo.hd && <span className="ms-pill hd">HD 1080p</span>}
              </div>
              <div className="field" style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                <div className="ms-script-label">
                  <span className="eyebrow">Skript</span>
                  <button className="act" style={{ padding: 0 }} onClick={() => { navigator.clipboard?.writeText(openVideo.text || ""); toast("Skript nusxalandi", "success"); }}>Nusxa olish</button>
                </div>
                <div className="ms-script">{openVideo.text || "Skript mavjud emas."}</div>
              </div>
              <div className="ms-actions">
                <a className="ms-btn primary" href={API.studioVideoUrl(openVideo.id)} download={`${openVideo.title || openVideo.id}.mp4`}><Ico.download /> Yuklab olish</a>
                <button className="ms-btn danger" onClick={() => setConfirmId(openVideo.id)}><Ico.trash /></button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── O'chirish dialogi ── */}
      {confirmVideo && (
        <div className="vstudio-confirm-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setConfirmId(null); }}>
          <div className="vstudio-confirm" role="alertdialog">
            <div className="ic"><Ico.alert /></div>
            <div className="ct">Videoni o'chirasizmi?</div>
            <div className="cm"><b>"{confirmVideo.title}"</b> kutubxonadan butunlay o'chiriladi. Bu amalni qaytarib bo'lmaydi.</div>
            <div className="ca">
              <button className="cf-cancel" onClick={() => setConfirmId(null)}>Bekor qilish</button>
              <button className="cf-delete" autoFocus onClick={() => { const id = confirmId!; setConfirmId(null); remove(id); }}>O'chirish</button>
            </div>
          </div>
        </div>
      )}

      <RenderProgress items={renders.filter((r) => r.state === "processing").map((r) => ({ id: r.id, title: r.title, photo: API.photoUrl(r.avatar_id) }))} />
    </div>
  );
}
