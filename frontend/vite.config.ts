import path from "node:path";
import babel from "@rolldown/plugin-babel";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    react({
      jsxImportSource: "@emotion/react",
    }),

    babel({
      plugins: ["@emotion/babel-plugin"],
      presets: [reactCompilerPreset()],
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:40001",
        changeOrigin: true,
      },
    },
  },
});
