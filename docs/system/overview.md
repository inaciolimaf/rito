# Visão geral do sistema

O Rito é um sistema de gestão jurídica multi-tenant: cada escritório é um tenant, e os dados de
um nunca aparecem para outro. O backend é um monólito modular em FastAPI, o frontend é uma SPA
React, e o estado vive no PostgreSQL. A forma completa, com diagramas, está em
`docs/ARQUITETURA.md`; este arquivo diz onde cada coisa mora e os caminhos que o gate verifica.

## Processos e portas

| Processo | Onde | Papel |
|---|---|---|
| API | `backend/app/main.py` (`create_app`) | HTTP: rotas em `/api/v1`, API pública em `/api/public/v1`, saúde em `/health` e `/health/ready` |
| Worker | `backend/app/workers/` (Celery) | Tudo que chama o mundo externo (DJEN, DataJud, LLM, SMTP, webhooks) sai daqui |
| Beat | `backend/app/workers/` (Celery beat) | Agendamentos: sincronizações e varreduras |
| Frontend | `frontend/src/` (Vite, React) | SPA; chamadas relativas a `/api/v1` |
| Identidade visual | `frontend/src/index.css`, `tailwind.config.ts` | tokens e movimento reduzido; ver `docs/frontend-identity.md` |
| CLI | `backend/app/cli.py` (`rito`) | Operação: migrações, seed, tenants, backup, health |

## Camadas do backend

```
router      só HTTP: recebe, valida o schema, chama o serviço, devolve. Um select() aqui é bug.
service     a regra. Não sabe o que é HTTP nem como o dado é guardado.
repository  só query. Não decide nada.
integração  atrás de interface (LLMProvider, FileStorage, PublicationSource, WebhookSender).
```

Os domínios ficam em `backend/app/domain/<domínio>/` (lista no índice `docs/system/README.md`).
`backend/app/core/` é o que todo domínio usa e não tem domínio próprio. `backend/app/integrations/`
é o que fala com fora. A regra de camadas é verificada em duas frentes:

- `import-linter` (`[tool.importlinter]` em `backend/pyproject.toml`, parte de `make lint`):
  `app.core` não importa domínio, IA, API pública, workers ou integrações; `app.integrations` não
  importa domínio. Os pares que ainda violam estão listados em `ignore_imports` como dívida.
- `backend/tests/meta/test_camadas.py`: três propriedades por AST (router sem query, router sem
  repository, regra sem I/O).

## Isolamento entre escritórios

O isolamento é feito pelo Postgres, não pelo `WHERE`:

1. toda tabela de domínio tem `tenant_id NOT NULL`;
2. RLS ligado e forçado, com política sobre `current_setting('app.tenant_id')` (`backend/app/core/rls.py`);
3. a sessão seta `app.tenant_id` no início de cada request ou tarefa (`backend/app/core/db.py`);
4. a aplicação usa a role `rito_app`, sem `BYPASSRLS`.

As exceções (parceria entre escritórios, biblioteca pública de modelos, catálogos globais sem
`tenant_id`) estão documentadas em `docs/SEGURANCA-RLS.md`.

## Configuração

- Uma única fonte: `backend/app/core/config.py` (`Settings`, lida do ambiente e do `.env`).
- Segredos sem valor padrão. Em produção o processo recusa segredo ausente, curto ou igual ao
  exemplo de `.env.example`.
- Variáveis configuradas no servidor **não são renomeadas**. Quando o nome do campo muda, a
  variável antiga é lida por alias (ver `CLAUDE.md`, seção Idioma).

## Erros e log

- Um formato só de erro: `application/problem+json` (RFC 9457), em `backend/app/core/errors.py`.
  `detail` é texto do produto, na língua do produto; `type` é código em inglês.
- Log estruturado em JSON em produção (`backend/app/core/logging.py`), com `request_id` propagado
  até o worker. Redação de PII e métricas em `backend/app/core/observability/`.

## Banco e migrações

- PostgreSQL 16, SQLAlchemy 2.0 assíncrono, migrações Alembic em `backend/alembic/`.
- Em produção `RUN_MIGRATIONS_ON_BOOT` aplica as migrações ao subir a API (o worker não aplica).
- Cada teste roda numa transação com rollback; um banco-modelo é criado uma vez por sessão
  (`backend/tests/conftest.py`).

## IA

Uma única saída de LLM: OpenRouter, em `backend/app/integrations/openrouter/`. Orquestração com
LangGraph em `backend/app/ai/`. Sem RAG: o contexto vem de ferramentas tipadas que respeitam RLS e
RBAC. Escrita sempre passa por preview e confirmação humana. Nenhum teste chama modelo real.

## Testes e gates

| Gate | Onde está | Falha quando |
|---|---|---|
| Lint e tipos | `make lint`: ruff, black, mypy strict (`warn_unreachable`), import-linter, eslint, tsc, prettier | qualquer um vermelho |
| Tamanho | `backend/tools/function_size.py` (`make lint`) e `backend/tests/meta/test_tamanho_de_funcao.py` | função > 30 linhas úteis (com exceções versionadas) ou arquivo > 300 (com lista temporária) |
| Documentação | `backend/tools/docs_coverage.py` (`make docs`) | pasta de domínio sem citação em `docs/system/` ou caminho citado que sumiu |
| Testes | `make test`, orçamento de 300 s | suíte vermelha ou wall-clock acima do teto |
| CI | `.github/workflows/ci.yml`: jobs `check`, `back`, `web`, `e2e` (duas fatias) e `image` em paralelo, todos chamando `make`; job `gate` (`make ci-gate`) | qualquer job vermelho ou cancelado, ou o run inteiro acima de 300 s desde o início (fila incluída) |
| Build e bundle | `make build` (job `check`) | build quebrado ou bundle acima do orçamento |
| Duplicação e auditoria | `make dup` (jscpd) e `make audit` (pip-audit, npm audit) no job `check` | duplicação acima do teto de `.jscpd.json`, ou dependência com vulnerabilidade alta |
| Imagem de produção | `make docker-image` e `make image-smoke` (job `image`) | imagem roda como root, tem gcc, ou `rito health` reprova em modo produção |
| Cobertura | `backend/pyproject.toml` `fail_under` (`make coverage-backend`) e `frontend/vite.config.ts` (`make coverage-frontend`), jobs `back` e `web` | medição abaixo do piso |
| Registro | `docs/GATES.md`, `backend/tests/meta/test_registro_de_gates.py` | gate existe e não está listado |

Os gates e seus tetos estão no registro `docs/GATES.md`. Teto só desce.

## Onde ler mais

- `CLAUDE.md`: como construir (stack, regras, comandos).
- `docs/ARQUITETURA.md`: diagrama e decisões de forma.
- `docs/DECISOES.md`: o porquê de cada decisão.
- `docs/RUNBOOK.md`: operar em produção.
- `specs/`: o que foi pedido, spec por spec.
