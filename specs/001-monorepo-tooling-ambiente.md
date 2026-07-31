# 001 — Monorepo, tooling e ambiente

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +0 s
**Depende de:** — · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

- [ ] `make up && make migrate && make dev` funciona em máquina limpa
- [ ] `make lint` verde
- [ ] `.env` ignorado, `.env.example` completo
- [ ] `ROADMAP.md` → ✅
- [ ] Commit `feat(001): monorepo, tooling e ambiente`
