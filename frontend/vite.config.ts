/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// Backend (FastAPI) endi ROOT '/' da xizmat qiladi → base '/'.
// '/' = public real-time (user), '/admin' = panel (login). Dev'da API 8100 ga proksi.
const BACKEND = "http://localhost:8100";
const proxy = Object.fromEntries(
  ["/api", "/chat", "/chat-stream", "/voices", "/idle.jpg", "/videos", "/health"].map(
    (p) => [p, { target: BACKEND, changeOrigin: true }],
  ),
);

// base: dev = "/" (localhost:8100/ ildizda). Spark deploy = "/avatar/" —
// nbt.railway.uz/avatar/ ostida chiqishi uchun `VITE_BASE=/avatar/ npm run build`.
// (Asset/index shu prefiks bilan; /api, /voices, WS absolyut qoladi — proksi ularni
//  backendga yo'naltirishi kerak.)
export default defineConfig({
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: { port: 5173, proxy },
  build: { outDir: "dist", emptyOutDir: true },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
