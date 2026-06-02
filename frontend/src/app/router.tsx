/* Ilova router'i — base /studio (backend shu yo'lda xizmat qiladi).
   /preview admin chrome'siz; qolganlari AppLayout ichida. */
import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "./AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { EditorPage } from "@/pages/EditorPage";
import { ConversationsPage } from "@/pages/ConversationsPage";
import { UsersPage } from "@/pages/UsersPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { PreviewPage } from "@/pages/PreviewPage";

export const router = createBrowserRouter(
  [
    { path: "/preview", element: <PreviewPage /> },
    { path: "/preview/:id", element: <PreviewPage /> },
    {
      path: "/",
      element: <AppLayout />,
      children: [
        { index: true, element: <DashboardPage /> },
        { path: "analytics", element: <AnalyticsPage /> },
        { path: "editor/:id", element: <EditorPage /> },
        { path: "conversations", element: <ConversationsPage /> },
        { path: "users", element: <UsersPage /> },
        { path: "settings", element: <SettingsPage /> },
      ],
    },
  ],
  { basename: "/studio" },
);
