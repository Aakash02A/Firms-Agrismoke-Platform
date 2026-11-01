/**
 * AgriSmoke AI - Service Worker
 * Enables offline execution for field monitoring officers in rural agricultural zones.
 * Employs a Network-First strategy for static assets (always fresh when online) and Network-First for API calls, both with cache fallback for offline field use.
 */

const CACHE_NAME = 'agrismoke-v3.0';
const STATIC_ASSETS = [
    'index.html',
    'css/styles.css',
    'js/app.js',
    'js/map-engine.js',
    'js/charts-engine.js',
    'js/prediction-model.js',
    'js/demo-data.js',
    'manifest.json'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        }).then(() => self.skipWaiting())
    );
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
    const url = new URL(event.request.url);

    // API calls: Network-First with Cache Fallback
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    if (response.status === 200) {
                        const copy = response.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                    }
                    return response;
                })
                .catch(() => caches.match(event.request))
        );
        return;
    }

    // Static Assets: Network-First (always fresh on localhost) with Cache Fallback (offline)
    event.respondWith(
        fetch(event.request).then((response) => {
            if (response && response.status === 200) {
                const copy = response.clone();
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
            }
            return response;
        }).catch(() => caches.match(event.request))
    );
});

