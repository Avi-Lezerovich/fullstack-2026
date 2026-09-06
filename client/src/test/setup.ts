/**
 * Vitest's per-file setup, named by vite.config.ts.
 *
 * It brings in jest-dom's matchers (`toBeInTheDocument` and friends) and
 * unmounts anything a test rendered, so one test's DOM cannot be found by the
 * next one's query.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
