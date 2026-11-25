import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Contraste de texto (WCAG 1.4.3, 4,5:1) sobre os tokens de `index.css`, nos dois temas.
 * O axe no jsdom não calcula cor, então os pares são lidos dos blocos `:root` e `.dark`.
 *
 * Um par abaixo de 4,5:1 só passa se estiver em `KNOWN_EXCEPTIONS` com o motivo. A lista é
 * dívida: quando o token for corrigido, o teste manda tirar a entrada (ele falha se a exceção
 * já não for mais necessária).
 */
// O vitest roda a partir de `frontend/` (script `test`), então o caminho é relativo a ele.
const CSS_PATH = resolve(process.cwd(), "src/index.css");
const TEXT_MIN_RATIO = 4.5;

type Theme = "light" | "dark";

interface TextPair {
  foreground: string;
  background: string;
}

const PAIRS: TextPair[] = [
  { foreground: "text-primary", background: "surface" },
  { foreground: "text-primary", background: "surface-muted" },
  { foreground: "text-muted", background: "surface" },
  { foreground: "text-muted", background: "surface-muted" },
  { foreground: "accent", background: "surface" },
  { foreground: "accent", background: "surface-muted" },
  { foreground: "danger", background: "surface" },
  { foreground: "danger", background: "surface-muted" },
  { foreground: "success", background: "surface" },
  { foreground: "warning", background: "surface" },
  { foreground: "accent-foreground", background: "accent" },
  { foreground: "danger-foreground", background: "danger" },
  { foreground: "success-foreground", background: "success" },
  { foreground: "warning-foreground", background: "warning" },
];

/** Exceções conhecidas: vazia. Os tokens de tema já passam em 4,5:1; uma nova exceção exige motivo aqui. */
const KNOWN_EXCEPTIONS: Record<string, string> = {};

function readBlock(css: string, selector: string): string {
  const escaped = selector.replace(/[.[\]]/g, "\\$&");
  const match = new RegExp(`${escaped}\\s*\\{([^}]*)\\}`).exec(css);
  if (!match?.[1]) throw new Error(`Bloco ${selector} não encontrado em index.css`);
  return match[1];
}

function readTokens(block: string): Map<string, string> {
  const tokens = new Map<string, string>();
  for (const match of block.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    tokens.set(match[1] ?? "", (match[2] ?? "").trim());
  }
  return tokens;
}

/** `H S% L%` do HSL do Tailwind (`hsl(var(--x) / <alpha>)`) para RGB em 0..1. */
function hslToRgb(value: string): [number, number, number] {
  const match = /([\d.]+)\s+([\d.]+)%\s+([\d.]+)%/.exec(value);
  if (!match) throw new Error(`Token sem HSL válido: ${value}`);
  const h = Number(match[1]);
  const s = Number(match[2]) / 100;
  const l = Number(match[3]) / 100;
  const a = s * Math.min(l, 1 - l);
  const channel = (n: number): number => {
    const k = (n + h / 30) % 12;
    return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  return [channel(0), channel(8), channel(4)];
}

function luminance([r, g, b]: [number, number, number]): number {
  const linear = (c: number): number => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

function contrastRatio(a: string, b: string): number {
  const la = luminance(hslToRgb(a));
  const lb = luminance(hslToRgb(b));
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

const css = readFileSync(CSS_PATH, "utf8");
const THEMES: Record<Theme, Map<string, string>> = {
  light: readTokens(readBlock(css, ":root")),
  dark: readTokens(readBlock(css, ".dark")),
};

describe("contraste de texto sobre os tokens", () => {
  for (const theme of ["light", "dark"] as const) {
    it.each(PAIRS.map((pair) => [pair.foreground, pair.background] as const))(
      `${theme}: %s sobre %s`,
      (foreground, background) => {
        const tokens = THEMES[theme];
        const fg = tokens.get(foreground);
        const bg = tokens.get(background);
        expect(fg, `token --${foreground} em ${theme}`).toBeDefined();
        expect(bg, `token --${background} em ${theme}`).toBeDefined();

        const ratio = contrastRatio(fg ?? "", bg ?? "");
        const key = `${theme} ${foreground} on ${background}`;
        if (ratio >= TEXT_MIN_RATIO) {
          expect(KNOWN_EXCEPTIONS[key], "par passa: remova da lista de exceções").toBeUndefined();
          return;
        }
        expect(
          KNOWN_EXCEPTIONS[key],
          `${key} = ${ratio.toFixed(2)}:1 abaixo de 4,5:1`,
        ).toBeDefined();
      },
    );
  }
});
