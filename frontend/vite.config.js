import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend (FastAPI) /studio ostida build natijasini xizmat qiladi → base '/studio/'.
// Dev rejimida (5173) API so'rovlari port 8100 ga proksilanadi.
const BACKEND = "http://localhost:8100";
const proxy = Object.fromEntries(
  ["/api", "/chat", "/chat-stream", "/voices", "/idle.jpg", "/videos", "/health"]
    .map((p) => [p, { target: BACKEND, changeOrigin: true }])
);

export default defineConfig({
  base: "/studio/",
  plugins: [react()],
  server: { port: 5173, proxy },
  build: { outDir: "dist", emptyOutDir: true },
});
