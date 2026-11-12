importScripts("./study-preview-cache.js");

const scope = new URL(self.registration.scope);
const { revision, files } = self.PPS_STUDY_PREVIEW_CACHE;
const prefix = `pps-study-preview:${scope.pathname}:`;
const cacheName = `${prefix}${revision}`;
const resources = new Set(files.map((file) => new URL(file, scope).href));
const shell = new URL("index.html", scope).href;
const appAssets = new URL("app/assets/", scope).pathname;

async function olderSnapshots() {
  return (await caches.keys()).filter((name) => name.startsWith(prefix) && name !== cacheName);
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(cacheName);
    await cache.addAll([...resources].map((url) => new Request(url, { cache: "reload" })));
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const snapshots = await olderSnapshots();
    const complete = await Promise.all(snapshots.map(async (name) =>
      (await caches.match(shell, { cacheName: name })) ? name : null));
    // A tab opened before activation may still request its old bundle.
    const previous = complete.filter(Boolean).at(-1);
    await Promise.all(snapshots.filter((name) => name !== previous).map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

async function serveResource(request, url, isAppAsset) {
  const cache = await caches.open(cacheName);
  if (request.mode === "navigate") {
    try {
      return await fetch(request, { cache: "no-cache" });
    } catch (error) {
      const offline = await cache.match(url);
      if (offline) return offline;
      throw error;
    }
  }

  const cached = await cache.match(url);
  if (cached) return cached;
  if (isAppAsset) {
    const [previous] = await olderSnapshots();
    const olderAsset = previous && await caches.match(url, { cacheName: previous });
    if (olderAsset) return olderAsset;
  }
  return fetch(request);
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || request.headers.has("range")) return;
  const url = new URL(request.url);
  if (url.origin !== scope.origin) return;
  url.search = "";
  if (url.pathname.endsWith("/")) url.pathname += "index.html";
  const isAppAsset = url.pathname.startsWith(appAssets);
  if (!resources.has(url.href) && !isAppAsset) return;
  event.respondWith(serveResource(request, url.href, isAppAsset));
});
