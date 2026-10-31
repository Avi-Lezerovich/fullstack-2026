/* Register the service worker (built by scripts/write-sw.mjs) and report whether the
   guide is ready to work with no internet. */
import { createStore } from "./store";

export const offlineStore = createStore<{ ready: boolean; online: boolean }>({ ready: false, online: navigator.onLine });

async function check() {
  let ready = false;
  try {
    const keys = await caches.keys();
    ready = keys.some((k) => k.startsWith("lolsuit-guide-") && !k.endsWith("runtime")) && !!navigator.serviceWorker?.controller;
  } catch { /* no Cache API */ }
  offlineStore.set({ ready, online: navigator.onLine });
}

export function registerSW() {
  if (location.protocol === "file:" || !("serviceWorker" in navigator) || import.meta.env.DEV) return;
  navigator.serviceWorker.register("sw.js").then(() => navigator.serviceWorker.ready).then(() => setTimeout(check, 500)).catch(() => {});
  navigator.serviceWorker.addEventListener("controllerchange", check);
  window.addEventListener("online", check);
  window.addEventListener("offline", check);
  check();
}
