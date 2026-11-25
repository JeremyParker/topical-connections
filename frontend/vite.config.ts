import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  if (!loadEnv(mode, import.meta.dirname).VITE_TOPIC) {
    throw new Error("Set VITE_TOPIC to the slug of the topic this frontend is for");
  }
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: { "/api": "http://127.0.0.1:8000" },
    },
  };
});
