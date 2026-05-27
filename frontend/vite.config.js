import { defineConfig } from "vite";

export default defineConfig({
  base: "/vorprojekt/",
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:5000",
      "/static": "http://127.0.0.1:5000",
    },
  },
});
