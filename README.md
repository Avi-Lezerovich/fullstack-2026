# LolSuit study guide (GitHub Pages)

This branch holds only the static study-guide site for the LolSuit project.
It shares no history with `main` and contains no application code, apart from a
generated snapshot of it that the code viewer reads.

Published at https://avi-lezerovich.github.io/fullstack-2026/

## Layout

```
src/
  layout.html              page shell: top bar, sidebar, footer, script tags
  sw.js                    service-worker template (build.py fills in the file list)
  topics/NN-name.html      one file per topic, included in file-name order
  topics/00-exam-finder/   the finder's groups ("asked to change X, where is it?")
  topics/13-cookbook/      one file per change recipe
assets/
  css/   base.css (tokens, layout) · components.css (topics, diagrams) · tools.css (palette, code pane, finder)
  js/    diagrams.js · core.js · code-viewer.js · palette.js · practice.js · offline.js
         (share window.Guide; loaded in that order)
  data/  seq-data.js (hand-written) · code-index.js + code.js (generated)
  img/
tools/
  build_code.py   snapshot the app's source into assets/data/
  build.py        assemble index.html from src/ and check every path:line reference
index.html        GENERATED: edit src/, not this file
sw.js             GENERATED: the service worker that keeps the guide usable offline
manifest.webmanifest  lets the browser install the guide as an app
.nojekyll         serve the files as-is
```

## Build

```bash
python tools/build_code.py ../fullstack-2026   # only when the app's code changed
python tools/build.py                          # always, after editing src/ or assets/
python tools/build.py --check                  # exit 1 if index.html or sw.js is stale
```

`build.py` inlines `<!-- @include path -->`, stamps every local asset with
`?v=<content hash>` so browsers never mix a cached script with a newer page, and
fails if a `path:line` in the guide points at a missing file or past its end. It
also writes `sw.js`, whose cache version changes whenever any of those files do.

Preview locally with `python -m http.server` in this folder (the code viewer
loads its data over HTTP, so opening the file directly will not work).

## Features

- **Ctrl+K or `/`**: one search over the finder, recipes, topics, exam questions,
  code symbols (functions, constants, routes, tables, env vars) and files.
- **Code viewer**: every file or symbol mentioned in the guide opens the real
  code at that line; in-browser grep across all files; copy `path:line`.
- **Open in VS Code**: "פתח ב־VS Code" in the code pane, or Alt+click on any path,
  opens `vscode://file/C:/Users/lzr/Documents/GitHub/fullstack-2026/<path>:<line>`
  (the folder is `LOCAL_ROOT` in assets/js/code-viewer.js).
- **Find usages**: click any name in the code pane to see how many lines use it,
  jump to its definition, or list every usage (opened files highlight the term).
- **Offline**: `sw.js` caches the page, every asset, the code snapshot and
  highlight.js on the first visit; fonts on the second. The sidebar says when the
  guide is saved. The page is network-first (3 s timeout), assets cache-first.
- **Practice (topic 20)**: a random recipe as a timed task with two hints and the
  full solution, all cloned from the recipe's own markup; results per recipe in
  localStorage.
- **Recent**: Ctrl+K with nothing typed lists what you opened last.
