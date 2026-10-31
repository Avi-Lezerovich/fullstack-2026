/* State of the code pane, shared by every link that opens it. */
import { createStore } from "./store";
import type { GrepOpts } from "./code";

export type PaneTab = "file" | "files" | "grep" | "usages";
export interface PaneState {
  open: boolean; wide: boolean; tab: PaneTab;
  path: string | null; line: number; end: number; term: string; nonce: number;
  grep: { q: string; opts: GrepOpts; nonce: number };
  usage: string;
}

export const paneStore = createStore<PaneState>({
  open: false, wide: false, tab: "file", path: null, line: 0, end: 0, term: "", nonce: 0,
  grep: { q: "", opts: {}, nonce: 0 }, usage: "",
});

export function openFile(path: string, line = 0, end = 0, term = "") {
  paneStore.set((s) => ({ ...s, open: true, tab: "file", path, line, end: end > line ? end : line, term, nonce: s.nonce + 1 }));
}
export function openGrep(q: string, opts: GrepOpts = {}) {
  paneStore.set((s) => ({ ...s, open: true, tab: "grep", grep: { q, opts, nonce: s.grep.nonce + 1 } }));
}
export function openUsages(name: string) {
  paneStore.set((s) => ({ ...s, open: true, tab: "usages", usage: name }));
}
export function openPane(tab: PaneTab = "files") { paneStore.set((s) => ({ ...s, open: true, tab })); }
export function closePane() { paneStore.set((s) => ({ ...s, open: false })); }
