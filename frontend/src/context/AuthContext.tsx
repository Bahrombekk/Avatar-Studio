/* Admin autentifikatsiya konteksti — bitta parol (token localStorage'da).
   Public (user) qism buni ishlatmaydi; faqat /admin uchun. */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { API, clearToken, getToken } from "@/api/client";

interface AuthContextValue {
  authed: boolean;
  checking: boolean;
  login: (password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(false);
  const [checking, setChecking] = useState(true);

  // Yuklanganda mavjud tokenni tekshiramiz.
  useEffect(() => {
    let alive = true;
    (async () => {
      if (!getToken()) {
        if (alive) setChecking(false);
        return;
      }
      const ok = await API.checkAuth();
      if (alive) {
        setAuthed(ok);
        setChecking(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const login = useCallback(async (password: string) => {
    await API.login(password);
    setAuthed(true);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setAuthed(false);
  }, []);

  return (
    <AuthContext.Provider value={{ authed, checking, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth AuthProvider ichida ishlatilishi kerak");
  return ctx;
}
