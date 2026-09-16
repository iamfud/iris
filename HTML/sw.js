const CACHE_NAME = 'iris-pwa-v138';
const ASSETS = [
  '/',
  '/index.html',
  '/style.css',
  '/script.js',
  '/settings_renderer.js',
  '/manifest.json',
  '/material-icons-outlined.woff2',
  '/mdi-webfont.ttf',
  '/Iris_full.png',
  '/icon-192.png',
  '/icon-512.png',
  '/icon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = event.request.url;
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
        return caches.match(event.request, { ignoreSearch: true }).then((fallback) => {
          if (fallback) return fallback;
          if (event.request.mode === 'navigate') {
            return caches.match('/index.html');
          }
        });
      })
  );
});
