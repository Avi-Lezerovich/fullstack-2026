/// <reference types="vite/client" />

// stylis ships without bundled types; declare an ambient module so the prefixer
// import in main.tsx type-checks without pulling in @types/stylis.
declare module "stylis";
