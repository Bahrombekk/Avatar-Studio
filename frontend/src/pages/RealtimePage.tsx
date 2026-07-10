/* Real-time ovozli suhbat — streaming STT + idle-loop + progressive video.
   Mikrofon XOM PCM (16k) qilib gapirayotganda WS orqali Yandex streaming STT'ga
   oqadi → to'xtaganda matn deyarli tayyor. Avatar idle loopda turadi; javob video
   generatsiya paytida progressive oqadi. Eski chat logikasiga tegmaydi. */
import { useEffect, useMemo, useRef, useState } from "react";
import { I } from "@/lib/icons";
import { API } from "@/api/client";
import { openRealtimeWS } from "@/api/realtime";
import { useAvatars } from "@/context/AvatarsContext";
import { useTweaksCtx } from "@/context/TweaksContext";
import { useT, LANGS } from "@/i18n";
import type { Avatar } from "@/types/avatar";

type Turn = { role: "user" | "avatar"; text: string; streaming?: boolean };

// HTTP resurslar (backend qaytaradigan video-oqim /api/... URL) uchun base-prefiks
// (dev "", Spark "/avatar") — Spark'da /avatar/api/ nginx location orqali o'tsin.
// (WS esa alohida root /api/ws/avatar/realtime — realtime.ts'da.)
const HTTP_BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

