/* Ilova router'i (base /).
   /         → public real-time (user) — loginsiz, hammaga ochiq
   /admin/*  → admin panel — login bilan (AppLayout ichida gate) */
import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "./AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { EditorPage } from "@/pages/EditorPage";
import { ConversationsPage } from "@/pages/ConversationsPage";
import { UsersPage } from "@/pages/UsersPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { PreviewPage } from "@/pages/PreviewPage";
import { VideoStudioPage } from "@/pages/VideoStudioPage";
import { CannedPage } from "@/pages/CannedPage";
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
        { path: "editor/:id", element: <EditorPage /> },
        { path: "conversations", element: <ConversationsPage /> },
        { path: "users", element: <UsersPage /> },
        { path: "settings", element: <SettingsPage /> },
        { path: "preview", element: <PreviewPage /> },
        { path: "preview/:id", element: <PreviewPage /> },
      ],
    },
  ],
  { basename: "/" },
);
