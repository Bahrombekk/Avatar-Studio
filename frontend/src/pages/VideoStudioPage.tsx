/* Video Studiya — offline HD video generatsiya (HeyGen uslubi).
   Avatar + skript (yoki GPT prompt) + ovoz → video render → kutubxona. */
import { useEffect, useMemo, useRef, useState } from "react";
import { Topbar } from "@/components/AdminShell";
import { Btn, Card, Segmented } from "@/components/ui/index.jsx";
import { I } from "@/lib/icons";
import { API, type Render } from "@/api/client";
import { useAvatars } from "@/context/AvatarsContext";
import { useToast } from "@/context/ToastContext";
import type { Voice } from "@/types/chat";

// Kutish bosqichlari (jonli ko'rsatish uchun). STAGE_T — har bosqich shu sekundgacha
// "tugagan" hisoblanadi (taxminiy; backend opaque). GEN_EST — taxminiy umumiy vaqt.
const GEN_STAGES = [
  { key: "text", label: "Matn tahlil qilinmoqda" },
  { key: "voice", label: "Ovoz tayyorlanmoqda" },
  { key: "face", label: "Avatar yuzi sozlanmoqda" },
  { key: "lip", label: "Lab harakati sinxronlanmoqda" },
  { key: "build", label: "Video yig'ilmoqda" },
];
const STAGE_T = [4, 11, 15, 24, 9999];
const GEN_EST = 26;

const FACTS = [
  "Bilasizmi? Afrosiyob soatiga ikki yuz ellik kilometr tezlikda yuradi.",
  "Maslahat: HD sifat tabiiyroq lab harakatini beradi.",
  "Bilasizmi? Avatar sanab o'tganda bosh tabiiy nod qiladi.",
  "Maslahat: qisqa va aniq jumlalar ravonroq talaffuz beradi.",
  "Bilasizmi? Sonlar va sanalar avtomatik so'z bilan o'qiladi.",
  "Maslahat: GPT rejimida faqat mavzu bersangiz, skriptni o'zi yozadi.",
  "Bilasizmi? Urg'uli gaplarda avatar biroz oldinga egiladi.",
];

