/* Avatar Studio — Chat ekrani (foydalanuvchi tomoni, premium).
   Portret ustuni + suhbat oqimi. REAL pipeline: GPT → TTS → MuseTalk video
   /chat-stream (SSE) orqali. Avatar props'dan o'qiladi. */
import React, { useState, useRef, useEffect } from "react";
import { I } from "../lib/icons";
import { API } from "../api/client";
import { LANGUAGES } from "../data/constants";

export function ChatScreen({ avatar, embedded = false }) {
  const greeting = {
    role: "bot",
    text: `Assalomu alaykum. Men ${avatar.name} — ${avatar.brand} yordamchisi. Savolingizni yozing.`,
    time: "—",
  };
  const [thread, setThread] = useState(() => [greeting]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(null);   // 'gpt' | 'tts' | 'video' | null
  const [speaking, setSpeaking] = useState(false);
  const [videoUrl, setVideoUrl] = useState(null);
  const [timing, setTiming] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const threadRef = useRef(null);
  const timerRef = useRef(null);
  const videoRef = useRef(null);

  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [thread, stage]);

  useEffect(() => () => clearInterval(timerRef.current), []);

  const sugg = avatar.suggestions || [];

  function send(text) {
    const msg = (text ?? input).trim();
    if (!msg || busy) return;
    setInput("");
    setThread((t) => [...t, { role: "user", text: msg, time: now() }]);
    setBusy(true); setTiming(null); setSpeaking(false); setVideoUrl(null);
    setStage("gpt"); startTimer();

    API.chatStream(msg, avatar.id, avatar.voice, (type, ev) => {
      if (type === "text") {
        setThread((t) => [...t, { role: "bot", text: ev.text, time: now() }]);
        setStage("tts");
      } else if (type === "tts_done") {
        setStage("video");
      } else if (type === "video") {
        stopTimer();
        setStage(null);
        const tm = ev.timing || {};
        setTiming({
          gpt: (tm.gpt || 0).toFixed(1), tts: (tm.tts || 0).toFixed(1),
          video: (tm.wav2lip || 0).toFixed(1), total: (tm.total || 0).toFixed(1),
        });
        setBusy(false);
        if (avatar.real && ev.video) {
          setVideoUrl(ev.video);
          setSpeaking(true);
        } else {
          // Video yo'q avatar (preprocessing kerak) — faqat "gapirmoqda" animatsiyasi.
          setSpeaking(true);
          setTimeout(() => setSpeaking(false), 2600);
        }
      } else if (type === "error") {
        stopTimer(); setStage(null); setBusy(false);
        setThread((t) => [...t, { role: "bot", text: "Xatolik: " + (ev.message || "noma'lum"), time: now() }]);
      }
    }).catch((e) => {
      stopTimer(); setStage(null); setBusy(false);
      setThread((t) => [...t, { role: "bot", text: "Ulanish xatosi: " + e.message, time: now() }]);
    });
  }

  function startTimer() {
    setElapsed(0);
    const t0 = Date.now();
    clearInterval(timerRef.current);
    timerRef.current = setInterval(() => setElapsed(((Date.now() - t0) / 1000)), 100);
  }
  function stopTimer() { clearInterval(timerRef.current); }

  const stateLabel = busy ? (stage === "gpt" ? "O‘ylamoqda" : stage === "tts" ? "Ovoz" : "Video")
    : speaking ? "Gapirmoqda" : "Tayyor";
  const stateColor = busy ? "var(--warn)" : speaking ? "var(--brass)" : "var(--ok)";

  const showVideo = avatar.real && videoUrl && speaking;

  return (
    <div className="cs-root" style={{ borderRadius: embedded ? 0 : "var(--radius-lg)" }}>
      {/* ── LEFT: portrait ── */}
      <aside className="cs-left">
        <div className="cs-brand">
          <div className="cs-brand-mark" style={{ background: avatar.accent }}>
            {avatar.portrait.initials}
          </div>
          <div>
            <div className="cs-brand-name">{avatar.name}</div>
            <div className="cs-brand-sub">{avatar.role} · {avatar.brandShort}</div>
          </div>
        </div>

        <div className={"cs-portrait" + (speaking ? " speaking" : "")}>
          <div className="cs-portrait-img" style={{
            background: `linear-gradient(155deg, ${avatar.portrait.from}, ${avatar.portrait.to})`,
          }}>
            {avatar.real ? (
              showVideo ? (
                <video ref={videoRef} className="cs-real-media" src={videoUrl}
                  autoPlay playsInline onEnded={() => setSpeaking(false)} />
              ) : (
                <img className="cs-real-media" src={API.photoUrl(avatar.id)} alt={avatar.name} />
              )
            ) : (
              <span className="cs-portrait-initials">{avatar.portrait.initials}</span>
            )}
          </div>
          <div className="cs-frame" />

          {speaking && !showVideo && (
            <div className="cs-eq">
              {[0,1,2,3,4].map((i) => <span key={i} />)}
            </div>
          )}

          {busy && (
            <div className="cs-load">
              <div className="cs-spin-wrap">
                <div className="cs-spin" />
                <div className="cs-timer">{elapsed.toFixed(1)}s</div>
              </div>
              <div className="cs-load-steps">
                {[["gpt","Matn"],["tts","Ovoz"],["video","Video"]].map(([k,l]) => {
                  const order = ["gpt","tts","video"];
                  const cur = order.indexOf(stage), mine = order.indexOf(k);
                  const cls = mine < cur ? "done" : mine === cur ? "active" : "";
                  return <div key={k} className={"cs-step " + cls}>{l}</div>;
                })}
              </div>
            </div>
          )}

          <div className="cs-overlay">
            <div>
              <div className="cs-pname">{avatar.name}</div>
              <div className="cs-prole">{avatar.role}</div>
            </div>
            <div className="cs-pill">
              <span className="cs-pill-dot" style={{ background: stateColor }} />
              {stateLabel}
            </div>
          </div>
        </div>

        <div className="cs-meta">
          <div className="cs-meta-cell">
            <div className="as-label">Brend</div>
            <div className="cs-meta-val">{avatar.brand}</div>
          </div>
          <div className="cs-meta-cell">
            <div className="as-label">Til</div>
            <div className="cs-meta-val">{(LANGUAGES.find(l=>l.code===avatar.language)||{}).native}</div>
          </div>
        </div>

        {timing && (
          <div className="cs-timing">
            {[["GPT",timing.gpt],["Ovoz",timing.tts],["Video",timing.video],["Jami",timing.total]].map(([k,v]) => (
              <div key={k} className="cs-timing-cell">
                <div className="as-label" style={{ fontSize: 8 }}>{k}</div>
                <div className="cs-timing-val">{v}s</div>
              </div>
            ))}
          </div>
        )}
      </aside>

      {/* ── RIGHT: conversation ── */}
      <main className="cs-right">
        <div className="cs-top">
          <h2>Bugungi <em>suhbat</em></h2>
          <span className="cs-top-mono">Sessiya · {avatar.language.toUpperCase()}-{avatar.language.toUpperCase()}</span>
        </div>

        <div className="cs-thread as-scroll" ref={threadRef}>
          {thread.map((m, i) => (
            <div key={i} className={"cs-turn " + m.role}>
              <div className="cs-turn-meta">
                <div className="cs-turn-sender">{m.role === "user" ? "Mehmon" : avatar.name}</div>
                <div className="cs-turn-time">{m.time}</div>
              </div>
              <div className="cs-turn-body">{m.text}</div>
            </div>
          ))}
          {busy && stage === "gpt" && (
            <div className="cs-turn bot">
              <div className="cs-turn-meta">
                <div className="cs-turn-sender">{avatar.name}</div>
                <div className="cs-turn-time">{now()}</div>
              </div>
              <div className="cs-turn-body"><div className="cs-typing"><span/><span/><span/></div></div>
            </div>
          )}
        </div>

        {thread.length <= 1 && !busy && (
          <div className="cs-sugs">
            {sugg.map((s, i) => (
              <button key={i} className="cs-sug" onClick={() => send(s)}>
                <span className="cs-sug-num">{String(i+1).padStart(2,"0")}</span>{s}
              </button>
            ))}
          </div>
        )}

        <div className="cs-input-wrap">
          <div className="cs-input">
            <textarea rows={1} placeholder="Savolingizni yozing…" value={input}
              maxLength={500}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
            <button className="cs-send" disabled={busy || !input.trim()} onClick={() => send()}>
              Yuborish <I.send size={13} />
            </button>
          </div>
          <div className="cs-input-hint">
            <span><kbd>Enter</kbd> yuborish · <kbd>Shift</kbd>+<kbd>Enter</kbd> yangi qator</span>
            <span>{input.length} / 500</span>
          </div>
        </div>
      </main>
    </div>
  );
}

function now() {
  const d = new Date();
  return String(d.getHours()).padStart(2,"0") + ":" + String(d.getMinutes()).padStart(2,"0");
}
