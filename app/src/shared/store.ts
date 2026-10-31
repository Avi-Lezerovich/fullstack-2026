/* A tiny external store (useSyncExternalStore) and try/catch-wrapped localStorage. */
import { useSyncExternalStore } from "react";

export interface Store<T> { get(): T; set(next: T | ((prev: T) => T)): void; subscribe(fn: () => void): () => void }

export function createStore<T>(initial: T): Store<T> {
  let value = initial;
  const subs = new Set<() => void>();
  return {
    get: () => value,
    set(next) {
      value = typeof next === "function" ? (next as (p: T) => T)(value) : next;
      subs.forEach((fn) => fn());
    },
    subscribe(fn) { subs.add(fn); return () => { subs.delete(fn); }; },
  };
}

export function useStore<T>(store: Store<T>): T {
  return useSyncExternalStore(store.subscribe, store.get, store.get);
}

export function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) ?? fallback : fallback;
  } catch { return fallback; }
}

export function save(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage blocked */ }
}

/* A store that persists itself under `key`. */
export function persisted<T>(key: string, fallback: T): Store<T> {
  const s = createStore<T>(load(key, fallback));
  s.subscribe(() => save(key, s.get()));
  return s;
}
