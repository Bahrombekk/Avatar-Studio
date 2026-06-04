/* Real-time ovozli suhbat — streaming STT + idle-loop + progressive video.
   Mikrofon XOM PCM (16k) qilib gapirayotganda WS orqali Yandex streaming STT'ga
   oqadi → to'xtaganda matn deyarli tayyor. Avatar idle loopda turadi; javob video
   generatsiya paytida progressive oqadi. Eski chat logikasiga tegmaydi. */
import { useEffect, useMemo, useRef, useState } from "react";
import { I } from "@/lib/icons";
import { API } from "@/api/client";
import { openRealtimeWS } from "@/api/realtime";
import { useAvatars } from "@/context/AvatarsContext";
import type { Avatar } from "@/types/avatar";

type Turn = { role: "user" | "avatar"; text: string; streaming?: boolean };

export function RealtimePage() {
  const { avatars } = useAvatars();
  const ready = useMemo(() => avatars.filter((a) => a.real), [avatars]);
  const [avatarId, setAvatarId] = useState<string>("");
  const avatar: Avatar | undefined = useMemo(
    () => ready.find((a) => a.id === avatarId) || ready[0],
    [ready, avatarId],
  );

  const [connected, setConnected] = useState(false);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [answerUrl, setAnswerUrl] = useState<string | null>(null);
  const [answerFading, setAnswerFading] = useState(false);
  const [metrics, setMetrics] = useState<
    { stt: number; gpt: number; tts: number; video: number | null } | null
  >(null);

  const wsRef = useRef<WebSocket | null>(null);
  const idleRef = useRef<HTMLVideoElement | null>(null);
  const answerRef = useRef<HTMLVideoElement | null>(null);
  const streamAtRef = useRef<number>(0);
  // Kadr-sinxron handoff: gapirish to'xtaganda idle qaysi kadrda turgani.
  const startFrameRef = useRef<number>(0);
  const answerPlayStartRef = useRef<number>(0);   // javob o'ynashni boshlagan vaqt
  const fadeTimerRef = useRef<number>(0);
  const fps = Number(avatar?.fps) || 25;
  // Audio capture
  const ctxRef = useRef<AudioContext | null>(null);
  const procRef = useRef<ScriptProcessorNode | null>(null);
  const mediaRef = useRef<MediaStream | null>(null);
  const recordingRef = useRef(false);

  // WebSocket
  useEffect(() => {
    if (!avatar) return;
    setError("");
    setAnswerUrl(null);
    const ws = openRealtimeWS(
      avatar.id,
      avatar.voice || "",
      (type, data) => {
        if (type === "listening") setStatus("Tinglanmoqda…");
        else if (type === "transcript") {
          const t = String(data.text || "");
          if (t) setTurns((p) => [...p, { role: "user", text: t }]);
          setStatus("Javob tayyorlanmoqda…");
          setMetrics({ stt: Number(data.t) || 0, gpt: 0, tts: 0, video: null });
        } else if (type === "token") {
          // GPT token oqimi — javob matni jonli yoziladi.
          const d = String(data.text || "");
          if (!d) return;
          setTurns((p) => {
            const last = p[p.length - 1];
            if (last && last.role === "avatar" && last.streaming) {
              const c = p.slice();
              c[c.length - 1] = { ...last, text: last.text + d };
              return c;
            }
            return [...p, { role: "avatar", text: d, streaming: true }];
          });
        } else if (type === "text") {
          // To'liq javob — jonli matnni yakunlaymiz (kesilgan bo'shliqlar bilan).
          const t = String(data.text || "");
          setTurns((p) => {
            const last = p[p.length - 1];
            if (last && last.role === "avatar" && last.streaming) {
              const c = p.slice();
              c[c.length - 1] = { role: "avatar", text: t || last.text };
              return c;
            }
            return t ? [...p, { role: "avatar", text: t }] : p;
          });
          setMetrics((m) => (m ? { ...m, gpt: Number(data.t) || m.gpt } : m));
        } else if (type === "stream" || type === "video") {
          const tm = (data.timing as { gpt?: number; tts?: number }) || {};
          setMetrics((m) =>
            m ? { ...m, gpt: tm.gpt ?? 0, tts: tm.tts ?? 0 } : m,
          );
          streamAtRef.current = performance.now();
          answerPlayStartRef.current = 0;
          window.clearTimeout(fadeTimerRef.current);
          setStatus("");
          setBusy(false);
          setAnswerFading(false);
          setAnswerUrl(String(data.url));
        } else if (type === "error") {
          setError(String(data.message || "Xatolik"));
          setStatus("");
          setBusy(false);
        } else if (type === "done") {
          setBusy(false);
          setStatus("");
        }
      },
      () => setConnected(true),
      () => setConnected(false),
    );
    wsRef.current = ws;
    const ping = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 20000);
    return () => {
      window.clearInterval(ping);
      try { ws.close(); } catch { /* ignore */ }
    };
  }, [avatar?.id, avatar?.voice]);

  // Idle loop — ref orqali majburiy muted+play (qora bo'lmasligi uchun)
  useEffect(() => {
    const v = idleRef.current;
    if (!v || !avatar) return;
    v.muted = true;
    v.load();
    const tryPlay = () => v.play().catch(() => {});
    tryPlay();
    v.addEventListener("canplay", tryPlay);
    return () => v.removeEventListener("canplay", tryPlay);
  }, [avatar?.id]);

  useEffect(() => {
    if (answerUrl && answerRef.current) {
      answerRef.current.load();
      answerRef.current.play().catch(() => {});
    }
  }, [answerUrl]);

  function stopCapture() {
    recordingRef.current = false;
    try { procRef.current?.disconnect(); } catch { /* ignore */ }
    procRef.current = null;
    try { mediaRef.current?.getTracks().forEach((t) => t.stop()); } catch { /* ignore */ }
    mediaRef.current = null;
    if (ctxRef.current) { ctxRef.current.close().catch(() => {}); ctxRef.current = null; }
  }

  async function startRecording() {
    setError("");
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError("Aloqa yo'q — sahifani yangilang");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Mikrofon ruxsati berilmadi");
      return;
    }
    mediaRef.current = stream;
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx({ sampleRate: 16000 });
    ctxRef.current = ctx;
    const src = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    procRef.current = proc;

    ws.send("start");
    recordingRef.current = true;
    setRecording(true);
    setStatus("Tinglanmoqda…");

    let speech = false;
    let silenceStart = 0;
    const startedAt = performance.now();
    const SIL_MS = 1100, THRESH = 0.015, MAX_MS = 20000;

    proc.onaudioprocess = (e) => {
      if (!recordingRef.current) return;
      const f32 = e.inputBuffer.getChannelData(0);
      // VAD
      let sum = 0;
      for (let i = 0; i < f32.length; i++) sum += f32[i] * f32[i];
      const rms = Math.sqrt(sum / f32.length);
      const now = performance.now();
      if (rms > THRESH) { speech = true; silenceStart = 0; }
      else if (speech) {
        if (!silenceStart) silenceStart = now;
        else if (now - silenceStart > SIL_MS) { stopRecording(); return; }
      }
      if (now - startedAt > MAX_MS) { stopRecording(); return; }
      // Float32 → Int16 PCM → WS
      const i16 = new Int16Array(f32.length);
      for (let i = 0; i < f32.length; i++) {
        const s = Math.max(-1, Math.min(1, f32[i]));
        i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      if (ws.readyState === WebSocket.OPEN) ws.send(i16.buffer);
    };
    src.connect(proc);
    proc.connect(ctx.destination);   // ba'zi brauzerlarda onaudioprocess uchun shart
  }

  function stopRecording() {
    if (!recordingRef.current) return;
    stopCapture();
    setRecording(false);
    setBusy(true);
    setStatus("Tinglanmoqda…");
    // Jonli idle videosi qaysi kadrda turibdi → javob aynan shu pozadan boshlansin
    // (kadr-sinxron handoff → idle→javob o'tishida bosh/ko'z sakramaydi).
    const idle = idleRef.current;
    let frame = 0;
    if (idle && idle.duration) {
      const total = Math.max(1, Math.round(idle.duration * fps));
      frame = Math.round(idle.currentTime * fps) % total;
    }
    startFrameRef.current = frame;
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send("stop:" + frame);
    }
  }

  useEffect(() => () => { stopCapture(); }, []);

  const toggleMic = () => (recording ? stopRecording() : startRecording());

  return (
    <div className="rt-wrap">
      <div className="rt-top">
        <div className="rt-brand"><I.layers size={18} /> Avatar Studio · <span>Jonli suhbat</span></div>
        <div className="rt-top-r">
          <span className={"rt-dot" + (connected ? " on" : "")} />
          <span className="rt-conn">{connected ? "Ulangan" : "Ulanmoqda…"}</span>
          {ready.length > 0 && (
            <select className="rt-select" value={avatar?.id || ""}
              onChange={(e) => setAvatarId(e.target.value)}>
              {ready.map((a) => (
                <option key={a.id} value={a.id}>{a.name} · {a.voice}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {!avatar ? (
        <div className="rt-empty">
          <I.bolt size={28} />
          <div>Ovozli suhbat uchun <b>modeli tayyor</b> avatar kerak.</div>
          <div className="rt-empty-sub">Avatar yarating → Idle + Artefakt quring.</div>
        </div>
      ) : (
        <div className="rt-stage">
          <div className={"rt-avatar" + (busy ? " busy" : "") + (recording ? " listening" : "")}>
            <img className="rt-media rt-base" src={API.photoUrl(avatar.id)} alt={avatar.name} />
            <video ref={idleRef} className="rt-media rt-idle" src={API.idleUrl(avatar.id)}
              loop muted autoPlay playsInline preload="auto" />
            {answerUrl && (
              <video ref={answerRef}
                className={"rt-media rt-answer" + (answerFading ? " rt-fade" : "")}
                src={answerUrl}
                autoPlay playsInline preload="auto"
                onPlaying={() => {
                  if (!answerPlayStartRef.current) answerPlayStartRef.current = performance.now();
                  if (streamAtRef.current) {
                    const v = (performance.now() - streamAtRef.current) / 1000;
                    streamAtRef.current = 0;
                    setMetrics((m) => (m ? { ...m, video: Math.round(v * 100) / 100 } : m));
                  }
                }}
                onEnded={() => {
                  // Idle'ni javob tugagan kadrdan davom ettiramiz (kadr-sinxron handoff).
                  // Javob davomiyligini HAQIQIY o'ynash vaqtidan olamiz — fragmented mp4'da
                  // video.duration NaN/Infinity bo'lishi mumkin (metadata yo'q).
                  const idle = idleRef.current;
                  if (idle && idle.duration) {
                    const M = Math.max(1, Math.round(idle.duration * fps));
                    const elapsed = answerPlayStartRef.current
                      ? (performance.now() - answerPlayStartRef.current) / 1000 : 0;
                    const N = Math.round(elapsed * fps);
                    const resume = (((startFrameRef.current + N) % M) + M) % M;
                    try { idle.currentTime = resume / fps; idle.play().catch(() => {}); } catch { /* ignore */ }
                  }
                  answerPlayStartRef.current = 0;
                  // Silliq crossfade: javobni so'ndirib idle'ni ochamiz (og'iz/kadr farqi yashirinadi).
                  setAnswerFading(true);
                  window.clearTimeout(fadeTimerRef.current);
                  fadeTimerRef.current = window.setTimeout(() => {
                    setAnswerUrl(null);
                    setAnswerFading(false);
                  }, 300);
                }} />
            )}
            {(recording || busy) && (
              <div className={"rt-state " + (recording ? "listen" : "think")}>
                <span className="rt-state-ind" />
                {recording ? "Tinglayapman…" : "O'ylayapman…"}
              </div>
            )}
            <div className="rt-name">{avatar.name}<small>{avatar.role}</small></div>
            {busy && <div className="rt-progress"><div className="ed-progress-bar" /></div>}
          </div>

          <div className="rt-side">
            <div className="rt-log">
              {turns.length === 0 && (
                <div className="rt-hint">Mikrofon tugmasini bosib gapiring — gapirib bo'lgach o'zi to'xtaydi.</div>
              )}
              {turns.map((t, i) => (
                <div key={i} className={"rt-turn " + t.role}>
                  <span className="rt-turn-who">{t.role === "user" ? "Siz" : avatar.name}</span>
                  <span className="rt-turn-text">{t.text}</span>
                </div>
              ))}
            </div>

            {error && <div className="rt-err"><I.x size={13} /> {error}</div>}
            {status && !error && <div className="rt-status">{status}</div>}

            {metrics && (
              <div className="rt-metrics">
                <div><span>STT</span><b>{metrics.stt.toFixed(1)}s</b></div>
                <div><span>GPT</span><b>{metrics.gpt.toFixed(1)}s</b></div>
                <div><span>TTS</span><b>{metrics.tts.toFixed(1)}s</b></div>
                <div><span>Video</span><b>{metrics.video != null ? metrics.video.toFixed(1) + "s" : "…"}</b></div>
                <div className="rt-metrics-total">
                  <span>Gapirguncha</span>
                  <b>{(metrics.stt + metrics.gpt + metrics.tts + (metrics.video || 0)).toFixed(1)}s</b>
                </div>
              </div>
            )}

            <button className={"rt-mic" + (recording ? " rec" : "")} onClick={toggleMic}
              disabled={busy && !recording}>
              <I.mic size={20} />
              {recording ? "Tinglanmoqda… (to'xtatish)" : busy ? "O'ylanmoqda…" : "Gapirish"}
            </button>
            <div className="rt-tip">Yandex streaming STT · {avatar.language?.toUpperCase()}</div>
          </div>
        </div>
      )}
    </div>
  );
}
