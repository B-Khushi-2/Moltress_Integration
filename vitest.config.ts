import { resolve } from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@renderer": resolve(__dirname, "src/renderer/src"),
      "@shared": resolve(__dirname, "src/shared"),
    },
  },
  test: {
    // The pre-existing suites exercise stock Hermes transports, so they run with
    // the Moltress Agent Layer off. Moltress has its own tests
    // (tests/moltress-transport.test.ts) that pass their config explicitly.
    env: { MOLTRESS_ENABLED: "false" },
    environment: "jsdom",
    globals: true,
    passWithNoTests: true,
    setupFiles: ["./src/renderer/src/test/setup.ts"],
    include: ["src/**/*.test.ts", "src/**/*.test.tsx", "tests/**/*.test.ts"],
  },
});
