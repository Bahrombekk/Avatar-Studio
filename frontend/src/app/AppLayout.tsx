/* Admin chrome layout: Sidebar + asosiy maydon (Outlet) + Tweaks paneli. */
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "@/components/AdminShell";
import { StudioTweaks } from "./StudioTweaks";
import { useGo, pathToRoute } from "./navigation";
import { useTweaksCtx } from "@/context/TweaksContext";

export function AppLayout() {
  const { t } = useTweaksCtx();
  const go = useGo();
  const route = pathToRoute(useLocation().pathname);
  const flags = {
    conversations: t.secConversations,
    users: t.secUsers,
    settings: t.secSettings,
  };

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
