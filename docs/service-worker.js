const CACHE = "pt-app-v4";
const CORE_ASSETS = ["./", "./index.html", "./manifest.json", "./pwa-icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(CORE_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Nettverk først for data.json / garmin_health.json (alltid fersk data når
// tilkoblet), cache som fallback offline. Cache-først for statiske filer.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isData = url.pathname.endsWith("data.json") || url.pathname.endsWith("garmin_health.json") || url.pathname.endsWith("activities.json");

  if (isData) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, clone));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
