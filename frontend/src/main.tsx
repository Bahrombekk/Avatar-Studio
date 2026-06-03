/* Avatar Studio — Vite kirish nuqtasi (router + global kontekstlar). */
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { router } from "./app/router";
import { ToastProvider } from "./context/ToastContext";
import { TweaksProvider } from "./context/TweaksContext";
import { AvatarsProvider } from "./context/AvatarsContext";
import { AuthProvider } from "./context/AuthContext";
import "./styles/styles.css";
import "./styles/admin.css";

const rootEl = document.getElementById("root");
if (rootEl) {
  ReactDOM.createRoot(rootEl).render(
    <React.StrictMode>
      <ToastProvider>
        <AuthProvider>
          <TweaksProvider>
            <AvatarsProvider>
              <RouterProvider router={router} />
            </AvatarsProvider>
          </TweaksProvider>
        </AuthProvider>
      </ToastProvider>
    </React.StrictMode>,
  );
}

// Boot splash'ni olib tashlash.
const boot = document.getElementById("boot");
if (boot) {
  requestAnimationFrame(() => {
    boot.classList.add("gone");
    setTimeout(() => boot.remove(), 450);
  });
}
