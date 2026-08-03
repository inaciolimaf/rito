import { defineConfig } from "@playwright/test";

const API_BASE_URL = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Máximo de 25 jornadas no projeto inteiro — ver CLAUDE.md §3.
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  workers: process.env.CI ? 4 : undefined,
  reporter: "list",
  globalSetup: "./global-setup.ts",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "uv run uvicorn app.main:app --host 0.0.0.0 --port 8000",
      cwd: "../backend",
      // As jornadas fazem 6+ logins (UI + setup de API) no mesmo minuto — com o
      // limite de produção (5/60s) a última jornada tomava 429 (flake da spec 036).
      env: { ...process.env, LOGIN_RATE_LIMIT: "100" },
      url: `${API_BASE_URL}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      cwd: "../frontend",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
