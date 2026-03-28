import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router", "zustand"],
          query: ["@tanstack/react-query", "dexie", "dexie-react-hooks"],
          markdown: [
            "react-markdown",
            "remark-gfm",
            "rehype-highlight",
            "highlight.js",
          ],
          ui: [
            "framer-motion",
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-scroll-area",
            "@radix-ui/react-tooltip",
            "@radix-ui/react-collapsible",
            "@radix-ui/react-separator",
            "@radix-ui/react-tabs",
          ],
          i18n: ["i18next", "react-i18next"],
          forms: ["react-hook-form"],
          charts: ["recharts"],
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8888",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
