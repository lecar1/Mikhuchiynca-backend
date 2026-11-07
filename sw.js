const CACHE_NAME = 'mikhuchiynca-v2';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/style.css',
  '/app.js?v=100002',
  '/preferences.js?v=1',
  '/export.js?v=1'
];

// Instalación: Precaché de activos estáticos
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[Service Worker] Precargando caché estático');
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activación: Limpieza de cachés anteriores
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[Service Worker] Eliminando caché antiguo:', key);
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Intercepción de peticiones (Fetch)
self.addEventListener('fetch', (event) => {
  // Ignorar peticiones que no sean GET (como POST a /generar-plan o /api/...)
  if (event.request.method !== 'GET') {
    return;
  }

  // Las rutas de API siempre deben ir a la red
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/') || url.pathname === '/chat' || url.pathname === '/generar-plan' || url.pathname === '/generar-plan-familiar') {
    return;
  }

  // Estrategia Cache First con Network Fallback para estáticos
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).catch(() => {
        // Fallback a index.html para navegaciones si offline
        if (event.request.mode === 'navigate') {
          return caches.match('/');
        }
      });
    })
  );
});
