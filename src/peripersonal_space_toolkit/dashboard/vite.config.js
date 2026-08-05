import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  plugins: [{
    name: "pps-compiled-paths",
    transformIndexHtml: {
      order: "post",
      handler(html) {
        return html
          .replaceAll('href="../../../', 'href="../../../../')
          .replaceAll('src="../viewer/', 'src="../../viewer/')
          .replaceAll('data-lazy-src="../viewer/', 'data-lazy-src="../../viewer/');
      },
    },
  }],
  build: {
    outDir: "compiled",
    emptyOutDir: true,
    sourcemap: true,
    target: ["es2022", "chrome109", "firefox115"],
  },
});