export function RealtimePage() {
  const { avatars } = useAvatars();
  const tr = useT();
  const { setTweak } = useTweaksCtx();
  const ready = useMemo(() => avatars.filter((a) => a.real), [avatars]);
  const [avatarId, setAvatarId] = useState<string>("");
  const avatar: Avatar | undefined = useMemo(
    () => ready.find((a) => a.id === avatarId) || ready[0],
    [ready, avatarId],
  );

  // Suhbat tili (jonli sahifa dropdownidan) — avatar standart tilidan boshlanadi.
  // O'zgarsa WS shu til bilan qayta ulanadi; ovoz avatar.langVoices[til] dan olinadi.
  const [convLang, setConvLang] = useState<string>("");
  useEffect(() => {
    if (avatar) setConvLang(((avatar as Avatar & { language?: string }).language) || "uz");
  }, [avatar?.id]);   // eslint-disable-line react-hooks/exhaustive-deps
  const effLang = convLang || (avatar as (Avatar & { language?: string }) | undefined)?.language || "uz";
  const langVoices = (avatar as (Avatar & { langVoices?: Record<string, string> }) | undefined)?.langVoices || {};
  const effVoice = langVoices[effLang] || avatar?.voice || "";

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
  // Avto-suhbat (qo'lsiz): yoqilsa javob tugagach avtomatik qayta tinglaydi →
  // uzluksiz aylanma suhbat (masalan boshqa AI bilan). Speak bosish shart emas.
  const [auto, setAuto] = useState(false);
  const autoRef = useRef(false);
  useEffect(() => { autoRef.current = auto; }, [auto]);

  const wsRef = useRef<WebSocket | null>(null);
  const idleRef = useRef<HTMLVideoElement | null>(null);
  const answerRef = useRef<HTMLVideoElement | null>(null);
  const streamAtRef = useRef<number>(0);
  // Barge-in: eng so'nggi navbat raqami — eski (bo'lib qo'yilgan) javob eventlari e'tiborsiz.
  const latestTurnRef = useRef<number>(0);
  // Kadr-sinxron handoff: gapirish to'xtaganda idle qaysi kadrda turgani.
  const startFrameRef = useRef<number>(0);
  const answerPlayStartRef = useRef<number>(0);   // javob o'ynashni boshlagan vaqt
  const fadeTimerRef = useRef<number>(0);
  // Stall-watchdog: javob videosi muzlab qolsa (currentTime ilgarilamasa) tiklash.
  const stallTimerRef = useRef<number>(0);
  const lastVidRef = useRef<{ t: number; at: number }>({ t: 0, at: 0 });
  const finishingRef = useRef(false);   // javob yakunlanmoqda (ikki marta bo'lmasin)
  const fps = Number(avatar?.fps) || 25;
  // Audio capture
  const ctxRef = useRef<AudioContext | null>(null);
  const procRef = useRef<ScriptProcessorNode | null>(null);
  const mediaRef = useRef<MediaStream | null>(null);
  const recordingRef = useRef(false);
  // Tugma ichidagi mini-waveform — ovoz sathi (mikrofon RMS + avatar audio analyser).
  const micLevelRef = useRef(0);       // foydalanuvchi mikrofon sathi (0..~0.15)
  const avatarLevelRef = useRef(0);    // avatar ovozi sathi (analyser RMS 0..~0.4)
  const waveCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const phaseRef = useRef<"idle" | "listening" | "thinking" | "speaking">("idle");

  // WebSocket
  useEffect(() => {
    if (!avatar) return;
    setError("");
    setAnswerUrl(null);
    const ws = openRealtimeWS(
      avatar.id,
      effVoice,
      (type, data) => {
        // Barge-in turn-filtri: yangi navbat (transcript) raqamini eslab qolamiz;
        // eski navbatga tegishli (bo'lib qo'yilgan javob) eventlarni e'tiborsiz qoldiramiz.
        const evTurn = typeof data.turn === "number" ? (data.turn as number) : null;
        if (type === "transcript" && evTurn != null) latestTurnRef.current = evTurn;
        else if (evTurn != null && evTurn < latestTurnRef.current) return;

        if (type === "listening") setStatus("Tinglanmoqda…");
        else if (type === "canceled") {
          // Server javobni bo'ldi (barge-in) — holatni tozalaymiz.
          setBusy(false);
          setStatus("");
        } else if (type === "transcript") {
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
          stopStallWatch();
          finishingRef.current = false;   // yangi javob — yakunlash bayrog'ini tiklaymiz
          setStatus("");
          setBusy(false);
          setAnswerFading(false);
          setAnswerUrl(HTTP_BASE + String(data.url));
        } else if (type === "error") {
          setError(String(data.message || "Xatolik"));
          setStatus("");
          setBusy(false);
          autoRelisten(900);   // avto: nutq topilmadi/xato → qayta tinglash
        } else if (type === "done") {
          setBusy(false);
          setStatus("");
        }
      },
      () => setConnected(true),
      () => setConnected(false),
      effLang,
    );
    wsRef.current = ws;
    const ping = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 20000);
    return () => {
      window.clearInterval(ping);
      try { ws.close(); } catch { /* ignore */ }
    };
  }, [avatar?.id, effVoice, effLang]);

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
    micLevelRef.current = 0;
    try { procRef.current?.disconnect(); } catch { /* ignore */ }
    procRef.current = null;
    try { mediaRef.current?.getTracks().forEach((t) => t.stop()); } catch { /* ignore */ }
    mediaRef.current = null;
    if (ctxRef.current) { ctxRef.current.close().catch(() => {}); ctxRef.current = null; }
  }

  // Avto rejim: javob tugagach (yoki nutq topilmasa) qayta tinglashni boshlaydi.
  function autoRelisten(delay = 500) {
    if (!autoRef.current) return;
    window.setTimeout(() => {
      if (autoRef.current && !recordingRef.current) startRecording();
    }, delay);
  }
  function toggleAuto() {
    const next = !autoRef.current;
    autoRef.current = next;
    setAuto(next);
    if (next && !recordingRef.current && !busy) startRecording();
    else if (!next) stopCapture();
  }

  // Javobni yakunlash — idle'ga KADR-SINXRON qaytish + fade + (avto) qayta tinglash.
  // onEnded (tabiiy tugash), onError (video xatosi) VA stall-watchdog (muzlash) shu
  // yerga keladi. finishingRef bilan bir javob uchun BIR MARTA bajariladi.
  function finishAnswer() {
    if (finishingRef.current) return;
    finishingRef.current = true;
    stopStallWatch();
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
    setAnswerFading(true);
    window.clearTimeout(fadeTimerRef.current);
    fadeTimerRef.current = window.setTimeout(() => {
      setAnswerFading(false);
      setAnswerUrl(null);
    }, 300);
    autoRelisten(450);   // avto rejim: keyingi navbatni tinglash
  }

  function stopStallWatch() {
    if (stallTimerRef.current) {
      window.clearInterval(stallTimerRef.current);
      stallTimerRef.current = 0;
    }
  }

  // Javob o'ynay boshlaganda ishga tushadi: currentTime ~7s ilgarilamasa (server
  // gap-fill paytida ham vaqt yuradi → "o'ylash" pauzasi tegmaydi; faqat HAQIQIY
  // muzlash) videoni muzlagan deb tiklaymiz (aks holda foydalanuvchi gapirmaguncha
  // qotib qolardi). Server-watchdog GPU slotni bo'shatadi; bu UI'ni tiklaydi.
  function startStallWatch() {
    stopStallWatch();
    lastVidRef.current = { t: -1, at: performance.now() };
    stallTimerRef.current = window.setInterval(() => {
      const v = answerRef.current;
      if (!v) { stopStallWatch(); return; }
      const now = performance.now();
      if (v.currentTime > lastVidRef.current.t + 0.05) {
        lastVidRef.current = { t: v.currentTime, at: now };   // ilgarilayapti
      } else if (now - lastVidRef.current.at > 7000) {
        finishAnswer();   // 7s muzladi → tiklaymiz
      }
    }, 2000);
  }

  async function startRecording() {
    setError("");
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError(tr("rt.noConn"));
      return;
    }
    // Barge-in: javob hali o'ynayotgan bo'lsa, uni darrov to'xtatib idle'ga qaytamiz.
    // Server "start"ni implicit barge sifatida qabul qiladi (joriy javobni bekor qiladi);
    // <video>'ni unmount qilish brauzerdagi oqim GET'ini ham bekor qiladi.
    if (answerUrl) {
      window.clearTimeout(fadeTimerRef.current);
      stopStallWatch();
      finishingRef.current = false;
      setAnswerFading(false);
      setAnswerUrl(null);
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          noiseSuppression: true,    // brauzer shovqin bostirish (eng samarali)
          echoCancellation: true,    // aks-sado bostirish
          autoGainControl: true,     // sathni avtomatik tekislash
          channelCount: 1,
        },
      });
    } catch {
      setError(tr("rt.micDenied"));
      return;
    }
    mediaRef.current = stream;
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx({ sampleRate: 16000 });
    ctxRef.current = ctx;
    const src = ctx.createMediaStreamSource(stream);
    // ── Shovqin filtri (Yandex'ga toza nutq) ── nutq diapazoni ≈90–7500Hz:
    //   high-pass → past gum/rumble (ventilyator, shamol) kesiladi;
    //   low-pass → yuqori hiss/shitir kesiladi; kompressor → sathni tekislaydi.
    const hp = ctx.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 90; hp.Q.value = 0.7;
    const lp = ctx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 7500;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -45; comp.knee.value = 25; comp.ratio.value = 4;
    comp.attack.value = 0.004; comp.release.value = 0.18;
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
      micLevelRef.current = rms;   // orb vizualizator uchun jonli sath
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
    src.connect(hp); hp.connect(lp); lp.connect(comp); comp.connect(proc);
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

  // ── Orb holati: tinglash / o'ylash / gapirish / bo'sh ────────────────────
  useEffect(() => {
    phaseRef.current = recording ? "listening"
      : answerUrl ? "speaking"
      : busy ? "thinking" : "idle";
  }, [recording, answerUrl, busy]);

  // ── Avatar ovozi analyser: javob videosi audiosini o'lchab orb'ni tebratadi.
  //    Video key={answerUrl} bilan qayta ulanadi → har javobda yangi DOM node,
  //    shuning uchun createMediaElementSource (element uchun bir marta) xato bermaydi. */
  useEffect(() => {
    if (!answerUrl) { avatarLevelRef.current = 0; return; }
    const v = answerRef.current;
    if (!v) return;
    let ctx: AudioContext | null = null;
    let src: MediaElementAudioSourceNode | null = null;
    let analyser: AnalyserNode | null = null;
    let raf = 0;
    try {
      const Ctx = window.AudioContext
        || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      ctx = new Ctx();
      ctx.resume().catch(() => {});
      src = ctx.createMediaElementSource(v);
      analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      src.connect(analyser);
      analyser.connect(ctx.destination);   // audio o'chib qolmasin — chiqishga ulaymiz
      const data = new Uint8Array(analyser.fftSize);
      const tick = () => {
        analyser!.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) { const x = (data[i] - 128) / 128; sum += x * x; }
        avatarLevelRef.current = Math.sqrt(sum / data.length);
        raf = requestAnimationFrame(tick);
      };
      tick();
    } catch { /* analyser bo'lmasa orb sintetik "gapirish" bilan jonlanadi */ }
    return () => {
      if (raf) cancelAnimationFrame(raf);
      try { src?.disconnect(); analyser?.disconnect(); } catch { /* ignore */ }
      try { ctx?.close(); } catch { /* ignore */ }
      avatarLevelRef.current = 0;
    };
  }, [answerUrl]);

  // ── Mini-waveform (CTA tugma ichida) — ovozga reaktiv ekvalayzer chiziqlari. */
  useEffect(() => {
    const canvas = waveCanvasRef.current;
    if (!canvas) return;
    const g = canvas.getContext("2d");
    if (!g) return;
    let raf = 0;
    const N = 16;                        // ustunlar soni
    const smooth = new Array(N).fill(0.15);
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const cw = canvas.clientWidth, ch = canvas.clientHeight;
      if (!cw || !ch) return;
      if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) {
        canvas.width = Math.round(cw * dpr); canvas.height = Math.round(ch * dpr);
      }
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, cw, ch);
      const t = performance.now();
      const phase = phaseRef.current;
      let level: number;
      if (phase === "listening") level = Math.min(micLevelRef.current * 7, 1);
      else if (phase === "speaking") level = Math.min(avatarLevelRef.current * 3.2, 1);
      else if (phase === "thinking") level = 0.3 + 0.2 * Math.sin(t / 280);
      else level = 0.16;
      const bw = cw / N;
      for (let i = 0; i < N; i++) {
        // Har ustun o'z fazasida tebranadi; ovoz sathi amplitudani boshqaradi.
        const osc = 0.35 + 0.65 * Math.abs(Math.sin(t / (160 + i * 23) + i * 1.7));
        const target = Math.max(0.1, Math.min(1, level * (0.5 + osc)));
        smooth[i] += (target - smooth[i]) * 0.25;
        const h = Math.max(2, smooth[i] * ch * 0.92);
        const x = i * bw + bw * 0.28;
        g.fillStyle = "rgba(255,255,255,.85)";
        const r = Math.min(bw * 0.22, 2);
        const y = (ch - h) / 2;
        g.beginPath();
        // roundRect hamma brauzerda bor (Chrome 99+); fallback oddiy rect.
        if (g.roundRect) g.roundRect(x, y, bw * 0.44, h, r);
        else g.rect(x, y, bw * 0.44, h);
        g.fill();
      }
    };
    draw();
    return () => { if (raf) cancelAnimationFrame(raf); };
  }, [avatar?.id]);

  const toggleMic = () => (recording ? stopRecording() : startRecording());

  return (
    <div className="rt-wrap">
      <div className="rt-top">
        <div className="rt-brand">
          <span className="rt-brand-ic"><I.layers size={15} /></span>
          <b>Avatar Studio</b>
          <span className="rt-brand-div" aria-hidden />
          <span className="rt-brand-page">{tr("app.live")}</span>
        </div>
        <div className="rt-top-r">
          <span className={"rt-pill rt-conn-pill" + (connected ? " on" : "")}>
            <span className="rt-pill-dot" />{connected ? tr("conn.connected") : tr("conn.connecting")}
          </span>
          {/* Suhbat tili: tanlansa Maftuna shu tilda + shu tilga tanlangan ovoz bilan
              gapiradi (WS qayta ulanadi). Interfeys tili ham shunga moslanadi. */}
          <label className="rt-pill rt-pill-sel" title="Suhbat tili / Language">
            <I.globe size={14} />
            <select value={effLang}
              onChange={(e) => { setConvLang(e.target.value); setTweak("uiLang", e.target.value); }}
              aria-label="Suhbat tili / Language">
              {LANGS.map((l) => (
                <option key={l.id} value={l.id}>{l.label}</option>
              ))}
            </select>
            <span className="rt-pill-chev" aria-hidden>▾</span>
          </label>
          {ready.length > 0 && avatar && (
            <label className="rt-pill rt-pill-sel" title="Avatar">
              <img className="rt-pill-ava" src={API.photoUrl(avatar.id)} alt="" />
              <select value={avatar.id} onChange={(e) => setAvatarId(e.target.value)}>
                {ready.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              <span className="rt-pill-chev" aria-hidden>▾</span>
            </label>
          )}
          {/* Avto-suhbat: yoqilsa qo'lsiz (Speak bosmasdan) uzluksiz gaplashadi. */}
          <button className={"rt-pill rt-avto" + (auto ? " on" : "")}
            onClick={toggleAuto} title="Avto-suhbat (qo'lsiz)">
            {auto ? "●" : "○"} Avto
          </button>
        </div>
      </div>

      {!avatar ? (
        <div className="rt-empty">
          <I.bolt size={28} />
          <div>{tr("rt.needReady")}</div>
          <div className="rt-empty-sub">{tr("rt.needReadySub")}</div>
        </div>
      ) : (
        <div className="rt-stage">
          <div className={"rt-avatar" + (busy ? " busy" : "") + (recording ? " listening" : "")}>
            {/* Orqa qatlam: o'sha rasmning xira versiyasi — video "contain" bo'lganda
                yon bo'shliqlarni to'ldiradi (yuz zoom bo'lmaydi, full-bleed saqlanadi). */}
            <div className="rt-avatar-bg" style={{ backgroundImage: `url(${API.photoUrl(avatar.id)})` }} aria-hidden />
            <img className="rt-media rt-base" src={API.photoUrl(avatar.id)} alt={avatar.name} />
            <video ref={idleRef} className="rt-media rt-idle" src={API.idleUrl(avatar.id)}
              loop muted autoPlay playsInline preload="auto" />
            {answerUrl && (
              <video ref={answerRef} key={answerUrl}
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
                  startStallWatch();   // muzlashni kuzatishni boshlaymiz
                }}
                onEnded={() => finishAnswer()}
                onError={() => finishAnswer()} />
            )}
            {(recording || busy) && (
              <div className={"rt-state " + (recording ? "listen" : "think")}>
                <span className="rt-state-ind" />
                {recording ? tr("rt.listeningShort") : tr("rt.thinkingShort")}
              </div>
            )}
            {/* Online belgisi (chap-tepa) — ulanish holati. */}
            <div className={"rt-online" + (connected ? " on" : "")}>
              <span className="rt-online-dot" />{connected ? "Online" : "Offline"}
            </div>
            {/* Brend kartasi (chap-past) — avatar nomi + roli + sifat belgilari. */}
            <div className="rt-badge">
              <div className="rt-badge-logo"><I.layers size={16} /></div>
              <div className="rt-badge-title">{avatar.name}</div>
              <div className="rt-badge-sub">{avatar.role}</div>
              <div className="rt-badge-chips">
                <span><I.check size={11} /> Ishonchli</span>
                <span><I.bolt size={11} /> Tezkor</span>
                <span><I.star size={11} /> Aniq</span>
              </div>
            </div>
            {busy && <div className="rt-progress"><div className="ed-progress-bar" /></div>}
          </div>

          <div className="rt-side">
            {turns.length === 0 ? (
              /* Xush kelibsiz paneli — suhbat boshlanmaguncha (mockup uslubi). */
              <div className="rt-welcome">
                <h1>Assalomu alaykum! <span className="rt-w-wave">👋</span></h1>
                <p className="rt-w-sub">
                  Men {avatar.name} — O'zbekiston Temir Yo'llari sun'iy intellekt yordamchisiman.<br />
                  Men sizga quyidagi yo'nalishlarda yordam bera olaman:
                </p>
                <div className="rt-cards">
                  {[
                    { ic: <I.grid size={17} />, cls: "c1", t: "Poyezdlar va chiptalar", s: "Yo'nalishlar, narxlar, jadval" },
                    { ic: <I.bolt size={17} />, cls: "c2", t: "Afrosiyob tezyurar", s: "Toshkent–Samarqand–Buxoro" },
                    { ic: <I.copy size={17} />, cls: "c3", t: "Hujjatlar", s: "Kerakli hujjatlar va ma'lumotlar" },
                    { ic: <I.clock size={17} />, cls: "c4", t: "Jadval va yo'nalishlar", s: "Jo'nash va yetib borish vaqtlari" },
                    { ic: <I.message size={17} />, cls: "c5", t: "Savollar", s: "Savollaringizga javob beraman" },
                  ].map((c) => (
                    <button key={c.t} className="rt-card"
                      onClick={() => { if (!busy && !recording) startRecording(); }}>
                      <span className={"rt-card-ic " + c.cls}>{c.ic}</span>
                      <span className="rt-card-tx"><b>{c.t}</b><small>{c.s}</small></span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="rt-log">
                {turns.map((t, i) => (
                  <div key={i} className={"rt-turn " + t.role + (t.streaming ? " streaming" : "")}>
                    <span className="rt-turn-who">{t.role === "user" ? tr("you") : avatar.name}</span>
                    <span className="rt-turn-text">{t.text}</span>
                  </div>
                ))}
              </div>
            )}

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

            {turns.length === 0 && !recording && !busy && (
              <div className="rt-hintbar">✦ Gapirishni boshlash uchun pastdagi tugmani bosing va gapiring.</div>
            )}

            <button className={"rt-cta" + (recording ? " rec" : "")} onClick={toggleMic}
              disabled={busy && !recording}>
              <span className="rt-cta-ic"><I.mic size={18} /></span>
              <span className="rt-cta-tx">
                <b>{recording ? "Tinglanmoqda… (to'xtatish)" : busy ? tr("rt.thinking") : "Gapirishni boshlash"}</b>
                <small>{recording ? "Gapirib bo'lgach o'zi to'xtaydi" : "Mikrofon tugmasini bosing va gapiring"}</small>
              </span>
              <canvas ref={waveCanvasRef} className="rt-cta-wave" aria-hidden />
            </button>
            <div className="rt-tip">Yandex streaming STT · {avatar.language?.toUpperCase()}</div>
          </div>
        </div>
      )}
    </div>
  );
}
