/* data/maps.json (scripts/build-data.mjs): endpoint chains and the env map. */
import { createStore } from "../shared/store";

export interface Loc { file: string; line: number }
export interface ServiceCall extends Loc { name: string; tables: string[] }
export interface Chain {
  fn: string; method: string; path: string; client: Loc; callers: Loc[];
  route: (Loc & { handler: string; handlerLine: number; auth: string; path: string }) | null;
  services: ServiceCall[]; tables: (Loc & { name: string })[];
}
export interface Orphan extends Loc { method: string; path: string; handler: string; handlerLine: number; auth: string; services: ServiceCall[] }
export interface EnvVar {
  name: string; field: string | null;
  code: { kind: string; default: string; line: number } | null;
  example: { value: string; commented: boolean; line: number } | null;
  compose: { default: string | null; required: boolean; line: number } | null;
  prod: { default: string | null; required: boolean; line: number } | null;
  readers: Loc[];
}
export interface Maps { commit: string; chains: Chain[]; orphans: Orphan[]; env: EnvVar[] }

export const mapsStore = createStore<Maps | null>(null);
let p: Promise<Maps> | null = null;
export function loadMaps() {
  if (!p) p = fetch("data/maps.json").then((r) => r.json() as Promise<Maps>).then((m) => { mapsStore.set(m); return m; });
  return p;
}
