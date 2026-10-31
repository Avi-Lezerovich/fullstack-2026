# LolSuit study guide (GitHub Pages)

This branch holds only the study-guide site for the LolSuit project. It shares no
history with `main` and contains no application code, apart from a generated
snapshot of it that the code viewer reads.

Published at https://avi-lezerovich.github.io/fullstack-2026/ (Pages serves the
branch root as-is; there is no Actions workflow).

The site is two windows built from one React app:

| Window | URL | For |
| --- | --- | --- |
| Study | `index.html` | learning before the exam: topics, Q&A drill, timed practice, progress |
| Exam | `exam.html` | working during the exam: finder, recipes, commands, code, flows, env map, workbench |

Each window has a button that opens the other one in its own browser window.

## Layout

```
app/                         source (Vite + React 18 + TypeScript)
  index.html  exam.html      the two entries
  content/                   topic HTML, one file per topic (+ finder groups, cookbook recipes)
  plugins/content.ts         virtual:topics: inlines <!-- @include -->, checks every path:line
  scripts/build-data.mjs     snapshot the app's code -> public/data/{code-index,code,maps}.json
  scripts/clean-root.mjs     delete the previous build output from the branch root
  scripts/write-sw.mjs       write ../sw.js from the emitted files
  src/shared/                shell, code pane, palette, VS Code links, diagrams, stores
  src/study/                 the study window
  src/exam/                  the exam window (pages/ + the timer, status lights, maps)
  src/styles/                base/content/tools (original design) + shell/exam (new)
  public/                    copied as-is: data/, img/, manifest.webmanifest
index.html exam.html assets/ data/ img/ sw.js manifest.webmanifest   GENERATED, committed
.nojekyll                    serve the files as-is
```

## Build

```bash
cd app
npm install
npm run data -- ../../fullstack-2026   # only when the app's code changed (git HEAD of that checkout)
npm run build                          # typecheck, clean the root, vite build, write sw.js
```

Then commit the branch root together with `app/`. `npm run build` fails if any
`path:line` in the content points at a missing file or past its end.

Local use: `npm run dev` (port 5180, hot reload), or serve the branch root as Pages
does, e.g. `python -m http.server 8765` from this folder, and open `/` and `/exam.html`.

## Exam window tools

- **Ctrl+K or `/`**: one search over the finder, recipes, topics, code symbols, files,
  commands, troubleshooting, endpoints and env vars. Alt+Enter opens the hit in VS Code.
- **Code** with find usages: definition + every usage grouped by file.
- **Open in VS Code**: `vscode://file/C:/Users/lzr/Documents/GitHub/fullstack-2026/<path>:<line>`
  (`LOCAL_ROOT` in `app/src/shared/vscode.ts`). Finder items, recipes and flows have
  "VS Code ×N", which opens every file of the task.
- **Flows**: each `api.ts` call as a chain: component → api.ts → route → service → tables.
- **Env & ports**: every variable in `config.py`, `.env.example` and both compose files,
  who reads it, and the mismatches (compose overrides the default, not passed to docker).
- **Commands**: collapsible groups and commands, shell badges, copy, pins.
- **Workbench**: pick a task; paste `git status --short` / `git diff` to see unexpected
  and untouched files; a verify checklist built from the changed files; a git helper.
- **Status lights**: probes the API (5002), the client (5174) and docker web (8080).
- **Timer and notes**: a draggable clock with a target and timestamped notes.
- **Offline**: `sw.js` precaches both pages, every asset and the code snapshot;
  pages are network-first (3 s timeout).

Progress, notes and settings live in this browser's localStorage.
