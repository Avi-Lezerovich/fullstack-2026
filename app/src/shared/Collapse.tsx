/* A collapsible block built on <details>, so it works with find-in-page and keyboard.
   `meta` sits in the summary line; clicks there (buttons only, no inputs) don't toggle. */
import type { ReactNode } from "react";

export default function Collapse({ title, meta, children, open, id, className, onToggle }: {
  title: ReactNode; meta?: ReactNode; children: ReactNode; open?: boolean; id?: string; className?: string; onToggle?: (open: boolean) => void;
}) {
  return (
    <details className={"clp " + (className || "")} open={open} id={id} onToggle={(e) => onToggle?.((e.currentTarget as HTMLDetailsElement).open)}>
      <summary><span className="clp-chev" aria-hidden="true" /><span className="clp-title">{title}</span>{meta && <span className="clp-meta" onClick={(e) => e.preventDefault()}>{meta}</span>}</summary>
      <div className="clp-body">{children}</div>
    </details>
  );
}
