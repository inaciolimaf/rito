# Frontend-standard: performance e garantias

Auditoria do `frontend-standard` (tabela `references/guarantees.md` e `performance.md`) contra o
frontend do Rito, em 2026-11-25. Formato: regra | estado | ação | dívida. Dívida é o que o padrão
pede e o código ainda não cumpre; cada item tem uma forma de descer (tirar da lista de baseline,
trocar o número, escrever a spec).

## Orçamento de bundle

| Medida | Antes | Depois |
|---|---|---|
| Teto do JS inicial | 300 KB, só `index-*.js` | **250 KB** gzip, o que `index.html` carrega: script de entrada, `modulepreload` e CSS |
| JS inicial (entry) | 138,4 KB gzip (medido antes do rebase) | 136,5 KB gzip |
| CSS inicial | 5,4 KB gzip (fora da conta) | 5,4 KB gzip (dentro da conta) |
| **Total inicial** | 138,4 KB (JS) + CSS fora da conta | **141,9 KB** gzip, folga de 108 KB |
| Chunks de rota | uma por página, `React.lazy` (editor de modelos 153 KB gzip e relatórios 13,9 KB gzip fora do inicial) | igual |

O número "antes" do JS sozinho veio do gate antigo, medido antes do rebase para
`chore/project-standard`; o "depois" é do build já rebaseado. A diferença de 2 KB entre os dois
vem do código que chegou com o rebase, não de uma mudança de performance desta rodada.

Gate: `make bundle` (faz o build e roda `frontend/scripts/check-bundle.mjs`). O CI já chama
`npm run bundle:check` depois do build.

Rotas: já estão em `React.lazy` (uma por página, em `src/App.tsx`); a tela de login e o shell
ficam estáticos de propósito. Nada a fazer.

## Regras

| Regra | Estado | Ação feita | Dívida |
|---|---|---|---|
| `react-hooks/exhaustive-deps` como erro | **ok** | promovido de aviso para erro; nenhum violação existente | — |
| `max-lines-per-function` 100 (sem brancos e comentários) em `src/` | **ok com baseline** | regra ativa; 52 arquivos existentes em `DEBT_FUNCTION_SIZE` | 52 arquivos com função acima de 100 linhas (lista em `frontend/eslint.config.js`) |
| `max-lines` 300 por arquivo em `src/` | **ok com baseline** | regra ativa; 8 arquivos em `DEBT_FILE_SIZE` | 8 arquivos acima de 300 linhas (`CustomerListPage`, `DocumentBrowser`, `TransactionsListPage`, `financial/api.ts`, `LawsuitsPage`, `lawsuits/api.ts`, `reports/api.ts`, `reportDefinitions.tsx`) |
| Testes isentos de tamanho | ok | `**/*.test.*`, `src/test/**`, `src/mocks/**` ficam fora das duas regras de tamanho | — |
| Número e data formatados em um lugar só (`no-restricted-properties` em `toLocale*`) | **ok com baseline** | regra ativa fora de `src/lib/`; 33 arquivos em `DEBT_FORMATTING` | 33 arquivos chamam `toLocale*` direto; devem passar por `src/lib` |
| Teclado escutado em um lugar só (`addEventListener("keydown")`) | **ok com baseline** | regra ativa; 6 arquivos em `DEBT_KEYBOARD` | 6 arquivos (`CopilotPanel`, `GlobalSearch`, `EditorAiAssistant`, `AiSuggestionOverlay`, `SlashCommandMenu`, `useClickOutside`) devem usar um hook de atalho |
| Rota lê os próprios parâmetros (`useParams({...})`) | ok | regra ativa; zero uso com argumento hoje | — |
| Componente genérico e lib não importam feature (`no-restricted-imports` em `components/domain`, `components/ui`, `lib`) | **ok com baseline** | regra ativa; 1 arquivo em `DEBT_LAYER` | `components/domain/IntegrationAlertBanner.tsx` importa `@/features/integration-alerts/api` |
| Cor só por token | ok | já existia (`rito/no-literal-tailwind-color`) | — |
| Import entre features (`features/x` → `features/y`) | **gap** | nenhuma regra: a regra precisa de "só pela API pública da feature" e 76 imports em 47 arquivos a violariam | decidir a fronteira antes de escrever a regra |
| Um `root` skeleton por tela (`expectOneDocument`) | gap | não criado | teste de tela ainda não usa este helper |
| Tipos da API gerados do OpenAPI | **ok (gerado)** | `openapi-typescript` 7.13.0; `npm run types:api` gera `frontend/generated/api-schema.ts`; `make api-types` e `make api-types-check` | o cliente em `src/features/*/api.ts` ainda escreve tipos à mão (ver dívida abaixo) |
| Erros da API legíveis (`readProblem()` único) | não auditado nesta rodada | — | — |
| Router com erro e pendência por rota | **ok, parcial** | `RouteErrorBoundary` em `src/App.tsx`: a fronteira fica dentro do `BrowserRouter` e se rearma a cada navegação; `CarregandoRota` é o `Suspense` fallback | o shell não é preservado quando uma tela quebra (a fronteira envolve o `Routes` inteiro), e o `errorElement` do react-router não se aplica ao modo declarativo usado aqui |
| Cobertura de frontend ≥ 60% | **gap** | piso mantido em 53% (medido: 54,96% statements, 54,96% linhas, 76,28% branches, 52,32% funções) | subir o piso para 60% exige ~5 pontos de testes; o piso não sobe nesta rodada |
| TanStack Query: defaults | ok | `retry: 1`, `staleTime: 30_000` em `src/App.tsx`; o padrão não fixa números | — |
| Métricas de campo (`web-vitals`) | gap | não instalado | rota que receba as métricas; é o gap nº 1 do padrão |
| Bundle sob o teto | ok | 141,9 KB de 250 KB | — |

