/* Avatar Studio — Vite kirish nuqtasi. */
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./styles/styles.css";
import "./styles/admin.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Boot splash'ni olib tashlash.
const boot = document.getElementById("boot");
if (boot) {
  requestAnimationFrame(() => {
    boot.classList.add("gone");
    setTimeout(() => boot.remove(), 450);
  });
}
