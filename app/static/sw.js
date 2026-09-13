const C='odak-v4';
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(['/static/style.css','/static/app.js','/static/fox.svg','/static/scenery.svg','/static/icon.svg'])).then(()=>self.skipWaiting()));});
self.addEventListener('fetch',e=>{e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)));});
