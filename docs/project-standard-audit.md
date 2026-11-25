# Auditoria contra o padrão `project-standard`

Data: 2026-11-25. Branch: `chore/project-standard`. Escopo: só o padrão `project-standard`
(backend, Makefile, CI, Docker, documentação, idioma). Os padrões `frontend-standard`,
`test-speed` e `mutation-testing` ficam para depois; o que eles pedem aparece aqui apenas como
item do checklist, marcado como "fora do escopo" ou "frontend-standard".

**Legenda de status**: `ok` = atende ao padrão (a verificação é um gate ou o código atende);
`partial` = existe, mas diverge ou só cobre uma parte; `missing` = não existe.
**"O que fazer"** diz o que foi aplicado nesta rodada (`aplicado`) ou o que ficou como dívida
(`dívida`), com o motivo.

## 1. Idioma

| Regra | Status | O que fazer |
|---|---|---|
| Código, identificadores, tabelas, rotas e tipos de erro em inglês | ok | Gate já existe: `backend/tests/meta/test_nomes_em_ingles.py`. |
| Comentários e docstrings em inglês | missing | dívida: cerca de 370 arquivos do backend têm docstring e a maior parte está em português. Traduzir é reescrita em massa; fica para um ciclo próprio. Código novo e tocado sai em inglês (regra escrita em `CLAUDE.md` §14). |
| Documentação (`docs/`, specs, `CLAUDE.md`) em inglês | partial | conflito com `CLAUDE.md` (ver seção 6). `docs/system/` e o `CLAUDE.md` novo foram escritos em português, como o resto de `docs/`. |
| `docs/glossary.md` mapeia termo do produto → nome no código | missing → ok | aplicado: `docs/glossary.md` com convenções de nome, o que fica em português e 40 termos. Precisa de revisão do dono do produto. |
| Variáveis do servidor, comandos e alvos do Makefile preservados | ok | Nenhum nome foi alterado. Só foram acrescentados alvos (`help`, `docs`, `coverage`, `types`, `openapi`). |

## 2. Python: ferramentas e configuração

