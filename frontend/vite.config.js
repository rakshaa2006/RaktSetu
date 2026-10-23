import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend only allows the origin http://localhost:5173 (and 127.0.0.1) by default,
// so the dev server keeps this port instead of silently choosing another.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
});