## Typecheck e lint

- `npx tsc -b`: ok (o `tsconfig.app.json` agora inclui `generated/`).
- `npx eslint .`: 0 erros, 18 avisos. Todos são `react-refresh/only-export-components`, que é aviso
  por decisão do projeto (`warn`). Ficam como dívida visível; não foram tratados aqui porque tocam
  componentes que outras frentes estão mexendo.
- `npx prettier --check .`: ok.

## Testes

- `npx vitest run`: 127 arquivos, 358 testes, todos passam (inclui o novo `ErrorBoundary.test.tsx`).
- Cobertura: 54,96% statements; piso de 53% passa.

## Mudanças nesta rodada

- `frontend/eslint.config.js`: regras acima, com listas `DEBT_*` por arquivo.
- `frontend/scripts/check-bundle.mjs`: teto de 250 KB sobre o que o `index.html` carrega.
- `frontend/package.json`: script `bundle` (build + gate) e `types:api`; dependência
  `openapi-typescript`.
- `frontend/generated/api-schema.ts`: tipos gerados. Fora de `src/` de propósito: arquivo de 26 mil
  linhas de tipos no `src/` derrubava a cobertura de 55% para 28% (o v8 conta as linhas do arquivo
  como não cobertas). `tsconfig.app.json` o inclui na checagem de tipos.
- `frontend/src/components/ErrorBoundary.tsx` e `.test.tsx`: `RouteErrorBoundary`.
- `frontend/src/App.tsx`: envolve o `Suspense`/`Routes` com `RouteErrorBoundary`.
- `frontend/.prettierignore`: o arquivo gerado.
- `Makefile`: `api-types`, `api-types-check`, `bundle`.
- `backend/tools/openapi.py`: `REDIS_URL` placeholder. Sem ele `make openapi` quebrava por
  `redis_url` obrigatório, e o alvo que gera o contrato não rodava.

## Dívida

1. 52 arquivos com função acima de 100 linhas (`DEBT_FUNCTION_SIZE`).
2. 8 arquivos acima de 300 linhas (`DEBT_FILE_SIZE`).
3. 33 arquivos com `toLocale*` fora de `src/lib` (`DEBT_FORMATTING`).
4. 6 arquivos com `keydown` fora de um hook (`DEBT_KEYBOARD`).
5. 1 arquivo de `components/domain` importando feature (`DEBT_LAYER`).
6. Cliente da API (`src/features/*/api.ts`) não usa o tipo gerado. Migrar é trabalho por feature,
   não desta rodada.
7. Cobertura 53% contra o padrão de 60%.
8. Import entre features sem regra.
9. Sem `expectOneDocument()` nos testes de tela.
10. Sem `web-vitals`.
11. Shell não preservado quando uma tela quebra.
12. 18 avisos de `react-refresh/only-export-components`.

Os baselines valem para arquivo, não para função: um arquivo na lista fica isento das regras de
tamanho inteiro, inclusive para funções novas. Ao corrigir um arquivo, tire-o da lista.

## CI (não alterado nesta rodada)

`.github/workflows/ci.yml` é de outra frente. Passos a adicionar:

- depois de `make lint`, ou dentro do job de frontend: `make api-types-check`, que falha se
  `frontend/generated/api-schema.ts` não bate com o `openapi.json` do commit;
- no lugar do `npm run bundle:check` atual: `make bundle` (já faz o build e o gate).
