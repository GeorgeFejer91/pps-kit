import { defineConfig, normalizePath } from "vite";
import { cpSync, rmSync } from "node:fs";
import { resolve } from "node:path";

const iconDirectory = resolve(import.meta.dirname, "../../../packages/pps-resources/assets/app");
const devIcons = "/@fs/" + normalizePath(iconDirectory).replace(/^\/+/, "") + "/";

export default defineConfig({
  base: "./",
  server: {
    fs: {
      allow: [import.meta.dirname, iconDirectory],
    },
  },
  plugins: [{
    name: "pps-compiled-paths",
    transformIndexHtml: {
      order: "post",
      handler(html, { server }) {
        if (server) html = html.replaceAll("../../../packages/pps-resources/assets/app/", devIcons);
        return html
          .replaceAll('href="../../../', 'href="../../../../');
      },
    },
    closeBundle() {
      const destination = resolve("compiled/viewer");
      rmSync(destination, { recursive: true, force: true });
      cpSync(resolve("viewer"), destination, { recursive: true });
    },
  }],
  build: {
    outDir: "compiled",
    emptyOutDir: true,
    sourcemap: true,
    target: ["es2022", "chrome109", "firefox115"],
  },
});
