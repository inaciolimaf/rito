import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TESTS_DIR = path.resolve(__dirname, "..");
const MAX_JOURNEYS = 25;

// Conta chamadas de teste (test(...), test.only(...), test.skip(...)) — não test.describe/
// test.step/test.beforeEach, que não são jornadas próprias.
const TEST_CALL_PATTERN = /\btest(\.(only|skip))?\(/g;

function countJourneysIn(dir: string): { file: string; count: number }[] {
  const results: { file: string; count: number }[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      // "meta" não conta como jornada — e o próprio arquivo deste teste tem a string
      // "test(" no regex/mensagens, o que inflaria a contagem se fosse incluído.
      if (entry.name === "meta") continue;
      results.push(...countJourneysIn(fullPath));
    } else if (entry.name.endsWith(".spec.ts")) {
      const text = readFileSync(fullPath, "utf-8");
      const matches = text.match(TEST_CALL_PATTERN);
      results.push({
        file: path.relative(TESTS_DIR, fullPath),
        count: matches?.length ?? 0,
      });
    }
  }
  return results;
}

test("máximo de 25 jornadas e2e no projeto inteiro (CLAUDE.md §3)", () => {
  const perFile = countJourneysIn(TESTS_DIR);
  const total = perFile.reduce((sum, item) => sum + item.count, 0);

  expect(
    total,
    `${total} jornadas encontradas (máx. ${MAX_JOURNEYS}): ${JSON.stringify(perFile)}. ` +
      "Não coube? Vira teste de integração (CLAUDE.md §3).",
  ).toBeLessThanOrEqual(MAX_JOURNEYS);
});
