import { defineConfig } from "vite";
import { cpSync, rmSync } from "node:fs";
import { resolve } from "node:path";

export default defineConfig({
  base: "./",
  plugins: [{
    name: "pps-compiled-paths",
    transformIndexHtml: {
      order: "post",
      handler(html) {
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
