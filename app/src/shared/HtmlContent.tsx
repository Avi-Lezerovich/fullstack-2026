/* Renders a fragment of topic HTML and wires it up (code links, copy, diagrams, actions).
   `widgets` replace `<div data-widget="name">` placeholders with React. */
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { enhance } from "./enhance";
import { indexStore } from "./code";
import { useStore } from "./store";
import { zoomStore } from "./Zoom";

export default function HtmlContent({ html, className, widgets, onReady }: {
  html: string; className?: string; widgets?: Record<string, ReactNode>; onReady?: (root: HTMLElement) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const idx = useStore(indexStore);
  const [slots, setSlots] = useState<[string, HTMLElement][]>([]);
  useLayoutEffect(() => {
    const root = ref.current!;
    root.innerHTML = html;
    setSlots(Array.from(root.querySelectorAll<HTMLElement>("[data-widget]")).map((el) => [el.dataset.widget!, el]));
  }, [html]);
  useEffect(() => {
    const root = ref.current!;
    const off = enhance(root, (svg, title) => zoomStore.set({ svg: svg.cloneNode(true) as SVGSVGElement, title }));
    onReady?.(root);
    return off;
    // idx: re-link once the code index arrives
  }, [html, idx]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <>
      <div ref={ref} className={className} />
      {widgets && slots.map(([name, el]) => widgets[name] ? createPortal(widgets[name], el, name) : null)}
    </>
  );
}
