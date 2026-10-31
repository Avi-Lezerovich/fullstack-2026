/* highlight.js, bundled (works offline) with only the languages the project uses. */
import type { HLJSApi } from "highlight.js";

let hl: Promise<HLJSApi> | null = null;
export function loadHighlighter(): Promise<HLJSApi> {
  if (!hl) {
    hl = Promise.all([
      import("highlight.js/lib/core"),
      import("highlight.js/lib/languages/python"),
      import("highlight.js/lib/languages/typescript"),
      import("highlight.js/lib/languages/sql"),
      import("highlight.js/lib/languages/yaml"),
      import("highlight.js/lib/languages/bash"),
      import("highlight.js/lib/languages/markdown"),
      import("highlight.js/lib/languages/json"),
      import("highlight.js/lib/languages/xml"),
      import("highlight.js/lib/languages/makefile"),
      import("highlight.js/lib/languages/ini"),
    ]).then(([core, python, ts, sql, yaml, bash, md, json, xml, make, ini]) => {
      const h = core.default;
      h.registerLanguage("python", python.default);
      h.registerLanguage("typescript", ts.default);
      h.registerLanguage("sql", sql.default);
      h.registerLanguage("yaml", yaml.default);
      h.registerLanguage("bash", bash.default);
      h.registerLanguage("markdown", md.default);
      h.registerLanguage("json", json.default);
      h.registerLanguage("xml", xml.default);
      h.registerLanguage("makefile", make.default);
      h.registerLanguage("ini", ini.default);
      return h;
    });
  }
  return hl;
}
