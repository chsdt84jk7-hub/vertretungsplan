// Service Worker: App offline startbar, Plan-Daten immer zuerst frisch aus dem Netz, Push-Nachrichten anzeigen.
const CACHE = 'vplan-v2';
const SHELL = ['./', 'index.html', 'manifest.webmanifest', 'icon.svg', 'icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;
  // Netzwerk zuerst, bei Funkloch die letzte Fassung aus dem Cache
  e.respondWith(
    fetch(e.request).then(r => {
      const copy = r.clone();
      caches.open(CACHE).then(c => c.put(e.request.url.split('?')[0], copy));
      return r;
    }).catch(() => caches.match(e.request.url.split('?')[0]))
  );
});

// Push vom GitHub-Workflow
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = { body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || 'Vertretungsplan', {
    body: d.body || 'Es gibt eine Änderung für dich.',
    icon: 'icon-192.png',
    badge: 'icon-192.png',
    data: { url: d.url || './' },
    tag: d.url || 'vplan',
    renotify: true,
  }));
});

// Tippen auf die Nachricht öffnet die App beim richtigen Tag
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const ziel = new URL(e.notification.data && e.notification.data.url || './', self.registration.scope).href;
  e.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
    for (const c of list) {
      if (c.url.startsWith(self.registration.scope) && 'navigate' in c) return c.navigate(ziel).then(w => w && w.focus());
    }
    return clients.openWindow(ziel);
  }));
});
