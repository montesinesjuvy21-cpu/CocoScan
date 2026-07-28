const CACHE_NAME = 'cocoscan-app-shell-v2';
const RUNTIME_CACHE = 'cocoscan-pages-runtime-v2';
const IMAGE_CACHE = 'cocoscan-report-images-v2';

const PRECACHE_ASSETS = [
    '/manifest.json',
    '/offline',
    '/static/css/weather_widget.css',
    '/static/js/report_modal.js',
    '/static/icons/icon-192x192.png',
    '/static/icons/icon-512x512.png',
    '/static/icons/favicon.ico',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'https://cdn.jsdelivr.net/npm/chart.js'
];

// Install event: Precache core app shell
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW] Precaching App Shell');
            return cache.addAll(PRECACHE_ASSETS).catch((err) => {
                console.warn('[SW] Some precache assets failed to load:', err);
            });
        }).then(() => self.skipWaiting())
    );
});

// Activate event: Clean up legacy caches
self.addEventListener('activate', (event) => {
    const currentCaches = [CACHE_NAME, RUNTIME_CACHE, IMAGE_CACHE];
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (!currentCaches.includes(cacheName)) {
                        console.log('[SW] Deleting legacy cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Helper: Send message to all client windows
function notifyClients(message) {
    self.clients.matchAll({ includeUncontrolled: true, type: 'window' }).then((clients) => {
        for (const client of clients) {
            client.postMessage(message);
        }
    });
}

// Fetch event: Implement advanced caching strategies
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Ignore non-GET requests and unsupported protocols
    if (request.method !== 'GET' || !url.protocol.startsWith('http')) {
        return;
    }

    // 1. Report Photos & Images: Cache First, Network Fallback
    if (url.hostname.includes('supabase.co') || url.pathname.startsWith('/static/uploads/') || 
        request.destination === 'image' || /\.(png|jpg|jpeg|webp|gif|svg|ico)$/i.test(url.pathname)) {
        
        event.respondWith(
            caches.open(IMAGE_CACHE).then(async (cache) => {
                const cachedResponse = await cache.match(request);
                if (cachedResponse) {
                    // Return cached image immediately for instant loading
                    return cachedResponse;
                }
                try {
                    const networkResponse = await fetch(request);
                    if (networkResponse && networkResponse.status === 200) {
                        cache.put(request, networkResponse.clone());
                    }
                    return networkResponse;
                } catch (error) {
                    console.warn('[SW] Image fetch offline fallback failed:', url.pathname);
                    // Return empty 204 or transparent gif if image offline and un-cached
                    return new Response('', { status: 204, statusText: 'No Content' });
                }
            })
        );
        return;
    }

    // 2. HTML Navigation & Report Dashboards: Stale-While-Revalidate (SWR)
    if (request.mode === 'navigate' || url.pathname.includes('/reports') || url.pathname.includes('/dashboard') || 
        url.pathname.includes('/scan') || url.pathname.includes('/drafts') || url.pathname.includes('/schedules') ||
        url.pathname.includes('/analytics') || url.pathname.includes('/map')) {

        event.respondWith(
            caches.open(RUNTIME_CACHE).then(async (cache) => {
                const cachedResponse = await cache.match(request);

                // Background network revalidation
                const networkFetchPromise = fetch(request).then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        cache.put(request, networkResponse.clone());
                        // If we served a cached response first, notify client that cache was refreshed
                        if (cachedResponse) {
                            notifyClients({ type: 'CACHE_UPDATED', url: request.url });
                        }
                    }
                    return networkResponse;
                }).catch((error) => {
                    console.warn('[SW] Network offline for navigation:', url.pathname);
                    return null;
                });

                // If in cache, return instantly (0ms latency!)
                if (cachedResponse) {
                    // Trigger network fetch in background without blocking
                    networkFetchPromise;
                    return cachedResponse;
                }

                // If not in cache, wait for network fetch
                const networkResponse = await networkFetchPromise;
                if (networkResponse) {
                    return networkResponse;
                }

                // If both cache and network fail, return the offline fallback portal
                if (request.mode === 'navigate') {
                    const offlineFallback = await caches.match('/offline');
                    if (offlineFallback) {
                        return offlineFallback;
                    }
                }

                return new Response('Offline: Resource unavailable', { status: 503, statusText: 'Service Unavailable' });
            })
        );
        return;
    }

    // 3. Static Assets (CSS, JS, Fonts): Cache First, Network Fallback
    if (request.destination === 'style' || request.destination === 'script' || request.destination === 'font' ||
        url.pathname.startsWith('/static/')) {
        
        event.respondWith(
            caches.match(request).then((cachedResponse) => {
                if (cachedResponse) {
                    return cachedResponse;
                }
                return fetch(request).then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const responseToCache = networkResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(request, responseToCache);
                        });
                    }
                    return networkResponse;
                }).catch(() => {
                    return new Response('', { status: 503, statusText: 'Service Unavailable' });
                });
            })
        );
        return;
    }

    // 4. Default / API requests: Network First, Cache Fallback
    event.respondWith(
        fetch(request).then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200 && request.method === 'GET') {
                const responseToCache = networkResponse.clone();
                caches.open(RUNTIME_CACHE).then((cache) => {
                    cache.put(request, responseToCache);
                });
            }
            return networkResponse;
        }).catch(async () => {
            const cachedResponse = await caches.match(request);
            if (cachedResponse) {
                return cachedResponse;
            }
            if (url.pathname.startsWith('/api/')) {
                return new Response(JSON.stringify({
                    success: false,
                    offline: true,
                    error: "You are currently offline. Working in local mode."
                }), {
                    status: 503,
                    headers: { 'Content-Type': 'application/json' }
                });
            }
            return new Response('Network error', { status: 503 });
        })
    );
});
