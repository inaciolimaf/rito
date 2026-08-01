import { execFileSync } from "node:child_process";

export default function globalSetup(): void {
  execFileSync("uv", ["run", "python", "scripts/seed_e2e.py"], {
    cwd: "../backend",
    stdio: "inherit",
  });
}
