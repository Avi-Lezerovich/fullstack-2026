/* Exam-session state, kept in this browser: the task being worked on, the pasted diff,
   checklists, notes and the clock. */
import { persisted } from "../shared/store";

export interface TaskRef { kind: "recipe" | "finder"; id: string; title: string; refs: string[]; verifyHtml?: string }
export interface Note { id: number; at: number; text: string; ref?: string }
export interface Clock { running: boolean; startedAt: number; elapsed: number; targetMin: number }

export const taskStore = persisted<TaskRef | null>("lolsuit-exam-task", null);
export const diffStore = persisted<string>("lolsuit-exam-diff", "");
export const checksStore = persisted<Record<string, boolean>>("lolsuit-exam-checks", {});
export const notesStore = persisted<Note[]>("lolsuit-exam-notes", []);
export const clockStore = persisted<Clock>("lolsuit-exam-clock", { running: false, startedAt: 0, elapsed: 0, targetMin: 0 });
export const pinsStore = persisted<string[]>("lolsuit-exam-pins", []);
export const timerUiStore = persisted<{ x: number; y: number; open: boolean }>("lolsuit-exam-timer-ui", { x: 16, y: 16, open: false });

export function clockSeconds(c: Clock, now = Date.now()) {
  return Math.floor((c.elapsed + (c.running ? now - c.startedAt : 0)) / 1000);
}

export function addNote(text: string, ref?: string) {
  if (!text.trim() && !ref) return;
  notesStore.set((n) => [...n, { id: Date.now(), at: Date.now(), text: text.trim(), ref }]);
}

/* Files named in a `git diff` or `git status --short` paste. */
export function changedFiles(paste: string): string[] {
  const out = new Set<string>();
  for (const raw of paste.split(/\r?\n/)) {
    const line = raw.replace(/\x1b\[[0-9;]*m/g, "");
    let m = /^diff --git a\/(\S+) b\/(\S+)/.exec(line);
    if (m) { out.add(m[2]); continue; }
    m = /^\+\+\+ b\/(\S+)/.exec(line);
    if (m) { out.add(m[1]); continue; }
    // status --short: "XY path" or "R  old -> new"
    m = /^\s?[MADRCU?!]{1,2}\s+(?:\S+ -> )?(\S+)$/.exec(line);
    if (m) { out.add(m[1].replace(/^"|"$/g, "")); continue; }
    // diff --stat: " path | 3 ++-"
    m = /^\s*(\S+)\s+\|\s+\d+/.exec(line);
    if (m && m[1].includes("/") ) out.add(m[1]);
  }
  return [...out];
}
