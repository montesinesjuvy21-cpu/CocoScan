const CACHE_NAME = 'cocoscan-app-shell-v6';
const RUNTIME_CACHE = 'cocoscan-pages-runtime-v6';
const IMAGE_CACHE = 'cocoscan-report-images-v6';

// Only precache truly public, unauthenticated assets to prevent login redirect caching corruption
const PRECACHE_ASSETS = [
    '/login',
    '/manifest.json',
    '/offline',
    '/static/css/weather_widget.css',
    '/static/js/report_modal.js',
    '/static/icons/icon-192x192.png',
    '/static/icons/icon-512x512.png',
    '/static/icons/favicon.ico',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js'
];

// Install event: Precache core public app shell
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW v6] Precaching Public App Shell');
            return cache.addAll(PRECACHE_ASSETS).catch((err) => {
                console.warn('[SW v6] Precache assets load warning:', err);
            });
        }).then(() => self.skipWaiting())
    );
});

// Activate event: Clean up legacy caches (v1-v5)
self.addEventListener('activate', (event) => {
    const currentCaches = [CACHE_NAME, RUNTIME_CACHE, IMAGE_CACHE];
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (!currentCaches.includes(cacheName)) {
                        console.log('[SW v6] Deleting legacy cache:', cacheName);
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

// Fetch event: Implement advanced caching and auth-safe routing
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);

    // Ignore non-GET requests and unsupported protocols
    if (request.method !== 'GET' || !url.protocol.startsWith('http')) {
        return;
    }

    // 1. Report Photos & Media: Cache First, Network Fallback
    if (url.hostname.includes('supabase.co') || url.pathname.startsWith('/static/uploads/') || 
        request.destination === 'image' || /\.(png|jpg|jpeg|webp|gif|svg|ico)$/i.test(url.pathname)) {
        
        event.respondWith(
            caches.open(IMAGE_CACHE).then(async (cache) => {
                const cachedResponse = await cache.match(request);
                if (cachedResponse) {
                    return cachedResponse;
                }
                try {
                    const networkResponse = await fetch(request);
                    if (networkResponse && networkResponse.status === 200 && !networkResponse.redirected) {
                        cache.put(request, networkResponse.clone());
                    }
                    return networkResponse;
                } catch (error) {
                    return new Response('', { status: 204, statusText: 'No Content' });
                }
            })
        );
        return;
    }

    // 2. HTML Navigation & Dashboards
    if (request.mode === 'navigate') {
        const isFarmerRoute = url.pathname.startsWith('/farmer/scan') || url.pathname.startsWith('/farmer/drafts') || url.pathname.startsWith('/farmer/dashboard');
        const isNonFarmerAdminRoute = url.pathname.startsWith('/admin') || url.pathname.startsWith('/agriculturist') || 
                                     url.pathname.startsWith('/lgu') || url.pathname.startsWith('/overview') || 
                                     url.pathname.startsWith('/map') || url.pathname.startsWith('/analytics');

        event.respondWith(
            (async () => {
                const runtimeCache = await caches.open(RUNTIME_CACHE);
                const appShellCache = await caches.open(CACHE_NAME);

                try {
                    // Always try network first for live navigation
                    const networkResponse = await fetch(request);

                    // CRITICAL FIX FOR AUTH REDIRECT BUG:
                    // Only cache in runtime if it was NOT redirected (e.g. not a 302 redirect to /login)
                    if (networkResponse && networkResponse.status === 200 && !networkResponse.redirected) {
                        // Only cache farmer routes and login in runtime cache for offline resilience
                        if (isFarmerRoute || url.pathname === '/login' || url.pathname === '/') {
                            runtimeCache.put(request, networkResponse.clone());
                        }
                    }
                    return networkResponse;
                } catch (networkErr) {
                    console.warn('[SW v6] Navigation offline for:', url.pathname);

                    // If non-farmer admin route goes offline, ALWAYS return standard /offline screen (no offline actions)
                    if (isNonFarmerAdminRoute) {
                        const offlinePage = await appShellCache.match('/offline') || await caches.match('/offline');
                        if (offlinePage) return offlinePage;
                        return new Response("Can't load right now, you're offline.", { status: 503, headers: { 'Content-Type': 'text/plain' } });
                    }

                    // If farmer route, attempt to serve cached farmer shell
                    if (isFarmerRoute) {
                        const cachedFarmer = await runtimeCache.match(request) || 
                                             await runtimeCache.match('/farmer/scan') || 
                                             await runtimeCache.match('/farmer/drafts');
                        if (cachedFarmer) {
                            return cachedFarmer;
                        }
                    }

                    // For login or general navigation, try /login or /offline
                    const fallback = await appShellCache.match('/login') || 
                                     await appShellCache.match('/offline') ||
                                     await caches.match('/offline');
                    if (fallback) {
                        return fallback;
                    }

                    return new Response("Can't load right now, you're offline.", { status: 503, headers: { 'Content-Type': 'text/plain' } });
                }
            })()
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
                    if (networkResponse && networkResponse.status === 200 && !networkResponse.redirected) {
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

    // 4. API & JSON requests: Network First, Cache Fallback
    event.respondWith(
        fetch(request).then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200 && request.method === 'GET' && !networkResponse.redirected) {
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
                    message: "You are currently offline or the server is temporarily unreachable.",
                    error: "You are currently offline."
                }), {
                    status: 200,
                    headers: { 'Content-Type': 'application/json' }
                });
            }
            return new Response('Network error', { status: 503 });
        })
    );
});
