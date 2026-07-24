import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em dev, o Vite faz proxy de /api, /health e /metrics para o backend (8000),
// incluindo o upgrade de WebSocket — assim o front roda em same-origin e não
// depende de CORS localmente.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", ws: true, changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
      "/metrics": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
