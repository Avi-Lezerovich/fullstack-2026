import { useEffect, useRef } from "react";
import { createStore, useStore } from "./store";

export const zoomStore = createStore<{ svg: SVGSVGElement; title: string } | null>(null);

export function ZoomDialog() {
  const z = useStore(zoomStore);
  const dlg = useRef<HTMLDialogElement>(null);
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const d = dlg.current!;
    if (z) {
      body.current!.replaceChildren(z.svg);
      if (!d.open) d.showModal();
    } else if (d.open) d.close();
  }, [z]);
  return (
    <dialog className="zoom" ref={dlg} aria-label="תרשים מוגדל" onClose={() => zoomStore.set(null)}
      onClick={(e) => { if (e.target === dlg.current) zoomStore.set(null); }}>
      <div className="zhead"><span className="ztitle">{z?.title}</span><button className="btn" type="button" onClick={() => zoomStore.set(null)}>סגור</button></div>
      <div className="zbody" ref={body} />
    </dialog>
  );
}