| Regra | Status | O que fazer |
|---|---|---|
| `uv` + `pyproject.toml` com `[dependency-groups] dev`, `uv.lock`, Python fixado | ok | `.python-version` = 3.12, `uv.lock` versionado. |
| ruff com o conjunto de regras do padrão | partial | O projeto já usa outro conjunto (E, F, I, UP, B, SIM, RET, PTH, ERA, TID, ICN, ASYNC, DTZ, C90, PLR, RUF100, S). Faltam N, A, C4, RUF amplo e ANN. Ligar ANN exigiria anotar milhares de funções: dívida. Mantido o conjunto atual, que é mais restrito em alguns pontos. |
| `line-length = 110` | partial | Conflito: o projeto usa 100 (todo o código está formatado assim). Mantido. Ver seção 6. |
| `ruff format --check` em CI | partial | O projeto usa `black --check` (mesma saída, já no lint e no CI). Mantido, para não reformatar o repositório à toa. Ver seção 6. |
| mypy `strict = true`, `warn_unreachable`, plugin pydantic | ok | `warn_unreachable` aplicado. Foram duas ocorrências, ambas em `tests/integration/` (`yield` inalcançável que torna o `stream` um gerador): anotadas com `# type: ignore[unreachable]` e motivo no comentário. |
| `tools/function_size.py`: 30 linhas úteis por função | ok | Gate já existe por meta-teste: `backend/tests/meta/test_tamanho_de_funcao.py` (com exceções versionadas, `EXCECOES`). Não foi duplicado. |
| `tools/function_size.py`: 300 linhas úteis por arquivo | missing → partial | aplicado: `backend/tools/function_size.py` com `[tool.function-size]` e `make lint`. Dívida: **28 arquivos** acima de 300 linhas, listados em `ignore-file-temporarily` (ex.: `app/domain/lawsuits/router.py` com 924). Cada um sai da lista quando for dividido por responsabilidade. |
| Duas funções acima de 30 linhas que o padrão reprovaria | partial | `customers/router.py::_customer_to_response` (42) e `posts/router.py::_to_response` (40): mapeadores puros, com exceção versionada no meta-teste. O arquivo de `posts/router.py` também sai do cálculo de tamanho de arquivo (`ignore`). Dívida: dividir ou aceitar, com a exceção registrada. |
| Módulos monolíticos: `api/modules/<domínio>` com interface pública em `__init__.py` | partial | O projeto usa `backend/app/domain/<domínio>/`, com `router`, `service`, `repository` e `models` por pasta. Sem `__init__.py` de interface pública na maioria dos domínios. Dívida: reestruturar é mudança grande, que o próprio padrão manda fazer em ondas (ver `structure.md`). |
| `import-linter` em `make lint` com contratos de camada | missing → partial | aplicado: `[tool.importlinter]` com dois contratos `forbidden` (`app.core` não importa camadas de cima; `app.integrations` não importa domínio), `make lint` e 22 pares de import existentes em `ignore_imports` como dívida. Um contrato de `layers` completo quebra com 110 pares: não foi usado. |
| Eventos entre módulos (sem import de domínio para domínio) | missing | dívida: não existe barramento de eventos (`core/events.py`). Hoje os módulos se chamam diretamente. Não é coberto por gate. |
| Unit of work: só a dependência de sessão faz `commit` | partial | Há 9 `commit()` fora de `app/core/db.py` (serviços, workers, `integration_alerts`, `auth`, `ai`). Dívida: um teste de arquitetura (AST) com lista temporária, como o padrão descreve. |
| `get_owned` para registro de usuário | missing | dívida: o isolamento do projeto é por tenant (RLS), não por dono do registro. Decidir se `get_owned` cabe aqui (provavelmente só para registros de usuário, como sessão e token de API). |
| Nada bloqueia o event loop: `ASYNC` ligado, sem sessão síncrona | ok | `ASYNC` está em `select`; não há `sqlalchemy.orm.Session` em `app/`. |
| Nenhuma espera sem prazo: `timeout` em HTTP, `lock_timeout`, `statement_timeout`, `idle_in_transaction_session_timeout` na conexão | partial | `S113` (request sem timeout) ligado via `S`. Não há `connect_args` de timeout no engine. Há `SET LOCAL statement_timeout` em `app/domain/ai/analytics.py` feito com `text()`. Dívida: antes de ligar os limites, auditar o que eles matariam (o padrão lista o procedimento em `runtime.md`). |
| SQL só pelo query builder (sem `text()` nem string SQL) | partial | Gate: `backend/tests/meta/test_sql_em_string.py` (com lista de exceções). `text()` ainda existe em alguns pontos listados lá. Mantido. |
| Módulo: raiz só com arquivos de contrato, no máximo 8 arquivos por pasta | missing | dívida: 11 pastas com mais de 8 arquivos `.py` (a maior, `app/domain/ai`, tem 21). Não há gate. |
| Login com limite de tentativas (429 + `Retry-After`) | ok | 429 em `backend/app/domain/auth/router.py` e limitador em `backend/app/core/rate_limit.py`. `Retry-After` tratado pelo tratador de erros (`backend/app/core/errors.py`). |
| Logout revoga a sessão no servidor; troca de senha e desativação encerram tudo | partial | Logout revoga o refresh token (`backend/app/domain/auth/service.py`). Access token segue válido até expirar. Não há versão de sessão nem `sid`. Dívida: ver `auth` no padrão (`runtime.md`). |
| Comentários: só docstring de módulo com decisão, sem separadores | partial | 28 arquivos do backend têm separadores (`# ---`, `# ===`). Dívida: remover, mecânico mas grande. |
| Cobertura: `fail_under` em `pyproject.toml`, `pytest --cov` no CI, alvo no Makefile | ok | `fail_under = 83` (medido: 89.25% em 2026-11-25); CI com passo próprio; alvo `make coverage` aplicado. |
| pytest com `asyncio_mode = "auto"` e `DeprecationWarning` do projeto como erro | ok | aplicado: `filterwarnings = ["error::DeprecationWarning:app.*"]`. A suíte continua verde (1970 testes). |
| `tests/unit/`, `tests/integration/` (marcador `integration`), `tests/golden/` | partial | `unit` e `integration` existem, sem o marcador `integration` (o `make test` não separa). Dívida: marcador e um alvo de teste só-unitário; `golden` não existe (são casos reais gravados). |
| Isolamento do ambiente por fixture autouse (nenhum teste lê o `.env`) | partial | `tests/conftest.py` define `APP_ENV`, `SECRET_KEY` e o banco de teste em `pytest_configure`; `env_file` não é desligado de forma explícita. Dívida: fixture `autouse` no conftest raiz que limpa as variáveis do `Settings`. |
| URL de banco de teste por variável, ou `skip` com motivo | ok | `TEST_DATABASE_URL` e `TEST_MIGRATIONS_DATABASE_URL`. |
| Uma transação por teste com rollback | ok | `tests/meta/test_isolamento_transacional.py`, banco-modelo por sessão em `tests/conftest.py`. |
| LLM e serviço externo com implementação fake determinística | ok | `ScriptedProvider` nos testes, `pytest-socket` bloqueia rede (`tests/meta/test_no_network.py`). |

