import { createStore, useStore } from "./store";

const toastStore = createStore<{ msg: string; n: number }>({ msg: "", n: 0 });
let timer: ReturnType<typeof setTimeout> | undefined;

export function toast(msg: string) {
  toastStore.set((p) => ({ msg, n: p.n + 1 }));
  clearTimeout(timer);
  timer = setTimeout(() => toastStore.set((p) => ({ ...p, msg: "" })), 1900);
}

export function copy(text: string, label?: string) {
  const ok = () => toast("הועתק: " + (label || (text.length > 60 ? text.slice(0, 60) + "…" : text)));
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, () => window.prompt("העתיקו:", text));
  else window.prompt("העתיקו:", text);
}

export function Toast() {
  const { msg } = useStore(toastStore);
  return <div className={"toast" + (msg ? " on" : "")} role="status">{msg}</div>;
}
