import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // tsconfig.json sets jsx: "preserve" because Next does its own transform.
  // Vitest has no Next in front of it, so it needs the automatic runtime or
  // every component test fails with "React is not defined".
  esbuild: { jsx: "automatic" },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Only our own tests. Without this, vitest walks node_modules.
    include: ["src/**/*.test.{ts,tsx}"],
    // No coverage threshold here. The backend gates on one; the frontend's value
    // is in what these tests assert, and a number would mostly reward rendering
    // more markup.
  },
  resolve: {
    // Mirror the "@/*" path alias from tsconfig.json.
    alias: { "@": resolve(__dirname, "./src") },
  },
});
