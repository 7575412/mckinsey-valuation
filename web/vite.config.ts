import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /api → FastAPI backend on :8000
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
