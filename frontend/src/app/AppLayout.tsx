/* Admin chrome layout: login bilan himoyalangan. Token bo'lmasa LoginPage,
   bo'lsa Sidebar + asosiy maydon (Outlet) + Tweaks paneli.
   Mobil (≤860px): sidebar off-canvas drawer — burger tugma ochadi, backdrop yopadi. */
import { Outlet, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { Sidebar } from "@/components/AdminShell";
import { StudioTweaks } from "./StudioTweaks";
import { useGo, pathToRoute } from "./navigation";
import { useTweaksCtx } from "@/context/TweaksContext";
import { useAuth } from "@/context/AuthContext";
import { LoginPage } from "@/pages/LoginPage";

export function AppLayout() {
  const { authed, checking } = useAuth();
  const { t } = useTweaksCtx();
  const go = useGo();
  const location = useLocation();
  const route = pathToRoute(location.pathname);
  // Mobil navigatsiya drawer holati — sahifa almashganda avtomatik yopiladi.
  const [navOpen, setNavOpen] = useState(false);
  useEffect(() => { setNavOpen(false); }, [location.pathname]);
  const flags = {
    conversations: t.secConversations,
    users: t.secUsers,
    settings: t.secSettings,
  };

  if (checking) {
    return <div className="login-wrap"><div className="login-sub">Yuklanmoqda…</div></div>;
  }
  if (!authed) return <LoginPage />;

  return (
    <div className={"app" + (navOpen ? " nav-open" : "")}>
      {/* Burger — faqat mobil ekranda ko'rinadi (CSS bilan boshqariladi). */}
      <button className="app-burger" aria-label="Menyu" aria-expanded={navOpen}
        onClick={() => setNavOpen((v) => !v)}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round">
          {navOpen
            ? <><line x1="6" y1="6" x2="18" y2="18" /><line x1="6" y1="18" x2="18" y2="6" /></>
            : <><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" /></>}
        </svg>
      </button>
      <div className="app-nav-backdrop" onClick={() => setNavOpen(false)} aria-hidden />
      <Sidebar route={route} go={go} flags={flags} />
      <div className="app-main">
        <Outlet />
      </div>
      <StudioTweaks />
    </div>
  );
}