## 3. Frontend (fora do escopo; registrado para o `frontend-standard`)

| Regra | Status | O que fazer |
|---|---|---|
| Vite + React + TS `strict`, `noUnusedLocals/Parameters`, `noFallthroughCasesInSwitch` | ok | `frontend/tsconfig.app.json`. |
| eslint flat com `js`, `typescript-eslint`, `react-hooks` com `exhaustive-deps: error` | partial | Falta `exhaustive-deps` como erro (hoje aviso). Regras próprias existem em `frontend/eslint-rules/`. Frontend-standard. |
| `max-lines-per-function` 100, `max-lines` 300, regras de reuso (cor, número, sombra, teclado) | missing | frontend-standard. |
| prettier + `eslint-config-prettier` | partial | Prettier ok; `eslint-config-prettier` não está instalado. frontend-standard. |
| `QueryView`, `Card`, `Button`, `formatting.ts`, `useShortcuts`, `palettes.ts` | partial | Há parte dos componentes; estrutura `features/<ctx>/` em vez de `modules/<domínio>/`. frontend-standard. |
| Router com `defaultErrorComponent` e `defaultPendingComponent` | missing | frontend-standard. |
| Tipos da API gerados do OpenAPI (`openapi-typescript`) | missing | O backend já gera `backend/openapi.json` (`make openapi`), mas o frontend não gera tipos a partir dele (`src/lib/domainEnums.generated.ts` é o único gerado). Próximo passo: frontend-standard. |
| Vitest + Testing Library, cobertura ≥ 60% | partial | Vitest ok (357 testes). Limite atual em `frontend/vite.config.ts` é 53% (linhas e statements). Conflito: padrão 60%. Ver seção 6. |
| Playwright com fluxos e smoke das rotas | partial | `e2e/` com 11 jornadas (teto 25). Uma falha pré-existente: `navigation.spec.ts` jornada 2 (ver seção 5). |
| `*.tsbuildinfo` e `coverage/` no `.gitignore` | ok | `coverage/` adicionado nesta rodada. |

## 4. Infraestrutura

| Regra | Status | O que fazer |
|---|---|---|
| `docker-compose.yml` local com portas no host e healthchecks | ok | `docker-compose.yml`: Postgres, Redis e MinIO com healthcheck. |
| Compose de produção para o PaaS (`docker-compose-coolify.yml` com `expose`, `:?`, `restart`, `start_period`) | partial | Existe `docker-compose.prod.yml` (nome diferente, publica a porta da API com `ports`, usa `${VAR:-default}` em alguns pontos). Dívida: adaptar ao checklist de `coolify.md`, com cuidado para não renomear variável já configurada no servidor. |
| Dockerfile do backend com camada de dependências separada (`uv sync --no-install-project`) | ok | `backend/Dockerfile`, multi-stage, usuário não-root, healthcheck em `/health`. uv fixado em 0.5. |
| Dockerfile do frontend multi-stage servido por proxy com `/api` | partial | Multi-stage ok, usa nginx (`frontend/nginx.conf`) em vez de Caddy. Conflito com o padrão (ver seção 6). |
| Healthcheck em todo serviço, `depends_on: condition: service_healthy` | partial | Healthcheck em postgres, redis, minio e API. Worker e beat não têm. Dívida. |
| Entrypoint que aplica migrações quando a variável manda | partial | A migração no boot é feita pela aplicação (`RUN_MIGRATIONS_ON_BOOT`), sem `entrypoint-*.sh`. Funciona; diferente do padrão, mantido. |
| `.env.example` comentado por seção; `.env*` no `.gitignore` e no `.dockerignore` | ok | `.gitignore` corrigido nesta rodada: antes só ignorava `.env` e `.env.local`; agora `.env.*` com `!.env.example` e `!.env.production.example`. |
| `.dockerignore` | missing → ok | aplicado: `backend/.dockerignore` e `frontend/.dockerignore` (os contextos são `backend/` e `frontend/`; o padrão previa um na raiz). |
| `make` com `help` como alvo padrão | missing → ok | aplicado: `help` com descrição em todos os alvos e `.DEFAULT_GOAL := help`. **Mudança de comportamento:** `make` sozinho antes rodava `up`; agora lista os comandos. Para subir os serviços, usar `make up`. |
| CI com jobs `check`, `back`, `web`, `e2e` e `gate` com 180 s | partial | CI tem um job `test` (30 min de teto) com `make lint`, `make docs` (aplicado), `make test` (300 s, o teto do `CLAUDE.md`), build, cobertura, auditoria e build da imagem. Dívida: dividir em jobs (test-speed) e decidir o teto (ver seção 6). |
| Todo passo do CI tem alvo no Makefile | partial | `lint`, `docs`, `test` e `coverage` têm alvo. Build do frontend, `dup:check`, `bundle:check`, auditoria de dependências e build da imagem não têm. Dívida: criar alvos com os mesmos comandos. |
| `make docs` no CI, depois do lint | ok | aplicado: passo `make docs` em `.github/workflows/ci.yml`. |
| Mutação nos métodos alterados | partial | Fora do escopo (`mutation-testing`). Existe `make test-mutation` (spec 132). |

