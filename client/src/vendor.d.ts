/**
 * Ambient declarations for the two RTL packages, neither of which ships types.
 * Only the pieces main.tsx actually uses are declared, typed as the plugin
 * shape Emotion expects so the cache config stays properly checked.
 */

declare module "stylis" {
  import type { StylisPlugin } from "@emotion/cache";
  export const prefixer: StylisPlugin;
}

declare module "stylis-plugin-rtl" {
  import type { StylisPlugin } from "@emotion/cache";
  const rtlPlugin: StylisPlugin;
  export default rtlPlugin;
}
