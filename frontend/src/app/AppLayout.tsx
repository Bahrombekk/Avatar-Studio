/* Admin chrome layout: login bilan himoyalangan. Token bo'lmasa LoginPage,
   bo'lsa Sidebar + asosiy maydon (Outlet) + Tweaks paneli. */
import { Outlet, useLocation } from "react-router-dom";
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
  const route = pathToRoute(useLocation().pathname);
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
    <div className="app">
      <Sidebar route={route} go={go} flags={flags} />
      <div className="app-main">
        <Outlet />
      </div>
      <StudioTweaks />
    </div>
  );
}
