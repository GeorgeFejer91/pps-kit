import { resolve } from "node:path";
import { defineConfig } from "vite";

const frontendRoot = resolve(import.meta.dirname, "frontend");

export default defineConfig({
  root: frontendRoot,
  base: "./",
  clearScreen: false,
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true,
  },
  build: {
    outDir: resolve(import.meta.dirname, "compiled"),
    emptyOutDir: true,
    cssCodeSplit: false,
    sourcemap: false,
    target: "es2022",
    rollupOptions: {
      input: {
        desktop: resolve(frontendRoot, "index.html"),
        companion: resolve(frontendRoot, "companion/index.html"),
      },
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
});
