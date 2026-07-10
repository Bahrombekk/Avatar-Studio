/* Ilova router'i (base /).
   /         → public real-time (user) — loginsiz, hammaga ochiq
   /admin/*  → admin panel — login bilan (AppLayout ichida gate) */
import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "./AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { EditorPage } from "@/pages/EditorPage";
import { ConversationsPage } from "@/pages/ConversationsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { PreviewPage } from "@/pages/PreviewPage";
import { VideoStudioPage } from "@/pages/VideoStudioPage";
import { CannedPage } from "@/pages/CannedPage";
import { KnowledgePage } from "@/pages/KnowledgePage";
import { RealtimePage } from "@/pages/RealtimePage";

export const router = createBrowserRouter(
  [
    // Public — foydalanuvchi real-time ovozli suhbat (loginsiz)
    { path: "/", element: <RealtimePage /> },

    // Admin panel — AppLayout login bilan himoyalaydi (gate ichida)
    {
      path: "/admin",
      element: <AppLayout />,
      children: [
        { index: true, element: <DashboardPage /> },
        { path: "analytics", element: <AnalyticsPage /> },
        { path: "studio", element: <VideoStudioPage /> },
        { path: "canned", element: <CannedPage /> },
        { path: "knowledge", element: <KnowledgePage /> },
        { path: "editor/:id", element: <EditorPage /> },
        { path: "conversations", element: <ConversationsPage /> },
        { path: "settings", element: <SettingsPage /> },
        { path: "preview", element: <PreviewPage /> },
        { path: "preview/:id", element: <PreviewPage /> },
      ],
    },
  ],
  // basename DINAMIK: joriy URL vite base ("/avatar") bilan boshlansa — o'sha,
  // aks holda "/". Shunda BITTA /avatar/ build uch xil kirishda ishlaydi:
  //   • proksi/subpath: nbt.railway.uz/avatar/  → pathname "/avatar/..." → basename "/avatar"
  //   • Spark to'g'ridan ROOT: 192.168.136.153:8100/ → pathname "/" → basename "/"
  //   • lokal dev (base "/"):  rawBase "" → basename "/"
  { basename: _routerBase() },
);

function _routerBase(): string {
  const raw = import.meta.env.BASE_URL.replace(/\/$/, "");   // "" yoki "/avatar"
  if (raw && window.location.pathname.startsWith(raw)) return raw;
  return "/";
}
