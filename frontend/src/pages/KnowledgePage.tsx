/* Bilim bazasi (RAG) — top-level admin sahifa.
   Manbalar (hujjatlar) + FAQ'lar, statistika, qidiruv.
   Satrni bosish → modal ochiladi: matnni KO'RISH va TAHRIRLASH; o'chirish shu yerda
   (tasdiqlash bilan) — satrda "x" YO'Q (adashib bosmaslik uchun).
   KB har avatarda alohida (API per-avatar), amalda birlashtirilgan. */
import { useEffect, useMemo, useRef, useState } from "react";
import { I } from "@/lib/icons";
import {
  API,
  type KnowledgeSource,
  type KnowledgeFaq,
  type FaqCandidate,
  type TranslateStatus,
} from "@/api/client";
import { Card, Btn } from "@/components/ui/index.jsx";
import { Topbar } from "@/components/AdminShell.jsx";
import { useAvatars } from "@/context/AvatarsContext";
import { useToast } from "@/context/ToastContext";

function fmt(n: number): string {
  return n.toLocaleString("ru");
}

type Editing =
  | { kind: "source"; id: string }
  | { kind: "faq"; id: string }
  | null;

export function KnowledgePage() {
  const { avatars } = useAvatars();
  const { toast } = useToast();
  const [avatarId, setAvatarId] = useState("");
  const selected = useMemo(
    () => avatars.find((a) => a.id === avatarId) || avatars[0],
    [avatars, avatarId],
  );

  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [faqs, setFaqs] = useState<KnowledgeFaq[]>([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState(""); // qidiruv

  // Yangi FAQ / hujjat yuklash
  const [nq, setNq] = useState("");
  const [na, setNa] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // Tahrirlash modali
  const [editing, setEditing] = useState<Editing>(null);

  const reload = () => {
    const id = selected?.id;
    if (!id) return;
    setLoading(true);
    API.knowledgeList(id)
      .then((d) => {
        setSources(d.sources || []);
        setFaqs(d.faqs || []);
      })
      .catch(() => toast("Bilim bazasi yuklanmadi", "error"))
      .finally(() => setLoading(false));
  };
  useEffect(reload, [selected?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const totals = useMemo(
    () => ({
      sources: sources.length,
      faqs: faqs.length,
      chunks: sources.reduce((s, x) => s + (x.n_chunks || 0), 0),
      chars: sources.reduce((s, x) => s + (x.chars || 0), 0),
    }),
    [sources, faqs],
  );

  const ql = q.trim().toLowerCase();
  const fSources = ql
    ? sources.filter((s) => s.name.toLowerCase().includes(ql))
    : sources;
  const fFaqs = ql
    ? faqs.filter((f) => (f.q + " " + f.a).toLowerCase().includes(ql))
    : faqs;

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    const id = selected?.id;
    if (!f || !id) return;
    setBusy(true);
    try {
      await API.knowledgeUpload(id, f);
      toast("Hujjat yuklandi", "success");
      reload();
    } catch (ex) {
      toast("Yuklanmadi: " + (ex as Error).message, "error");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const addFaq = async () => {
    const id = selected?.id;
    if (!id || !nq.trim() || !na.trim()) return;
    setBusy(true);
    try {
      await API.knowledgeAddFaq(id, nq.trim(), na.trim());
      setNq("");
      setNa("");
      toast("FAQ qo'shildi", "success");
      reload();
    } catch (ex) {
      toast("Qo'shilmadi: " + (ex as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const STATS = [
    { k: "Manbalar", v: fmt(totals.sources), ic: "copy" as const },
    { k: "FAQ", v: fmt(totals.faqs), ic: "message" as const },
    { k: "Bo'laklar", v: fmt(totals.chunks), ic: "layers" as const },
    { k: "Belgilar", v: fmt(totals.chars), ic: "grid" as const },
  ];

  return (
    <div className="pg as-scroll">
      <Topbar
        title="Bilim bazasi"
        sub={`RAG · ${fmt(totals.sources)} manba · ${fmt(totals.faqs)} FAQ · ${fmt(totals.chunks)} bo'lak`}
        actions={
          avatars.length > 0 && selected ? (
            <label className="kb-ava-sel" title="Avatar">
              <img src={API.photoUrl(selected.id)} alt="" />
              <select
                value={selected.id}
                onChange={(e) => setAvatarId(e.target.value)}
              >
                {avatars.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
              <span className="kb-ava-chev" aria-hidden>▾</span>
            </label>
          ) : null
        }
      />

      <div className="pg-body">
        <div className="kb-note">
          <I.bolt size={15} />
          Barcha avatarlar bir xil bilim bazasiga tayanadi — bu yerdagi o'zgarish
          tanlangan avatarga tegishli. Manba yoki FAQ ustiga bosib ichidagi matnni
          ko'ring va tahrirlang.
        </div>

        <div className="kb-stats">
          {STATS.map((s) => {
            const Ico = I[s.ic];
            return (
              <Card key={s.k} className="kb-stat" style={undefined}>
                <div className="kb-stat-ic">
                  <Ico size={16} />
                </div>
                <div className="kb-stat-v">{s.v}</div>
                <div className="as-label">{s.k}</div>
              </Card>
            );
          })}
        </div>

        <div className="kb-toolbar">
          <div className="dash-search">
            <I.search size={15} />
            <input
              placeholder="Manba yoki FAQ ichidan qidirish…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          {loading && <span className="kb-loading">Yuklanmoqda…</span>}
          <div className="kb-toolbar-sp" />
          {selected && <TranslateControl avatarId={selected.id} />}
        </div>

        <div className="kb-grid">
          {/* ── Manbalar (hujjatlar) ── */}
          <Card className="kb-panel" style={undefined}>
            <div className="kb-panel-head">
              <div className="kb-panel-title">
                <I.copy size={16} /> Manbalar
              </div>
              <span className="kb-panel-count">
                {fSources.length} / {totals.sources}
              </span>
            </div>
            <div className="kb-list">
              {fSources.map((s) => (
                <button
                  className="kb-row"
                  key={s.id}
                  onClick={() => setEditing({ kind: "source", id: s.id })}
                >
                  <span className="kb-src-type">{s.type || "txt"}</span>
                  <div className="kb-src-main">
                    <div className="kb-src-name">{s.name}</div>
                    <div className="kb-src-meta">
                      {fmt(s.n_chunks || 0)} bo'lak · {fmt(s.chars || 0)} belgi
                      {s.added ? " · " + s.added : ""}
                    </div>
                  </div>
                  <I.chevron size={16} />
                </button>
              ))}
              {!fSources.length && (
                <div className="kb-empty">
                  {ql ? "Mos manba topilmadi" : "Hujjat yo'q"}
                </div>
              )}
            </div>
            <div className="kb-add">
              <input
                ref={fileRef}
                type="file"
                accept=".txt,.md,.markdown"
                onChange={onFile}
                disabled={busy || !selected}
                hidden
              />
              <Btn
                kind="ghost"
                icon="plus"
                onClick={() => fileRef.current?.click()}
                disabled={busy || !selected}
              >
                Hujjat yuklash (.txt / .md)
              </Btn>
            </div>
          </Card>

          {/* ── FAQ (savol–javob) ── */}
          <Card className="kb-panel" style={undefined}>
            <div className="kb-panel-head">
              <div className="kb-panel-title">
                <I.message size={16} /> FAQ
              </div>
              <span className="kb-panel-count">
                {fFaqs.length} / {totals.faqs}
              </span>
            </div>
            <div className="kb-list">
              {fFaqs.map((f) => (
                <button
                  className="kb-row kb-row-faq"
                  key={f.id}
                  onClick={() => setEditing({ kind: "faq", id: f.id })}
                >
                  <div className="kb-src-main">
                    <div className="kb-faq-q">{f.q}</div>
                    <div className="kb-faq-a">{f.a}</div>
                  </div>
                  <I.chevron size={16} />
                </button>
              ))}
              {!fFaqs.length && (
                <div className="kb-empty">
                  {ql ? "Mos FAQ topilmadi" : "FAQ yo'q"}
                </div>
              )}
            </div>
            <div className="kb-add">
              <input
                className="as-field"
                value={nq}
                placeholder="Savol…"
                onChange={(e) => setNq(e.target.value)}
                disabled={!selected}
              />
              <textarea
                className="as-field"
                value={na}
                placeholder="Javob…"
                rows={2}
                onChange={(e) => setNa(e.target.value)}
                disabled={!selected}
              />
              <Btn
                kind="ghost"
                icon="plus"
                onClick={addFaq}
                disabled={busy || !nq.trim() || !na.trim()}
              >
                FAQ qo'shish
              </Btn>
            </div>
          </Card>
        </div>
      </div>

      {editing && selected && editing.kind === "source" && (
        <SourceModal
          avatarId={selected.id}
          srcId={editing.id}
          onClose={() => setEditing(null)}
          onReload={reload}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
      {editing && selected && editing.kind === "faq" && (
        <FaqModal
          avatarId={selected.id}
          faq={faqs.find((f) => f.id === editing.id)}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

/* ── RU/EN tarjima boshqaruvi (fon-job + progress) ── */
function TranslateControl({ avatarId }: { avatarId: string }) {
  const { toast } = useToast();
  const [st, setSt] = useState<TranslateStatus>({ state: "idle" });
  const timer = useRef<number | null>(null);

  const stop = () => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  };

  const poll = () => {
    API.knowledgeTranslateStatus(avatarId)
      .then((s) => {
        setSt(s);
        if (s.state === "running") {
          timer.current = window.setTimeout(poll, 1500);
        } else if (s.state === "done") {
          toast("Tarjima tugadi — RU/EN qo'shildi", "success");
        } else if (s.state === "error") {
          toast("Tarjima xatosi: " + (s.error || ""), "error");
        }
      })
      .catch(() => {});
  };

  // Avatar o'zgarganda holatni tekshir — ishlab turgan job bo'lsa progressni davom ettir.
  useEffect(() => {
    stop();
    setSt({ state: "idle" });
    API.knowledgeTranslateStatus(avatarId)
      .then((s) => {
        setSt(s);
        if (s.state === "running") poll();
      })
      .catch(() => {});
    return stop;
  }, [avatarId]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    try {
      const s = await API.knowledgeTranslate(avatarId, ["ru", "en"]);
      setSt(s);
      stop();
      poll();
    } catch (ex) {
      toast((ex as Error).message, "error");
    }
  };

  const running = st.state === "running";
  const pct = running && st.total ? Math.round(((st.done || 0) / st.total) * 100) : 0;

  return (
    <div className="kb-tr" title="Bilim bazasini rus va ingliz tiliga aynan tarjima qilib qo'shadi (ko'p tilli javob)">
      <Btn kind="ghost" icon="globe" onClick={start} disabled={running}>
        {running ? `Tarjima qilinmoqda… ${pct}%` : "RU / EN ga tarjima"}
      </Btn>
      {running && (
        <div className="kb-tr-bar" aria-hidden>
          <span style={{ width: pct + "%" }} />
        </div>
      )}
    </div>
  );
}

/* ── Manba modali: matnni ko'rish/tahrirlash + o'chirish ── */
function SourceModal({
  avatarId,
  srcId,
  onClose,
  onSaved,
  onReload,
}: {
  avatarId: string;
  srcId: string;
  onClose: () => void;
  onSaved: () => void;
  onReload: () => void;
}) {
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);

  // Avto-FAQ (GPT bu manbadan savol-javob taklif qiladi → admin tanlab qo'shadi).
  const [cands, setCands] = useState<FaqCandidate[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [genBusy, setGenBusy] = useState(false);
  const [addBusy, setAddBusy] = useState(false);

  const genFaqs = async () => {
    setGenBusy(true);
    try {
      const c = await API.knowledgeSuggestFaqs(avatarId, srcId, 8);
      setCands(c);
      setSel(new Set(c.map((_, i) => i))); // barchasi tanlangan holda
      if (!c.length) toast("Yangi FAQ topilmadi (barchasi mavjud bo'lishi mumkin)", "info");
    } catch (ex) {
      toast("FAQ yaratilmadi: " + (ex as Error).message, "error");
    } finally {
      setGenBusy(false);
    }
  };

  const toggle = (i: number) =>
    setSel((s) => {
      const n = new Set(s);
      n.has(i) ? n.delete(i) : n.add(i);
      return n;
    });

  const addSelected = async () => {
    if (!cands) return;
    const picked = cands.filter((_, i) => sel.has(i));
    if (!picked.length) return;
    setAddBusy(true);
    try {
      const r = await API.knowledgeAddFaqBulk(avatarId, picked);
      toast(`${r.added} ta FAQ qo'shildi`, "success");
      setCands(null);
      setSel(new Set());
      onReload();
    } catch (ex) {
      toast("Qo'shilmadi: " + (ex as Error).message, "error");
    } finally {
      setAddBusy(false);
    }
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    API.knowledgeGetSource(avatarId, srcId)
      .then((d) => {
        if (!alive) return;
        setName(d.name || "");
        setText(d.text || "");
      })
      .catch(() => toast("Manba yuklanmadi", "error"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [avatarId, srcId]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await API.knowledgeUpdateSource(avatarId, srcId, text, name.trim());
      toast("Manba saqlandi (qayta indekslandi)", "success");
      onSaved();
    } catch (ex) {
      toast("Saqlanmadi: " + (ex as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const del = async () => {
    setBusy(true);
    try {
      await API.knowledgeDeleteSource(avatarId, srcId);
      toast("Manba o'chirildi", "success");
      onSaved();
    } catch {
      toast("O'chirilmadi", "error");
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Manbani tahrirlash"
      onClose={onClose}
      busy={busy}
      confirmDel={confirmDel}
      setConfirmDel={setConfirmDel}
      onDelete={del}
      onSave={save}
      canSave={!loading && !!text.trim()}
    >
      {loading ? (
        <div className="kb-modal-loading">Yuklanmoqda…</div>
      ) : (
        <>
          <label className="kb-modal-lbl">Nom</label>
          <input
            className="as-field"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
          />
          <label className="kb-modal-lbl">
            Matn <span>({text.length.toLocaleString("ru")} belgi)</span>
          </label>
          <textarea
            className="as-field kb-modal-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={busy}
          />
          <p className="kb-modal-hint">
            Saqlaganda matn qayta bo'laklarga bo'linadi va embedding qayta hisoblanadi.
          </p>

          {/* ── Avto-FAQ (GPT bu manbadan savol-javob chiqaradi) ── */}
          <div className="kb-gen">
            <div className="kb-gen-head">
              <div className="kb-gen-title">
                <I.spark size={15} /> GPT bilan FAQ yaratish
              </div>
              <Btn
                kind="ghost"
                icon="spark"
                onClick={genFaqs}
                disabled={busy || genBusy || addBusy}
              >
                {genBusy ? "O'ylanmoqda…" : cands ? "Qayta yaratish" : "Yaratish"}
              </Btn>
            </div>
            <p className="kb-modal-hint">
              GPT shu manba matnini o'qib, faqat undagi faktlar asosida savol-javoblar
              taklif qiladi. Kerakligini belgilab, bilim bazasiga qo'shing.
            </p>

            {cands && cands.length > 0 && (
              <>
                <div className="kb-cand-list">
                  {cands.map((c, i) => (
                    <label className="kb-cand" key={i}>
                      <input
                        type="checkbox"
                        checked={sel.has(i)}
                        onChange={() => toggle(i)}
                      />
                      <div className="kb-cand-main">
                        <div className="kb-cand-q">{c.q}</div>
                        <div className="kb-cand-a">{c.a}</div>
                      </div>
                    </label>
                  ))}
                </div>
                <Btn
                  kind="primary"
                  icon="plus"
                  onClick={addSelected}
                  disabled={addBusy || sel.size === 0}
                >
                  {addBusy
                    ? "Qo'shilmoqda…"
                    : `Tanlanganlarni qo'shish (${sel.size})`}
                </Btn>
              </>
            )}
          </div>
        </>
      )}
    </Modal>
  );
}

/* ── FAQ modali: savol/javobni tahrirlash + o'chirish ── */
function FaqModal({
  avatarId,
  faq,
  onClose,
  onSaved,
}: {
  avatarId: string;
  faq: KnowledgeFaq | undefined;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { toast } = useToast();
  const [q, setQ] = useState(faq?.q || "");
  const [a, setA] = useState(faq?.a || "");
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);

  if (!faq) return null;

  const save = async () => {
    if (!q.trim() || !a.trim()) return;
    setBusy(true);
    try {
      await API.knowledgeUpdateFaq(avatarId, faq.id, q.trim(), a.trim());
      toast("FAQ saqlandi", "success");
      onSaved();
    } catch (ex) {
      toast("Saqlanmadi: " + (ex as Error).message, "error");
    } finally {
      setBusy(false);
    }
  };

  const del = async () => {
    setBusy(true);
    try {
      await API.knowledgeDeleteFaq(avatarId, faq.id);
      toast("FAQ o'chirildi", "success");
      onSaved();
    } catch {
      toast("O'chirilmadi", "error");
      setBusy(false);
    }
  };

  return (
    <Modal
      title="FAQ tahrirlash"
      onClose={onClose}
      busy={busy}
      confirmDel={confirmDel}
      setConfirmDel={setConfirmDel}
      onDelete={del}
      onSave={save}
      canSave={!!q.trim() && !!a.trim()}
    >
      <label className="kb-modal-lbl">Savol</label>
      <input
        className="as-field"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        disabled={busy}
      />
      <label className="kb-modal-lbl">Javob</label>
      <textarea
        className="as-field kb-modal-text"
        value={a}
        onChange={(e) => setA(e.target.value)}
        disabled={busy}
      />
    </Modal>
  );
}

/* ── Umumiy modal qobig'i (backdrop + footer) ── */
function Modal({
  title,
  children,
  onClose,
  busy,
  confirmDel,
  setConfirmDel,
  onDelete,
  onSave,
  canSave,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  busy: boolean;
  confirmDel: boolean;
  setConfirmDel: (v: boolean) => void;
  onDelete: () => void;
  onSave: () => void;
  canSave: boolean;
}) {
  return (
    <div className="kb-modal-back" onClick={busy ? undefined : onClose}>
      <div className="kb-modal" onClick={(e) => e.stopPropagation()}>
        <div className="kb-modal-head">
          <b>{title}</b>
          <button className="kb-modal-x" onClick={onClose} disabled={busy}>
            <I.x size={16} />
          </button>
        </div>
        <div className="kb-modal-body">{children}</div>
        <div className="kb-modal-foot">
          <button
            className={"kb-del" + (confirmDel ? " on" : "")}
            onClick={() => (confirmDel ? onDelete() : setConfirmDel(true))}
            disabled={busy}
          >
            <I.x size={14} />
            {confirmDel ? "Tasdiqlang — o'chirish" : "O'chirish"}
          </button>
          <div className="kb-modal-foot-r">
            <Btn kind="ghost" icon={undefined} onClick={onClose} disabled={busy}>
              Bekor
            </Btn>
            <Btn kind="primary" icon="check" onClick={onSave} disabled={busy || !canSave}>
              {busy ? "Saqlanmoqda…" : "Saqlash"}
            </Btn>
          </div>
        </div>
      </div>
    </div>
  );
}
