import { defineConfig } from "vitest/config";

// Pure-logic unit tests (config precedence, stage mapping, event reducers).
// jsdom gives us localStorage; no React plugin needed — we don't render here.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
  },
});
