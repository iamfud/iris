const CACHE_NAME = 'iris-pwa-v151';
const ASSETS = [
  '/',
  '/deck.html',
  '/deck.js',
  '/login.html',
  '/style.css',
  '/manifest.json',
  '/material-icons-outlined.woff2',
  '/mdi-webfont.ttf',
  '/Iris_full.png',
  '/icon-192.png',
  '/icon-512.png',
  '/icon.png',
  '/icon-180.png',
  '/apple-touch-icon.png',
  '/apple-touch-icon-precomposed.png',
  '/apple-touch-icon-152.png',
  '/apple-touch-icon-120.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return Promise.allSettled(
        ASSETS.map((asset) => cache.add(asset).catch(() => null))
      );
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((current) => current.match('/deck.html')).then((shell) => {
      if (!shell) return;
      return caches.keys().then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      ));
    }).then(() => self.clients.claim())
  );
});

function matchAnyCache(request) {
  return caches.keys().then((keys) => {
    const ordered = [CACHE_NAME].concat(keys.filter((key) => key !== CACHE_NAME));
    return ordered.reduce((promise, key) => promise.then((found) => {
      if (found) return found;
      return caches.open(key).then((cache) => cache.match(request, { ignoreSearch: true }));
    }), Promise.resolve(null));
  });
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = event.request.url;
  const path = new URL(url).pathname;
  if (/\.(png|ico)$/.test(path) || path.endsWith('/manifest.json')) {
    event.respondWith(
      matchAnyCache(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request, { cache: 'no-store' }).then((response) => {
          if (response && response.ok && url.startsWith(self.location.origin)) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone)).catch(() => {});
          }
          return response;
        });
      }).catch(() => new Response('', {
        status: 503,
        statusText: 'Service Unavailable',
        headers: { 'Content-Type': 'text/plain; charset=utf-8' }
      }))
    );
    return;
  }
  // Bypass service worker cache for dynamic APIs and live media streams
  if (url.includes('/api/') || url.includes('/media/') || url.includes('/pair')) {
    return;
  }

  // Network-first strategy for live updates with offline cache fallback
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.status === 200 && url.startsWith(self.location.origin)) {
          const resClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, resClone)).catch(() => {});
        }
        return response;
      })
      .catch(() => {
        return matchAnyCache(event.request).then((fallback) => {
          if (fallback) return fallback;
          if (event.request.mode === 'navigate') {
            return matchAnyCache('/deck.html').then((deck) => {
              return deck || new Response('Iris is offline', {
                status: 503,
                statusText: 'Service Unavailable',
                headers: { 'Content-Type': 'text/plain; charset=utf-8' }
              });
            });
          }
          return new Response('', { status: 503, statusText: 'Service Unavailable' });
        });
      })
  );
});
