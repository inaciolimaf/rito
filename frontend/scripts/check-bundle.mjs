/**
 * Gate de tamanho do bundle (spec 098, regra 7; frontend-standard, performance.md).
 *
 * Roda DEPOIS do build de produção: medir bytes exige o `dist/`, e o build não cabe na
 * suíte de unidade. O que a suíte de unidade garante é a propriedade ESTRUTURAL (editor e
 * gráficos atrás de fronteira lazy, em `src/App.bundle.test.ts`); o que este script garante
 * é o número.
 *
 *   node scripts/check-bundle.mjs            (ou: make bundle, que faz o build antes)
 *
 * O teto é o que `index.html` carrega antes de a primeira tela aparecer: o script de entrada,
 * os `modulepreload` e o CSS. Chunk de rota não entra: quem não abre a tela não o baixa.
 */
import { gzipSync } from "node:zlib";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, posix } from "node:path";
import { fileURLToPath } from "node:url";

// `fileURLToPath` e NÃO `.pathname`: `URL.pathname` devolve o caminho percent-encoded e
// quebra em checkouts com espaço ou acento (dívida 39).
const DIST = fileURLToPath(new URL("../dist/", import.meta.url));

// Teto do padrão frontend-standard: 250 KB gzip de JS inicial, preloads incluídos.
// Medido em 2026-11-25: 135,2 KB de JS + 5,4 KB de CSS. Sobe só por spec própria.
const TETO_INICIAL_KB = 250;

// Chunks que precisam existir SEPARADOS: se o editor voltar para o bundle inicial por um
// import estático descuidado, o teto pode continuar passando e a regra estaria quebrada.
const CHUNKS_OBRIGATORIOS = ["TemplateEditorPage", "ReportsPage"];

if (!existsSync(join(DIST, "index.html"))) {
  console.error(`dist não encontrado em ${DIST} — rode \`npm run build\` antes.`);
  process.exit(1);
}

const html = readFileSync(join(DIST, "index.html"), "utf8");

// Recursos que o index.html manda carregar já na primeira visita: <script src>,
// <link rel="modulepreload"> e <link rel="stylesheet">. Caminhos absolutos em `/assets/...`.
const referencias = [
  ...html.matchAll(/<script[^>]*\ssrc="([^"]+)"/g),
  ...html.matchAll(/<link[^>]*\srel="(?:modulepreload|stylesheet)"[^>]*\shref="([^"]+)"/g),
  ...html.matchAll(/<link[^>]*\shref="([^"]+)"[^>]*\srel="(?:modulepreload|stylesheet)"/g),
].map((m) => m[1]);
const iniciais = [...new Set(referencias)].filter((url) => /\.(js|css)$/.test(url));

if (iniciais.length === 0) {
  console.error("index.html não referencia nenhum JS/CSS — o build rodou?");
  process.exit(1);
}

const gzipKb = (url) => {
  const arquivo = join(DIST, posix.normalize(url.replace(/^\//, "")));
  return gzipSync(readFileSync(arquivo)).length / 1024;
};

const tamanhos = iniciais.map((url) => ({ url, kb: gzipKb(url) }));
const total = tamanhos.reduce((soma, item) => soma + item.kb, 0);
const problemas = [];

if (total > TETO_INICIAL_KB) {
  problemas.push(`bundle inicial com ${total.toFixed(1)} KB gzip, teto é ${TETO_INICIAL_KB} KB`);
}

const nomesJs = existsSync(join(DIST, "assets")) ? readdirSync(join(DIST, "assets")) : [];
for (const chunk of CHUNKS_OBRIGATORIOS) {
  if (!nomesJs.some((nome) => nome.startsWith(`${chunk}-`))) {
    problemas.push(`${chunk} não saiu em chunk próprio — voltou para o bundle inicial?`);
  }
}

console.log(`bundle inicial: ${total.toFixed(1)} KB gzip (teto ${TETO_INICIAL_KB} KB)`);
for (const { url, kb } of tamanhos.sort((a, b) => b.kb - a.kb)) {
  console.log(`  ${url}: ${kb.toFixed(1)} KB gzip`);
}

if (problemas.length > 0) {
  console.error("\nFALHA (spec 098, regra 7; frontend-standard):");
  for (const problema of problemas) console.error(`  - ${problema}`);
  process.exit(1);
}
