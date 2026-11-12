import { resolve } from "node:path";
import { defineConfig, normalizePath } from "vite";

const frontendRoot = resolve(import.meta.dirname, "frontend");
const iconDirectory = resolve(import.meta.dirname, "../../packages/pps-resources/assets/app");
const creditDirectory = resolve(import.meta.dirname, "../designer/frontend");
const creditFiles = ["george-fejer.webp", "bial-foundation.svg"].map((name) => resolve(creditDirectory, name));
const devAssetPath = (directory) => "/@fs/" + normalizePath(directory).replace(/^\/+/, "") + "/";

export default defineConfig({
  root: frontendRoot,
  base: "./",
  clearScreen: false,
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true,
    fs: {
      allow: [import.meta.dirname, iconDirectory, ...creditFiles],
    },
  },
  plugins: [{
    name: "pps-runner-dev-assets",
    apply: "serve",
    transformIndexHtml(html) {
      return html
        .replace(/(?:\.\.\/)+packages\/pps-resources\/assets\/app\//gu, devAssetPath(iconDirectory))
        .replaceAll("../../../designer/frontend/", devAssetPath(creditDirectory));
    },
  }],
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
