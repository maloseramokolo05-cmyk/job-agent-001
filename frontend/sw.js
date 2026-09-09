const CACHE='tumelo-job-agent-pwa-v1';
const APP_SHELL=['/assets/index.html','/assets/style.css','/assets/app.js','/assets/manifest.webmanifest','/assets/icon-192.png','/assets/icon-512.png'];
self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(APP_SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));
});
self.addEventListener('fetch',event=>{
  const request=event.request;
  const url=new URL(request.url);
  if(request.method!=='GET'||url.origin!==location.origin) return;
  if(url.pathname.startsWith('/api/')) return;
  if(request.mode==='navigate'){
    event.respondWith(fetch(request).then(response=>{const copy=response.clone();caches.open(CACHE).then(cache=>cache.put('/assets/index.html',copy));return response;}).catch(()=>caches.match('/assets/index.html')));
    return;
  }
  if(url.pathname.startsWith('/assets/')){
    event.respondWith(caches.match(request).then(cached=>{
      const network=fetch(request).then(response=>{if(response.ok)caches.open(CACHE).then(cache=>cache.put(request,response.clone()));return response;}).catch(()=>cached);
      return cached||network;
    }));
  }
});
