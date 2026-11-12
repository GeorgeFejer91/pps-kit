import { resolve } from "node:path";
import { defineConfig, normalizePath } from "vite";

const frontendRoot = resolve(import.meta.dirname, "frontend");
const iconDirectory = resolve(import.meta.dirname, "../../packages/pps-resources/assets/app");
const devIcons = "/@fs/" + normalizePath(iconDirectory).replace(/^\/+/, "") + "/";

export default defineConfig({
  root: frontendRoot,
  base: "./",
  clearScreen: false,
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true,
    fs: {
      allow: [import.meta.dirname, iconDirectory],
    },
  },
  plugins: [{
    name: "pps-runner-dev-icons",
    apply: "serve",
    transformIndexHtml(html) {
      return html.replace(/(?:\.\.\/)+packages\/pps-resources\/assets\/app\//gu, devIcons);
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