## 5. Documentação

| Regra | Status | O que fazer |
|---|---|---|
| `CLAUDE.md` com as seções "Documentação — leia primeiro" e "Idioma" | missing → ok | aplicado: seções 13 e 14 em `CLAUDE.md` (em português, como o resto do arquivo). Comandos novos na seção 10. |
| `docs/system/README.md` com índice e um arquivo por domínio | partial | aplicado: `docs/system/README.md` (índice com as 52 pastas que o gate exige, e o formato do arquivo de domínio) e `docs/system/overview.md`. Dívida: 52 arquivos de domínio; o índice marca todos como `pendente`. |
| `tools/docs_coverage.py` + `make docs` + passo de CI | missing → ok | aplicado: `backend/tools/docs_coverage.py` (raiz do repositório; `[tool.docs-coverage]` em `backend/pyproject.toml`), alvo `make docs`, passo no CI. DOC001 passa porque o índice cita cada pasta; DOC002 verifica os caminhos citados. |
| `README.md`: o que é, mapa de pastas, como rodar, deploy | partial | Há o que é, estado, produto, stack, testes e "Começando". Faltam o mapa de pastas (apontar para `docs/system/overview.md`) e o link de deploy. Dívida: revisão do README, fora deste escopo. |
| Specs numeradas `NN-nome.md` com tabela no README | partial | Specs existem em `specs/NNN-slug.md` (três dígitos, 000 a 139). Não há tabela de specs no README. Conflito de numeração (ver seção 6). Dívida: a tabela. |
| `docs/deploy-<paas>.md` passo a passo | missing | dívida: existe `docs/RUNBOOK.md`, que cobre a operação. Escrever o passo a passo do PaaS quando o alvo de deploy for escolhido. |
| Padrão de registro de gates (`docs/GATES.md`, consultado por meta-teste) | ok | Registro atualizado com import-linter, tamanho de arquivo e `make docs`. |

## 6. Conflitos com o `CLAUDE.md` (o `CLAUDE.md` prevalece)

| Ponto | Padrão | `CLAUDE.md` / projeto | Decisão |
|---|---|---|---|
| Orçamento de `make test` | 180 s | 300 s (§3, gate, não aviso) | Mantido 300 s. O padrão é mais estrito, mas o custo de reduzir é o do `test-speed`, fora deste escopo. |
| Idioma da documentação | inglês | português (§9 e §14 novo) | Mantido português em `docs/system/`, glossário e `CLAUDE.md`. |
| Largura de linha | 110 | 100 (`ruff`, `black`) | Mantido 100. Mudar reformataria o repositório inteiro. |
| Formatador | `ruff format` | `black` | Mantido `black` (mesma saída, já no lint e no CI). |
| Nome dos comandos | inglês (`docs`, `types`) | português (`test`, `lint`, `up`) | Mantidos os nomes existentes. Novos alvos em inglês, como o padrão manda. |
| Cobertura do frontend | 60% | sem número no `CLAUDE.md`; limite atual 53% | Mantido 53% (medido). Subir é trabalho do `frontend-standard`. |
| Nome do arquivo de compose de produção | `docker-compose-<paas>.yml` | `docker-compose.prod.yml` (`RUNBOOK.md` o cita) | Mantido; renomear afeta documentação e operação. |
| Proxy do frontend | Caddy | nginx (`ARQUITETURA.md`) | Mantido nginx. |
| Numeração das specs | `NN-nome.md` | `NNN-slug.md` (spec 100, 139 citadas em código e teste) | Mantido. Renumerar quebra referências no código e nos testes. |
| Estrutura de pastas | `api/modules/<domínio>` | `backend/app/domain/<domínio>` | Mantido; ver a linha de módulos na seção 2. |
| Regra de bloqueio do event loop e de sessão síncrona | sem sessão síncrona | igual | Sem conflito. |
| Língua dos comentários | inglês | `CLAUDE.md` §9 pede código em inglês; comentários estão em português | Dívida (seção 2). |

