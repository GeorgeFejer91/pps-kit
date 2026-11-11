importScripts("./study-preview-cache.js");

const scope = new URL(self.registration.scope);
const { revision, files } = self.PPS_STUDY_PREVIEW_CACHE;
const prefix = `pps-study-preview:${scope.pathname}:`;
const cacheName = `${prefix}${revision}`;
const resources = new Set(files.map((file) => new URL(file, scope).href));

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(cacheName).then((cache) =>
    cache.addAll([...resources].map((url) => new Request(url, { cache: "reload" })))));
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names
      .filter((name) => name.startsWith(prefix) && name !== cacheName)
      .map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || request.headers.has("range")) return;
  const url = new URL(request.url);
  if (url.origin !== scope.origin) return;
  url.search = "";
  if (url.pathname.endsWith("/")) url.pathname += "index.html";
  if (!resources.has(url.href)) return;
  event.respondWith(caches.open(cacheName).then(async (cache) =>
    (await cache.match(url.href)) || fetch(request)));
});
