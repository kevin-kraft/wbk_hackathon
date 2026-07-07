import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Relative base so the built app works no matter what path/host it's served from
// (root, a sub-path behind a reverse proxy, a file:// preview, etc.).
export default defineConfig({
  base: "./",
  plugins: [react(), tailwindcss()],
  server: { host: true, port: 5173 },
  preview: { host: true, port: 4173 },
});
