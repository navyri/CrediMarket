import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Puerto fijo 5173: es el origen permitido por CORS en los 4 servicios
// (ajustes.cors_origins, configurable por variable de entorno).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  preview: { port: 5173 },
});
