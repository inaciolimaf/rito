import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import tailwindConfig from "../../tailwind.config";

const SRC_DIR = resolve(__dirname, "..");
const SEMANTIC_ROOTS = [
  "surface",
  "primary",
  "on-primary",
  "muted",
  "accent",
  "danger",
  "warning",
  "success",
  "default",
  "overlay",
];

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      return sourceFiles(path);
    }
    const isProductCode = /\.(ts|tsx)$/.test(entry) && !/\.test\.(ts|tsx)$/.test(entry);
    return isProductCode ? [path] : [];
  });
}

function definedColorNames(): Set<string> {
  const colors = tailwindConfig.theme?.extend?.colors ?? {};
  return new Set(Object.keys(colors));
}

describe("tokens semânticos", () => {
  it("toda classe de cor semântica usada no código existe na configuração do Tailwind", () => {
    const defined = definedColorNames();
    const pattern = new RegExp(
      `\\b(?:text|bg|border|ring|fill|stroke|divide|outline)-(${SEMANTIC_ROOTS.join("|")})(?![\\w-])`,
      "g",
    );
    const missing = new Set<string>();

    for (const file of sourceFiles(SRC_DIR)) {
      const content = readFileSync(file, "utf8");
      for (const match of content.matchAll(pattern)) {
        const name = match[1] ?? "";
        const rootName = name.split("-")[0] ?? name;
        const known = defined.has(name) || defined.has(rootName);
        if (!known) {
          missing.add(`${name} em ${file.slice(SRC_DIR.length + 1)}`);
        }
      }
    }

    expect([...missing]).toEqual([]);
  });

  it("o CSS global tem o bloco de movimento reduzido", () => {
    const css = readFileSync(join(SRC_DIR, "index.css"), "utf8");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
  });
});
