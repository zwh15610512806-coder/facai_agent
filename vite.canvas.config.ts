import { resolve } from "node:path";

import { defineConfig } from "vite";

export default defineConfig({
  root: resolve(__dirname, "frontend/canvas"),
  publicDir: resolve(__dirname, "frontend/canvas/public"),
  build: {
    outDir: resolve(__dirname, "static/canvas"),
    emptyOutDir: true,
    lib: {
      entry: {
        canvas: resolve(__dirname, "frontend/canvas/src/main.ts"),
        "canvas-admin": resolve(__dirname, "frontend/canvas/src/admin.ts"),
      },
      formats: ["es"],
      fileName: (_format, entryName) => `${entryName}.js`,
      cssFileName: "canvas",
    },
    rollupOptions: {
      output: {
        assetFileNames: (asset) =>
          asset.name?.endsWith(".css") ? "canvas.css" : "[name][extname]",
      },
    },
  },
});
