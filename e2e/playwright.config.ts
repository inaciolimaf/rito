import { cpus } from "node:os";
import { defineConfig } from "@playwright/test";

const API_BASE_URL = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Quantas vezes esta máquina é mais lenta que a de referência (4 núcleos, onde os prazos
// abaixo foram calibrados). O runner do GitHub tem 2 — metade da máquina, e ainda dividida
// com o pytest e o vitest, que rodam CONCORRENTES (CLAUDE.md §3).
//
// Escalar o prazo não é afrouxar o teste: o que ele afirma é «a jornada acontece», não «a
// jornada acontece em 30 s». Prazo fixo num host duas vezes mais lento mede a máquina, não
// o produto — e falha em jornadas DIFERENTES a cada execução, que é como esta configuração
// se manifestava no CI (auth/customers/financial numa corrida, inbox/publications na
// seguinte). Um gate que sorteia qual teste reprova não diz nada sobre o código.
const LENTIDAO = Math.max(1, 4 / Math.min(4, cpus().length));
const prazo = (base: number): number => Math.round(base * LENTIDAO);

// Máximo de 25 jornadas no projeto inteiro — ver CLAUDE.md §3.
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  // Dívida 33: as três suítes do `make test` rodam CONCORRENTES (CLAUDE.md §3), e o
  // `run-tests.sh` já limita as outras duas por isso — pytest em 3 workers, vitest em 1,
  // "para dar ar às outras suítes". O e2e era o único sem teto: fora do CI, `undefined`
  // significa UM WORKER POR NÚCLEO (12 nesta máquina), disputando CPU com o pytest, o
  // vitest, o uvicorn e o vite ao mesmo tempo.
  //
  // O sintoma era jornada caindo por lentidão, sempre nas cinco que passam por um
  // `EntityPicker` — o seletor assíncrono espera a busca voltar, e sob disputa a resposta
  // não chega dentro dos 5 s padrão do `expect`. Cinco reprovaram numa execução; a
  // seguinte, com a mesma árvore, fechou 10/10.
  //
  // Três é o mesmo teto do pytest, pelo mesmo motivo. `PLAYWRIGHT_WORKERS` devolve o
  // comportamento antigo em máquina dedicada.
  // O teto continua 4 no CI e 3 aqui, mas agora ENCOLHE em máquina pequena: o runner do
  // GitHub tem 2 núcleos, e 4 workers de e2e somados aos do pytest e do vitest davam 8
  // processos de teste para 2 CPUs. Três jornadas estouravam o timeout de 30 s por
  // inanição de CPU — o dialog do Radix não fechava a tempo, e o sintoma parecia defeito
  // de produto. É a dívida 33 outra vez, num host que a spec 120 não tinha medido.
  workers: Number(
    process.env.PLAYWRIGHT_WORKERS ??
      Math.max(1, Math.min(process.env.CI ? 4 : 3, cpus().length - 1)),
  ),
  // 30 s na máquina de referência, 60 s em duas CPUs. O padrão do Playwright é 30 s fixos.
  timeout: prazo(30_000),
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
      timeout: prazo(30_000),
    },
    {
      command: "npm run dev -- --port 5173 --strictPort",
      cwd: "../frontend",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: prazo(30_000),
    },
  ],
});
