// Cache-first app shell so the app opens offline after the first visit. API calls are never cached.
const CACHE = 'thirdeye-v1';
const SHELL = ['./', './index.html', './manifest.webmanifest', './css/app.css',
  './js/app.js', './js/bus.js', './js/util.js', './js/settings.js', './js/capture.js', './js/slides.js', './js/notes.js',
  './js/ai.js', './js/transcribe.js', './js/ocr.js', './js/assistant.js', './js/studysheet.js',
  './icons/icon-192.png', './icons/icon-512.png', './icons/apple-touch-icon.png'];

self.addEventListener('install', (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;
  e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request).then((r) => {
    if (r.ok && u.pathname.includes('/vendor/')) { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
    return r;
  })));
});
