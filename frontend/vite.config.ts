import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发态把 /api(含 WebSocket)代理到后端;构建产物输出到 dist/,由 FastAPI 托管。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true, ws: true },
    },
  },
  build: { outDir: "dist", chunkSizeWarningLimit: 1500 },
});
