import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The built UI goes straight into the Python package so users never need Node.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: "../postlens/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
