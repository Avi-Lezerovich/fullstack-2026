/* The code pane as a full page: file, all files, grep and find-usages side by side with
   nothing else in the way. */
import { useEffect } from "react";
import CodePane from "../../shared/CodePane";
import { paneStore } from "../../shared/pane";

export default function CodePage() {
  useEffect(() => {
    const s = paneStore.get();
    paneStore.set({ ...s, open: true, tab: s.path ? s.tab : "files" });
    // leaving the page should not leave the docked pane open on top of the next one
    return () => paneStore.set((p) => ({ ...p, open: false }));
  }, []);
  return <div className="code-page"><CodePane docked={false} /></div>;
}
