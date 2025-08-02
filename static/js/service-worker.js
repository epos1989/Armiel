self.addEventListener('install', function(e) {
  e.waitUntil(caches.open('armiel-v1').then(function(cache){
    return cache.addAll(['/', '/manifest.json']);
  }));
});
self.addEventListener('fetch', function(e){
  e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));
});
