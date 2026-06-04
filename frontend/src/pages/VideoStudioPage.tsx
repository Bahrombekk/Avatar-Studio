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
  const pollRef = useRef<number>(0);

  // Generatsiya davomida sekund hisoblagich (qiziqarli progress uchun).
  useEffect(() => {
    if (!busy) {
      setElapsed(0);
      return;
    }
    const t = window.setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => window.clearInterval(t);
  }, [busy]);

  const stageMsg =
    elapsed < 3 ? "Matn tayyorlanmoqda…"
    : elapsed < 9 ? "Ovoz sintez qilinmoqda…"
    : elapsed < 22 ? "Video kadrlari yaratilmoqda…"
    : "Yakunlanmoqda…";

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
              {busy && (
                <div className="vs-prog">
                  <div className="vs-bar"><div className="vs-bar-fill" /></div>
                  <div className="vs-prog-msg">
                    <span className="vs-prog-stage"><span className="vs-spin" />{stageMsg}</span>
                    <span className="vs-prog-time">{elapsed}s</span>
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
