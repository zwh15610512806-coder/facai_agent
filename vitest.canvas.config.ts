import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["frontend/canvas/src/**/*.test.ts"],
    setupFiles: ["./frontend/canvas/test/setup.ts"],
  },
});
