import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "serve-root-favicons",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (
            req.url === "/favicon.ico" ||
            req.url === "/favicon.png" ||
            req.url === "/favicon-16x16.png" ||
            req.url === "/favicon-32x32.png" ||
            req.url === "/favicon-48x48.png" ||
            req.url === "/favicon-96x96.png" ||
            req.url === "/apple-touch-icon.png" ||
            req.url === "/site.webmanifest"
          ) {
            req.url = `/ui${req.url}`;
          }
          next();
        });
      },
    },
  ],
  base: "/ui/",
  build: {
    outDir: "../app/ui/static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/v1": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
    },
  },
});
