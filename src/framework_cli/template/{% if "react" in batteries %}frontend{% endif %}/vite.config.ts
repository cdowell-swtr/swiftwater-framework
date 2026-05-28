/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In the compose `frontend` service the backend is the in-network `app`; from a host-run
// `task fe:dev` it's the published localhost port (set via VITE_PROXY_TARGET).
const backend = process.env.VITE_PROXY_TARGET ?? "http://app:8000";
const apiPaths = ["/items", "/health", "/heartbeat", "/metrics", "/docs", "/openapi.json"];

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: Object.fromEntries(apiPaths.map((p) => [p, { target: backend, changeOrigin: true }])),
  },
  build: { outDir: "dist" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/setupTests.ts",
    coverage: { provider: "v8" },
  },
});
