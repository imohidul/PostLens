import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The built UI goes straight into the Python package so users never need Node.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // One bundle is fine for a desktop app that loads from 127.0.0.1, so raise
  // the size warning (meant for websites on slow networks).
  build: { outDir: "../postlens/static", emptyOutDir: true, chunkSizeWarningLimit: 1500 },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
