import { defineConfig } from "@playwright/test";

// Máximo de 25 jornadas no projeto inteiro — ver CLAUDE.md §3.
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  workers: process.env.CI ? 4 : undefined,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
});
