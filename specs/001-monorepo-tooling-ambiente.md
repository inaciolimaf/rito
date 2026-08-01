# 001 — Monorepo, tooling e ambiente

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +0 s
**Depende de:** — · **Status:** ✅ concluída

---

## 1. Objetivo

Um desenvolvedor clona o repositório e, com dois comandos, tem Postgres, Redis, backend e
frontend rodando. Nenhuma feature ainda — só o chão.

## 2. Escopo

- Estrutura `backend/`, `frontend/`, `e2e/`, `specs/`, `docs/`
- `docker-compose.yml`: Postgres 16, Redis 7, MinIO (storage S3-compatible em dev)
- `Makefile` com todos os alvos do `CLAUDE.md`
- `.env.example` documentando cada variável
- `pyproject.toml` (ruff, black, mypy strict, pytest) e `package.json` (eslint, prettier, tsc)
- `.pre-commit-config.yaml`
- `.gitignore`

## 3. Fora de escopo

- Qualquer endpoint ou tela → 002 e 006
- CI no GitHub Actions → 009

## 4. Modelo de dados

Nenhum. Só o container do Postgres com database `rito` e `rito_test`.

## 5. Contratos de API

Nenhum.

## 6. Front-end

Só o scaffold do Vite, sem rotas. Tela em branco que renderiza.

## 7. Regras de negócio

1. `make up` sobe Postgres, Redis e MinIO com healthcheck e volumes nomeados.
2. `make dev` sobe backend e frontend concorrentes, com reload.
3. Nenhum segredo versionado. `.env` está no `.gitignore`; `.env.example` tem placeholders.
4. `mypy` em modo `strict`. `tsconfig` com `strict: true` e `noUncheckedIndexedAccess`.
5. Variáveis obrigatórias documentadas: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`,
   `OPENROUTER_API_KEY`, `DATAJUD_API_KEY`, `S3_*`.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| smoke | `pytest` coleta 0 testes sem erro de import | `backend/tests/test_smoke.py` | ~0,1 s |
| smoke | Vitest roda e passa | `frontend/src/smoke.test.ts` | ~0,2 s |

**Total estimado:** ~0,3 s

## 9. Descobertas

- `make migrate` e `make dev` estão com os alvos corretos no `Makefile`, mas só executam de
  fato a partir da 002 (esqueleto do backend/FastAPI) e da 006 (esqueleto do frontend/Vite
  real) — hoje `backend/app` é um pacote vazio e `frontend/src` só renderiza uma tela em
  branco. `make up` já foi validado de ponta a ponta nesta máquina.
- O `.env.example` e o `.gitignore` já existiam completos no repositório antes deste ciclo
  (commit anterior) — só foram conferidos contra o escopo da spec, não recriados.
- Descartada a abordagem de criar `rito_test` via script SQL montado em
  `docker-entrypoint-initdb.d` (bind mount de arquivo): neste ambiente de execução o daemon
  Docker não enxerga corretamente arquivos recém-criados montados individualmente — eles
  aparecem como diretórios vazios para o daemon, mesmo existindo e tendo conteúdo do lado do
  host. Como isso quebraria `make up` de forma silenciosa e é uma causa raiz de
  infraestrutura (não de código), o `Makefile` cria `rito_test` via
  `docker compose exec ... psql` logo após o `up`, checando idempotência antes de criar. Essa
  abordagem é mais robusta e não depende de bind mount de arquivo — mantida mesmo fora deste
  ambiente específico.
- `react-router-dom` ficou fixado em `^7.18.2` (não `8.x`) porque a major 8 exige
  `react >=19.2.7`, e o `CLAUDE.md` fixa React 18 sem spec explícita autorizando o upgrade.
  O `npm audit` acusa uma vulnerabilidade alta (GHSA-qwww-vcr4-c8h2) na faixa 7.12–8.2, mas ela
  é restrita ao **modo RSC** (React Server Components) — este projeto é uma SPA client-side
  via Vite, sem RSC, então o vetor não se aplica. Reavaliar quando o projeto migrar para
  React 19 (spec explícita necessária) ou quando sair um patch 7.x.
- Nenhum endpoint, tela ou migration foi criado — confirma o "fora de escopo" da spec.

## 10. Definição de pronto

- [x] `make up` sobe Postgres, Redis e MinIO com healthcheck, e cria `rito_test`
      idempotentemente (validado nesta máquina). `make migrate`/`make dev` ficam prontos para
      as specs 002/006, que fornecem o código que essas tasks executam.
- [x] `make lint` verde (ruff, black --check, mypy strict no backend; eslint, tsc, prettier
      --check no frontend)
- [x] `.env` ignorado, `.env.example` completo com todas as variáveis do `CLAUDE.md`
- [x] `ROADMAP.md` → ✅
- [x] Commit `feat(001): monorepo, tooling e ambiente`
