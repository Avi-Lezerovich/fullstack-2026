/* LolSuit study guide — service worker, so the guide keeps working with no internet.
   Template: tools/build.py fills in VERSION and PRECACHE and writes /sw.js.

   - Everything the page needs is cached on install: the page, every css/js file
     (their URLs carry a content hash, so a cached copy is never stale), the code
     snapshot, and highlight.js from the CDN.
   - The page itself is network-first with a short timeout: online you get the
     latest build, offline (or on a crawling network) the cached copy.
   - Fonts are cached the first time they load (their file URLs are not known
     in advance). */
const VERSION = "876b6cb8eefc";
const PRECACHE = [
  "index.html",
  "manifest.webmanifest",
  "assets/css/base.css?v=2a089f171e",
  "assets/css/components.css?v=4cb7c04ca6",
  "assets/css/tools.css?v=3639c4a1db",
  "assets/data/code-index.js?v=6d5cd3087c",
  "assets/data/seq-data.js?v=440b262b23",
  "assets/img/lolsuit-seal.svg?v=91116f206f",
  "assets/js/code-viewer.js?v=25b85199d0",
  "assets/js/core.js?v=fbbd8be7c5",
  "assets/js/diagrams.js?v=3c99f4aa60",
  "assets/js/offline.js?v=19f03362a7",
  "assets/js/palette.js?v=d87ad9556c",
  "assets/js/practice.js?v=9b00526017",
  "assets/data/code.js?v=546a080",
  "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"
];
const CACHE = "lolsuit-guide-" + VERSION;
const RUNTIME = "lolsuit-guide-runtime";
const PAGE = "index.html";
const NETWORK_TIMEOUT_MS = 3000;

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys
        .filter((key) => key.startsWith("lolsuit-guide-") && key !== CACHE && key !== RUNTIME)
        .map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

function pageFromNetwork(request) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("slow network")), NETWORK_TIMEOUT_MS);
    // no-cache: always revalidate with the server (a cheap 304 when nothing changed).
    // A plain fetch may be answered from the HTTP cache, which on GitHub Pages
    // (max-age=600) would show a page up to ten minutes old after a deploy.
    fetch(request.url, { cache: "no-cache", credentials: "same-origin" }).then((response) => {
      clearTimeout(timer);
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(PAGE, copy));
      }
      resolve(response);
    }, (error) => { clearTimeout(timer); reject(error); });
  });
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  if (request.mode === "navigate") {
    event.respondWith(pageFromNetwork(request).catch(() =>
      caches.match(PAGE, { ignoreSearch: true }).then((hit) => hit || fetch(request))));
    return;
  }

  event.respondWith(caches.match(request).then((hit) => hit || fetch(request).then((response) => {
    // Keep fonts and any other cross-origin file for next time.
    const url = new URL(request.url);
    if ((response.ok || response.type === "opaque") && url.origin !== self.location.origin) {
      const copy = response.clone();
      caches.open(RUNTIME).then((cache) => cache.put(request, copy));
    }
    return response;
  })));
});
