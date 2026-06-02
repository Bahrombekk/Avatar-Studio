/* Avatar Studio — Vite kirish nuqtasi (router + global kontekstlar). */
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { router } from "./app/router";
import { ToastProvider } from "./context/ToastContext";
import { TweaksProvider } from "./context/TweaksContext";
import { AvatarsProvider } from "./context/AvatarsContext";
import "./styles/styles.css";
import "./styles/admin.css";

const rootEl = document.getElementById("root");
if (rootEl) {
  ReactDOM.createRoot(rootEl).render(
    <React.StrictMode>
      <ToastProvider>
        <TweaksProvider>
          <AvatarsProvider>
            <RouterProvider router={router} />
          </AvatarsProvider>
        </TweaksProvider>
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
