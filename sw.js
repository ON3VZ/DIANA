/*
 * Diana — service worker.
 *
 * Regel: alles wat nagekeken en versiebeheerd is, komt cache-first; alles wat
 * vers moet zijn, komt network-first met een zichtbare terugval.
 *
 * Kaarttegels krijgen een eigen cache met een ruwe LRU-limiet, zodat een
 * gedownload gebied blijft staan maar de opslag niet ongelimiteerd groeit.
 */
const VERSION   = 'diana-v1';
const SHELL     = `${VERSION}-shell`;
const TILES     = `${VERSION}-tiles`;
const TILE_MAX  = 3000;               // ruwweg 60 MB aan vectortegels

// Zowel de gepubliceerde indeling (data naast index.html) als de repo-indeling
// (data een niveau hoger) staat erin. Wat niet bestaat, wordt overgeslagen:
// addAll() faalt in zijn geheel bij één 404, dus we cachen stuk voor stuk.
const SHELL_FILES = [
  './', './index.html', './manifest.webmanifest',
  './vendor/maplibre-gl.js', './vendor/maplibre-gl.css',
  './data/onff.geojson', './data/onff-index.json', './data/meta.json',
  '../data/onff.geojson', '../data/onff-index.json', '../data/meta.json',
];

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const cache = await caches.open(SHELL);
    await Promise.all(SHELL_FILES.map(u =>
      cache.add(u).catch(() => {})     // ontbrekende indeling: gewoon overslaan
    ));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => !k.startsWith(VERSION)).map(k => caches.delete(k)))
  ).then(()=>self.clients.claim()));
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return;

  // Live data: nooit uit de cache serveren zonder het te melden.
  if (url.hostname === 'spots.wwff.co' || url.hostname === 'docs.google.com') {
    event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
    return;
  }

  // Kaarttegels en lettertypen: cache-first met LRU.
  if (url.hostname === 'tiles.openfreemap.org') {
    event.respondWith(caches.open(TILES).then(async cache => {
      const hit = await cache.match(event.request);
      if (hit) return hit;
      const res = await fetch(event.request);
      if (res.ok) { cache.put(event.request, res.clone()); trim(cache); }
      return res;
    }));
    return;
  }

  // App-shell en data: cache-first, netwerk als aanvulling.
  event.respondWith(caches.match(event.request).then(hit =>
    hit || fetch(event.request).then(res => {
      if (res.ok && url.origin === location.origin) {
        const copy = res.clone();
        caches.open(SHELL).then(c => c.put(event.request, copy));
      }
      return res;
    })
  ));
});

async function trim(cache){
  const keys = await cache.keys();
  if (keys.length <= TILE_MAX) return;
  for (const k of keys.slice(0, keys.length - TILE_MAX)) await cache.delete(k);
}

/* "Gebied downloaden voor offline": de pagina stuurt een lijst tegel-URL's door. */
self.addEventListener('message', event => {
  if (event.data?.type !== 'PREFETCH_TILES') return;
  event.waitUntil(caches.open(TILES).then(async cache => {
    let done = 0;
    for (const u of event.data.urls) {
      try { const r = await fetch(u); if (r.ok) await cache.put(u, r); } catch {}
      done++;
      if (done % 25 === 0) broadcast({type:'PREFETCH_PROGRESS', done, total:event.data.urls.length});
    }
    broadcast({type:'PREFETCH_DONE', done});
  }));
});
async function broadcast(msg){
  (await self.clients.matchAll()).forEach(c => c.postMessage(msg));
}
