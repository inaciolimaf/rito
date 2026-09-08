import { mkdtempSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TESTS_DIR = path.resolve(__dirname, "..");
const MAX_JOURNEYS = 25;
// Piso entregue pela spec 139. Até ela este gate afirmava só `<= MAX_JOURNEYS`, e zero
// satisfaz isso: apagar as nove jornadas deixava `make test` verde e MAIS RÁPIDO, porque
// o wall-clock do CLAUDE.md §11 melhorava junto. O teto nunca foi o risco.
//
// O número é o MEDIDO hoje (9 jornadas em 9 arquivos), no molde do piso de cobertura da
// spec 117: sobe quando a medição sobe, e descer exige spec própria com o motivo escrito.
const MIN_JOURNEYS = 9;

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

function checkJourneyCount(perFile: { file: string; count: number }[]): void {
  const total = perFile.reduce((sum, item) => sum + item.count, 0);
  const detail = `${total} jornadas encontradas: ${JSON.stringify(perFile)}. `;

  expect(
    total,
    `${detail}Máx. ${MAX_JOURNEYS} — não coube? Vira teste de integração (CLAUDE.md §3).`,
  ).toBeLessThanOrEqual(MAX_JOURNEYS);
  expect(
    total,
    `${detail}Mín. ${MIN_JOURNEYS} — jornada não se apaga para o wall-clock caber: ou o ` +
      "piso desce numa spec própria, com o motivo escrito, ou a jornada volta.",
  ).toBeGreaterThanOrEqual(MIN_JOURNEYS);
}

test("as jornadas e2e ficam entre o piso de 9 e o teto de 25 (CLAUDE.md §3)", () => {
  checkJourneyCount(countJourneysIn(TESTS_DIR));
});

test("o piso reprova um e2e esvaziado, e o teto um e2e inchado", () => {
  // Caso plantado (spec 139): o cenário medido pela auditoria — as nove jornadas
  // apagadas, sobrando só este arquivo de meta. Antes do piso, isso passava.
  const raiz = mkdtempSync(path.join(tmpdir(), "rito-journey-"));
  mkdirSync(path.join(raiz, "meta"));
  writeFileSync(
    path.join(raiz, "meta", "journey-count.spec.ts"),
    'test("máximo de 25 jornadas", () => {});\n',
  );
  expect(countJourneysIn(raiz), "o contador passou a contar o gate meta").toHaveLength(0);
  expect(() => checkJourneyCount(countJourneysIn(raiz))).toThrow();

  // Controle: com as nove de volta, a MESMA checagem passa.
  writeFileSync(
    path.join(raiz, "jornadas.spec.ts"),
    Array.from({ length: MIN_JOURNEYS }, (_, i) => `test("jornada ${i}", () => {});`).join("\n"),
  );
  checkJourneyCount(countJourneysIn(raiz));

  // E o outro lado do gate continua mordendo.
  expect(() =>
    checkJourneyCount([{ file: "inchado.spec.ts", count: MAX_JOURNEYS + 1 }]),
  ).toThrow();
});
