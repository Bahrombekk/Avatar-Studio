/* Admin login sahifasi — bitta parol. To'g'ri bo'lsa panel ochiladi. */
import { useState } from "react";
import { I } from "@/lib/icons";
import { useAuth } from "@/context/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(password);
    } catch (err) {
      setError((err as Error).message || "Kirish xatosi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="login-logo"><I.layers size={26} /></div>
        <div className="login-title">Avatar Studio</div>
        <div className="login-sub">Admin panel — kirish uchun parolni kiriting</div>
        <input
          className="as-field login-input"
          type="password"
          placeholder="Parol"
          value={password}
          autoFocus
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <div className="login-err"><I.x size={13} /> {error}</div>}
        <button className="login-btn" type="submit" disabled={busy || !password}>
          {busy ? "Tekshirilmoqda…" : "Kirish"}
        </button>
        <a className="login-back" href="/">← Foydalanuvchi sahifasiga</a>
      </form>
    </div>
  );
}
