/**
 * Gate de tamanho do bundle (spec 098, regra 7).
 *
 * Roda DEPOIS do build, não dentro da suíte de unidade: medir bytes exige um build de
 * produção, que leva mais tempo que todos os 279 testes de front-end somados e não cabe
 * no orçamento de 300 s do `make test`. O que a suíte de unidade garante é a propriedade
 * ESTRUTURAL (editor e gráficos atrás de fronteira lazy, em
 * `src/App.bundle.test.tsx`); o que este script garante é o número.
 *
 *   node scripts/check-bundle.mjs
 */
import { gzipSync } from "node:zlib";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const DIST = new URL("../dist/assets/", import.meta.url).pathname;

// Regra 7. O teto é do bundle INICIAL — o que todo mundo baixa antes de ver qualquer
// coisa. Os chunks de rota não contam: quem nunca abre o editor nunca os baixa.
const TETO_INICIAL_KB = 300;

// Chunks que precisam existir SEPARADOS. Se o editor voltar para o bundle inicial por
// causa de um import estático descuidado, o teto acima até poderia continuar passando
// (o editor tem 153 KB, o inicial tem 138) — e a regra 7 estaria quebrada mesmo assim.
const CHUNKS_OBRIGATORIOS = ["TemplateEditorPage", "ReportsPage"];

const arquivos = readdirSync(DIST).filter((nome) => nome.endsWith(".js"));

const gzipKb = (nome) => gzipSync(readFileSync(join(DIST, nome))).length / 1024;

// O bundle inicial é o `index-<hash>.js`: o entry, o único que o index.html carrega.
const inicial = arquivos.find((nome) => /^index-[\w-]+\.js$/.test(nome));
if (!inicial) {
  console.error("não achei o chunk inicial em dist/assets — o build rodou?");
  process.exit(1);
}

const tamanhoInicial = gzipKb(inicial);
const problemas = [];

if (tamanhoInicial > TETO_INICIAL_KB) {
  problemas.push(
    `bundle inicial com ${tamanhoInicial.toFixed(1)} KB gzip, teto é ${TETO_INICIAL_KB} KB`,
  );
}

for (const chunk of CHUNKS_OBRIGATORIOS) {
  if (!arquivos.some((nome) => nome.startsWith(`${chunk}-`))) {
    problemas.push(`${chunk} não saiu em chunk próprio — voltou para o bundle inicial?`);
  }
}

console.log(`bundle inicial: ${tamanhoInicial.toFixed(1)} KB gzip (teto ${TETO_INICIAL_KB} KB)`);
for (const nome of arquivos.filter((n) => n !== inicial).sort()) {
  console.log(`  ${nome}: ${gzipKb(nome).toFixed(1)} KB gzip`);
}

if (problemas.length > 0) {
  console.error("\nFALHA (spec 098, regra 7):");
  for (const problema of problemas) console.error(`  - ${problema}`);
  process.exit(1);
}
