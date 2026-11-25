import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // Keeps the browser's Host header, because the API uses it to pick a topic.
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
});