## 7. Dívida (resumo para o dono do projeto)

Ordem sugerida, do que mais protege para o que é só estético:

1. **Sem gate ainda**: unidade de trabalho (9 `commit()` fora de `db.py`), limite de 8 arquivos por pasta,
   separadores de comentário (28 arquivos), idioma dos comentários.
2. **Arquivos grandes**: 28 arquivos acima de 300 linhas úteis (lista em `[tool.function-size]`). Cada
   um sai da lista quando for dividido.
3. **Fronteiras**: 22 pares em `ignore_imports` do `import-linter`; eventos entre módulos não existem.
4. **Documentação**: 52 arquivos de domínio em `docs/system/` (hoje `pendente`); `deploy-<paas>.md`;
   tabela de specs no README.
5. **Tempos e esperas**: timeouts de conexão (`lock_timeout` etc.) e `SET LOCAL statement_timeout` com `text()`.
6. **Testes**: marcador `integration`, alvo só-unitário, fixture autouse de ambiente, `golden/`.
7. **CI**: dividir em jobs e alvos para cada passo (test-speed); definir o teto.
8. **Compose de produção**: checklist de `coolify.md`.
9. **Autenticação**: versão de sessão e encerramento de sessões na troca de senha.
10. **Frontend**: tudo da seção 3 (frontend-standard).

## 8. Verificação desta rodada

Resultados obtidos em 2026-11-25 nesta máquina (Postgres, Redis e MinIO via `make up`, Chromium do
Playwright instalado com `npx playwright install chromium`):

- `make lint`: **verde** (exit 0): ruff, black, mypy (com `warn_unreachable`, 680 arquivos), tamanho de função
  e arquivo (com a lista temporária), `lint-imports` (2 contratos, 2 kept), eslint (0 erros, 18 avisos já
  existentes), tsc, prettier.
- `make docs`: **verde** (exit 0).
- `make test`: backend **1970 passed**, frontend **357 passed**, e2e **10 passed, 1 failed**. Wall-clock
  149 s (orçamento 300 s). Exit 2 por causa do único teste e2e que falha:
  `tests/navigation.spec.ts` jornada 2, sidebar leva a `/posts` e o teste espera `/home`. **Esta falha existe
  também no commit base** (verificado com `git stash` e uma execução de `make test` sobre a árvore original:
  mesmo teste, mesma mensagem). Não foi corrigida: é comportamento do frontend, fora do escopo.
- `make coverage`: **verde**, 89.25% (piso 83%).
- `pytest tests/meta`: 155 passed.
- `make help`: lista os 21 alvos.
- `make openapi`: gera `backend/openapi.json` (ignorado pelo git).

## 9. Arquivos alterados nesta rodada

- `backend/pyproject.toml`: `warn_unreachable`, `[tool.importlinter]`, `[tool.function-size]`,
  `[tool.docs-coverage]`, `filterwarnings`, dependência `import-linter`.
- `backend/uv.lock`: dependência `import-linter`.
- `backend/tools/function_size.py`, `backend/tools/docs_coverage.py` (raiz do repositório, adaptado), `backend/tools/openapi.py` (adaptado para `app.main`).
- `backend/tests/integration/test_ai_editor.py`, `backend/tests/integration/test_ai_runtime_timeout.py`: `# type: ignore[unreachable]` com motivo.
- `backend/.dockerignore`, `frontend/.dockerignore`.
- `.gitignore`: `.env.*` com exceções, `coverage/`, `openapi.json`.
- `Makefile`: `help` (padrão), descrições, `lint` com tamanho e fronteiras, `docs`, `coverage`, `types`, `openapi`.
- `.github/workflows/ci.yml`: passo `make docs`.
- `.pre-commit-config.yaml`: hook de tamanho.
- `CLAUDE.md`: comandos e seções 13 (Documentação) e 14 (Idioma).
- `docs/system/README.md`, `docs/system/overview.md`, `docs/glossary.md`, `docs/GATES.md` (três gates registrados), `docs/project-standard-audit.md` (este arquivo).
