/**
 * Gate de duplicação (spec 119).
 *
 * A «regra dos 3 usos» (`CLAUDE.md` §6) é a regra cultural mais citada do projeto e era a
 * única sem instrumento. Este script dá um número a ela e trava o número: um teto por
 * linguagem, no valor medido + 0,1 pp. Não é um alvo aspiracional — um teto que ninguém
 * atinge reprova o PR de quem não causou o problema, e o fim previsível é o gate desligado.
 *
 * Roda FORA do `make test`, como passo próprio do CI ao lado do `bundle:check` (098):
 * não é teste e não deve consumir os 300 s do orçamento.
 *
 *   npm run dup:check          (a partir de frontend/)
 *
 * A configuração — caminhos, formatos, `min-lines`/`min-tokens`, exclusões e os tetos —
 * vive em `.jscpd.json` na raiz, para que o mesmo comando dê o mesmo número em qualquer
 * máquina. Testes ficam de fora: repetição em teste costuma ser legítima (cada teste conta
 * sua história inteira) e medir junto contamina o número.
 */
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

// `fileURLToPath`, não `url.pathname`: o caminho do checkout pode ter acento e o
// pathname da URL vem percent-encoded.
const RAIZ = fileURLToPath(new URL("../../", import.meta.url));
const CONFIG = join(RAIZ, ".jscpd.json");

const config = JSON.parse(readFileSync(CONFIG, "utf8"));
const tetos = config.thresholds ?? {};

const saida = mkdtempSync(join(tmpdir(), "jscpd-"));
try {
  const execucao = spawnSync(
    join(RAIZ, "frontend/node_modules/.bin/jscpd"),
    ["--config", CONFIG, "--reporters", "json,silent", "--output", saida],
    { cwd: RAIZ, encoding: "utf8" },
  );

  // `thresholds` é campo NOSSO, não do jscpd: ele só entende um teto global, e a spec 119
  // pede um por linguagem. O jscpd ignora o campo e avisa; o aviso é esperado e não vira
  // ruído no log do CI — qualquer outra linha de stderr passa.
  for (const linha of (execucao.stderr ?? "").split("\n")) {
    if (linha && !linha.includes("unknown field 'thresholds'")) console.error(linha);
  }
  if (execucao.status !== 0) {
    console.error(`jscpd terminou com código ${execucao.status}`);
    process.exit(1);
  }

  const relatorio = JSON.parse(readFileSync(join(saida, "jscpd-report.json"), "utf8"));
  const formatos = relatorio.statistics.formats;

  // Cada arquivo é contado UMA vez: os formatos declarados em `.jscpd.json` têm extensões
  // disjuntas (.py / .ts / .tsx). O jscpd 4 contava os mesmos .tsx duas vezes — uma como
  // `tsx`, outra como `javascript` — e inflava o total; por isso a lista é explícita.
  const analisados = Object.values(formatos).reduce((soma, f) => soma + f.sources, 0);

  const problemas = [];
  console.log(`duplicação em ${analisados} arquivos de produção (backend/app + frontend/src):`);
  for (const [formato, dados] of Object.entries(formatos).sort()) {
    const teto = tetos[formato];
    const pct = dados.percentage;
    const rotuloTeto = teto === undefined ? "sem teto" : `teto ${teto.toFixed(2)}%`;
    console.log(
      `  ${formato.padEnd(11)} ${pct.toFixed(2)}% ` +
        `(${dados.duplicatedLines}/${dados.lines} linhas, ${dados.clones} clones) — ${rotuloTeto}`,
    );
    if (teto !== undefined && pct > teto) {
      problemas.push(`${formato} com ${pct.toFixed(2)}% de duplicação, teto é ${teto.toFixed(2)}%`);
    }
  }

  if (problemas.length > 0) {
    console.error("\nFALHA (spec 119):");
    for (const problema of problemas) console.error(`  - ${problema}`);
    console.error(
      "\nExtraia o padrão repetido para components/domain/ (front) ou para uma função/" +
        "BaseRepository (back) — CLAUDE.md §6. Subir o teto é a última opção, e precisa de spec.",
    );
    process.exit(1);
  }
} finally {
  rmSync(saida, { recursive: true, force: true });
}