export function VideoStudioPage() {
  const { avatars } = useAvatars();
  const { toast } = useToast();
  const ready = useMemo(() => avatars.filter((a) => a.real), [avatars]);

  const [avatarId, setAvatarId] = useState("");
  const [mode, setMode] = useState<"script" | "gpt">("script");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [prompt, setPrompt] = useState("");
  const [voice, setVoice] = useState("");
  const [hd, setHd] = useState(true);

  const [voices, setVoices] = useState<Voice[]>([]);
  const [renders, setRenders] = useState<Render[]>([]);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [factIdx, setFactIdx] = useState(0);
  const [justDone, setJustDone] = useState(false);   // "Tayyor!" qisqa bayrami
  const pollRef = useRef<number>(0);

  // Generatsiya davomida sekund hisoblagich.
  useEffect(() => {
    if (!busy) {
      setElapsed(0);
      return;
    }
    const t = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => window.clearInterval(t);
  }, [busy]);

  // Qiziqarli fakt/maslahat — har ~4.5s yangisi (yumshoq fade).
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => setFactIdx((i) => (i + 1) % FACTS.length), 4500);
    return () => window.clearInterval(t);
  }, [busy]);

  // Kutish holati: bosqich, foiz, qolgan vaqt.
  const curStage = busy ? STAGE_T.filter((t) => elapsed >= t).length : GEN_STAGES.length;
  const stageLabel = busy ? GEN_STAGES[curStage]?.label || "Yakunlanmoqda…" : "Tayyor!";
  const pct = busy ? Math.min(94, Math.round((elapsed / GEN_EST) * 100)) : 100;
  const remain = elapsed < GEN_EST ? `~${Math.max(1, GEN_EST - elapsed)}s qoldi` : "Deyarli tayyor…";

  const avatar = useMemo(
    () => ready.find((a) => a.id === avatarId) || ready[0],
    [ready, avatarId],
  );

  useEffect(() => {
    API.voices().then(setVoices).catch(() => {});
    void loadRenders();
    return () => window.clearInterval(pollRef.current);
  }, []);

  useEffect(() => {
    if (avatar && !voice) setVoice(avatar.voice || "");
  }, [avatar, voice]);

  async function loadRenders() {
    try {
      setRenders(await API.studioRenders());
    } catch (e) {
      console.error(e);
    }
  }

  async function generate() {
    if (!avatar) {
      toast("Avval tayyor avatar tanlang", "error");
      return;
    }
    if (mode === "script" && !text.trim()) {
      toast("Skript matnini yozing", "error");
      return;
    }
    if (mode === "gpt" && !prompt.trim()) {
      toast("Mavzu/prompt yozing", "error");
      return;
    }
    setBusy(true);
    try {
      const { render_id } = await API.studioRender({
        avatar_id: avatar.id,
        mode,
        text: mode === "script" ? text : "",
        prompt: mode === "gpt" ? prompt : "",
        voice: voice || avatar.voice || null,
        hd,
        title,
      });
      pollStatus(render_id);
    } catch (e) {
      setBusy(false);
      toast((e as Error).message, "error");
    }
  }

  function pollStatus(id: string) {
    window.clearInterval(pollRef.current);
    pollRef.current = window.setInterval(async () => {
      try {
        const s = await API.studioRenderStatus(id);
        if (s.state === "done") {
          window.clearInterval(pollRef.current);
          setBusy(false);
          setJustDone(true);   // qisqa "Tayyor!" holati
          window.setTimeout(() => setJustDone(false), 1600);
          toast("Video tayyor!", "success");
          await loadRenders();
        } else if (s.state === "error") {
          window.clearInterval(pollRef.current);
          setBusy(false);
          toast("Xato: " + (s.error || "noma'lum"), "error");
        }
      } catch {
        /* keyingi pollda qayta urinadi */
      }
    }, 2500);
  }

  async function remove(id: string) {
    try {
      await API.studioDeleteRender(id);
      await loadRenders();
      toast("O'chirildi", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  return (
    <div className="pg as-scroll">
      <Topbar title="Video Studiya" sub="Offline video generatsiya — skript yoki GPT, kutubxonaga saqlanadi" />
      <div className="pg-body vs-wrap">
        {ready.length === 0 ? (
          <Card className="vs-empty" style={{}}>
            <I.bolt size={26} />
            <div>Video generatsiya uchun <b>modeli tayyor</b> avatar kerak.</div>
            <div className="as-label">Avatar yarating → Idle + Artefakt quring.</div>
          </Card>
        ) : (
          <div className="vs-grid">
            {/* ── Render formasi ── */}
            <Card className="vs-form" style={{}}>
              <div className="vs-h">Yangi video</div>

              <label className="as-label">Avatar</label>
              <select className="vs-input" value={avatar?.id || ""}
                onChange={(e) => setAvatarId(e.target.value)}>
                {ready.map((a) => <option key={a.id} value={a.id}>{a.name} · {a.role}</option>)}
              </select>

              <label className="as-label">Manba</label>
              <Segmented value={mode} onChange={(v: string) => setMode(v as "script" | "gpt")}
                options={[{ value: "script", label: "Skript yozish" }, { value: "gpt", label: "GPT'dan" }]} />

              <label className="as-label">Sarlavha</label>
              <input className="vs-input" value={title} placeholder="Masalan: Salomlashuv videosi"
                onChange={(e) => setTitle(e.target.value)} />

              {mode === "script" ? (
                <>
                  <label className="as-label">Matn (avatar AYNAN shuni gapiradi)</label>
                  <textarea className="vs-input vs-ta" rows={6} value={text}
                    placeholder="Aytiladigan matnni yozing…"
                    onChange={(e) => setText(e.target.value)} />
                  <div className="vs-cnt">{text.length} / 2000</div>
                </>
              ) : (
                <>
                  <label className="as-label">Mavzu / ko'rsatma (GPT skript yozadi)</label>
                  <textarea className="vs-input vs-ta" rows={4} value={prompt}
                    placeholder="Masalan: Bandlik markazi xizmatlari haqida 4 jumlalik tanishtiruv"
                    onChange={(e) => setPrompt(e.target.value)} />
                </>
              )}

              <div className="vs-row">
                <div style={{ flex: 1 }}>
                  <label className="as-label">Ovoz</label>
                  <select className="vs-input" value={voice}
                    onChange={(e) => setVoice(e.target.value)}>
                    {voices.map((v) => <option key={v.id} value={v.id}>{v.label || v.name || v.id}</option>)}
                  </select>
                </div>
                <label className="vs-hd">
                  <input type="checkbox" checked={hd} onChange={(e) => setHd(e.target.checked)} />
                  HD sifat
                </label>
              </div>

              <Btn kind="primary" icon="play" onClick={generate} disabled={busy}>
                {busy ? "Generatsiya…" : "Video yaratish"}
              </Btn>

              {(busy || justDone) && (
                <div className="vs-overlay">
                <div className={"vs-gen" + (justDone ? " done" : "")}>
                  {/* avatar preview (nafas olib turadi) + ovoz to'lqini */}
                  <div className="vs-gen-top">
                    {avatar && <img className="vs-gen-av" src={API.photoUrl(avatar.id)} alt="" />}
                    <div className="vs-gen-wave" aria-hidden="true">
                      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
                        <span key={i} style={{ animationDelay: `${i * 0.1}s` }} />
                      ))}
                    </div>
                  </div>
                  {/* silliq gradient + shimmer progress */}
                  <div className="vs-pbar">
                    <div className="vs-pbar-fill" style={{ width: pct + "%" }} />
                  </div>
                  <div className="vs-gen-meta">
                    <span className="vs-gen-stage">
                      {justDone ? <I.check size={14} /> : <span className="vs-spin" />}
                      {stageLabel}
                    </span>
                    <span className="vs-prog-time">{busy ? remain : "100%"}</span>
                  </div>
                  {/* bosqichlar — tugaganda ✓ */}
                  <ul className="vs-steps">
                    {GEN_STAGES.map((s, i) => {
                      const st = justDone || i < curStage ? "done"
                        : i === curStage ? "active" : "pending";
                      return (
                        <li key={s.key} className={"vs-step " + st}>
                          <span className="vs-step-ic">{st === "done" ? "✓" : st === "active" ? "•" : ""}</span>
                          {s.label}
                        </li>
                      );
                    })}
                  </ul>
                  {/* qiziqarli fakt/maslahat — yumshoq almashadi */}
                  {busy && <div className="vs-fact" key={factIdx}>{FACTS[factIdx]}</div>}
                </div>
                </div>
              )}
            </Card>

            {/* ── Kutubxona ── */}
            <div className="vs-lib">
              <div className="vs-h">Kutubxona · {renders.length} ta</div>
              {renders.length === 0 && <div className="as-label">Hali video yo'q.</div>}
              <div className="vs-lib-grid">
                {renders.map((r) => (
                  <Card key={r.id} className="vs-item" style={{}}>
                    <video className="vs-video" src={API.studioVideoUrl(r.id)}
                      controls preload="metadata" playsInline />
                    <div className="vs-item-t">{r.title}</div>
                    <div className="as-label vs-item-m">
                      {r.avatar_name} · {r.voice} {r.hd ? "· HD" : ""}
                    </div>
                    <div className="vs-item-foot">
                      <a className="vs-dl" href={API.studioVideoUrl(r.id)} download={`${r.title || r.id}.mp4`}>
                        <I.chevron size={13} /> Yuklab olish
                      </a>
                      <button className="vs-del" onClick={() => remove(r.id)} title="O'chirish">
                        <I.x size={14} />
                      </button>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
