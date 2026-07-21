import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Config de Vite con integracion de Vitest para tests unit de componentes.
//
// Para tests usamos jsdom (entorno navegador simulado) y los matchers
// custom de @testing-library/jest-dom.
//
// Comandos:
//   npm test           -> corre todos los tests en modo watch
//   npm run test:run   -> corre una vez sin watch
//   npm run test:ui    -> UI mode (opcional, requiere vitest ui)
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/__tests__/setup.js"],
    include: ["src/__tests__/**/*.test.{js,jsx}"],
  },
});
