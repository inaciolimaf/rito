# Rito — Constituição de Engenharia

> **Todo processo tem um rito. O seu escritório também.**
>
> Este arquivo é lido a cada ciclo do `/loop`. É a fonte de verdade sobre **como** construir.
> O `ROADMAP.md` define **o que** construir. As specs em `specs/` definem **o detalhe**.

---

## 1. O que é o Rito

Sistema de gestão jurídica para escritórios de advocacia brasileiros — SaaS multi-tenant.
Referência funcional: `docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` (levantamento completo do ADVBOX,
incluindo campos de formulário, taxonomias e regras de negócio reais).

**Escopo:** paridade quase total com o ADVBOX + camada de IA densa.

---

## 2. Stack — não desvie sem spec explícita

### Backend
| Item | Escolha |
|---|---|
| Linguagem | Python 3.12 |
| Framework | FastAPI |
| ORM | SQLAlchemy 2.0 (async, `Mapped`/`mapped_column`) |
| Migrations | Alembic |
| Banco | PostgreSQL 16 |
| Fila/cache | Redis + Celery (beat para sync agendada) |
| Validação | Pydantic v2 |
| Testes | pytest, pytest-asyncio, pytest-xdist |

### Frontend
| Item | Escolha |
|---|---|
| Build | Vite |
| Framework | React 18 + TypeScript (strict) |
| Estilo | Tailwind CSS |
| Componentes base | shadcn/ui |
| Data fetching | TanStack Query |
| Roteamento | React Router |
| Formulários | React Hook Form + Zod |
| Testes | Vitest + Testing Library |

### IA
| Item | Escolha |
|---|---|
| Gateway | **OpenRouter** — sempre. Nunca chame provider direto. |
| Orquestração | **LangGraph** |
| Padrão | **Tool calling.** **RAG é proibido** — sem vector store, sem pgvector, sem embeddings. |
| Modelo | **Selecionável pelo usuário** por feature. Nunca hardcode um modelo. |
| Streaming | SSE |

### E2E
Playwright, sharded.

---

## 3. Orçamento de testes — regra inegociável

**Wall-clock de `make test` < 300 s (5 minutos).** As três suítes rodam **concorrentes entre si**.

| Suíte | Estratégia | Teto |
|---|---|---|
| Backend | `pytest -n auto`, template database + `BEGIN`/`ROLLBACK` por teste | 45 s |
| Frontend | Vitest threads, jsdom, sem browser | 30 s |
| E2E | Playwright `--workers=N`, **máx. 25 jornadas no projeto inteiro** | 300 s |

Regras derivadas:
- **Nunca** `sleep` em teste. Use espera por condição.
- **Nunca** recriar schema por teste. Template DB criado uma vez por sessão.
- **Nunca** chamar rede externa. LLM, DJEN e DataJud são **sempre** mockados via fixtures gravadas em `tests/fixtures/http/`.
- E2E só ganha jornada nova se couber no teto. Se não couber, o caso vira teste de integração.
- Toda spec declara seu **orçamento de tempo**. Estourou, a spec não fecha.

O CI falha se o wall-clock passar de 300 s. Isso é um gate, não um aviso.

---

## 4. Multi-tenancy — desde a primeira tabela

- **Toda** tabela de domínio tem `tenant_id UUID NOT NULL`.
- **Row Level Security ligado** em todas elas. Política por `current_setting('app.tenant_id')`.
- A sessão do SQLAlchemy seta `app.tenant_id` no início de cada request/task.
- A aplicação **nunca** filtra tenant no `WHERE` manualmente — quem garante é o RLS.
- Teste obrigatório por tabela nova: **tenant A não enxerga dado de tenant B**.

---

## 5. Arquitetura

```
backend/
  app/
    core/          config, security, db, deps, rls, errors
    domain/        entidades por bounded context
      <ctx>/
        models.py      SQLAlchemy
        schemas.py     Pydantic
        repository.py  acesso a dados
        service.py     regra de negócio
        router.py      HTTP
    integrations/  openrouter/, djen/, datajud/, storage/
    ai/            graphs/ (LangGraph), tools/, prompts/
    workers/       celery tasks
  alembic/
  tests/           unit/, integration/, fixtures/
frontend/
  src/
    components/ui/       shadcn (não editar à mão)
    components/domain/   DataTable, FormModal, FilterBar, EntityPicker, KanbanBoard, StatCard...
    features/<ctx>/      páginas + hooks + api
    lib/                 api client, utils
  tests/
e2e/                     Playwright
specs/                   uma spec por arquivo
docs/                    pesquisa e decisões
```

### SOLID — o que exigimos na prática
- **SRP:** `router` só faz HTTP. `service` só faz regra. `repository` só faz query. Router com `select()` dentro é bug.
- **OCP:** integrações atrás de interface (`LLMProvider`, `PublicationSource`, `FileStorage`). Adicionar provider não altera consumidor.
- **LSP:** implementações de uma interface são intercambiáveis nos testes (o mock é uma implementação real da interface).
- **ISP:** interfaces pequenas. Nada de `IService` genérico.
- **DIP:** service depende de abstração, injetada via `Depends`. `import openrouter` dentro de service é bug.

---

## 6. Componentes reutilizáveis — regra dos 3 usos

O objetivo é que implementar a 40ª tela custe pouco.

**Nenhuma feature escreve tabela, modal, filtro ou formulário do zero.** Existe:
- `<DataTable>` — colunas, ordenação, paginação keyset, seleção, ações de linha, export
- `<FilterBar>` — filtros declarativos por schema
- `<FormModal>` — formulário por schema Zod, validação, submit, erro
- `<EntityPicker>` — busca assíncrona de cliente/processo/usuário
- `<KanbanBoard>` — colunas, drag & drop, callback de mudança
- `<StatCard>`, `<EmptyState>`, `<ConfirmDialog>`, `<AIActionPreview>`

Se você escreveu a mesma estrutura **três vezes**, pare e extraia para `components/domain/`.
Toda spec deve declarar quais componentes reutiliza e quais cria.

No backend, o equivalente: `BaseRepository` com CRUD + filtros + paginação. Repositório novo herda.

### Contrato de listagem (toda spec de listagem segue isto)

```
GET /api/v1/<recurso>?cursor=&limit=&sort=&order=&<filtros>
200 { "items": [...], "next_cursor": "...|null", "total": 123 }
```

- **Keyset, nunca offset** — offset quebra em volume. `cursor` codifica `(sort_value, id)` em base64.
- `<DataTable>` nunca faz fetch sozinho — recebe `data`/`pagination`/callbacks; quem busca é a feature.
- Filtros vivem na URL (`useFilters`) — recarregar a página preserva o estado, o link é compartilhável.
- Export respeita os filtros ativos, não a página visível.
- Ver `specs/007-design-system-dominio.md` para os sete componentes de `components/domain/`
  (`DataTable`, `FilterBar`, `FormModal`, `EntityPicker`, `StatCard`, `EmptyState`, `ConfirmDialog`)
  e os hooks `useDataTable`/`useFilters` que os sustentam.

---

## 7. IA — regras duras

1. **OpenRouter é o único caminho de saída.** Um client, `app/integrations/openrouter/`.
2. **Modelo é configuração, não código.** Tabela `ai_feature_config` guarda modelo por feature; usuário troca na UI.
3. **RAG é proibido.** Contexto vem de **tool calling** — o agente consulta o banco via ferramentas tipadas.
4. **Toda ferramenta de escrita exige confirmação humana.** Fluxo: agente propõe → UI mostra preview → usuário confirma → executa → grava em `ai_audit_log`.
5. **Ferramentas respeitam RLS e RBAC.** Uma tool nunca vê além do que o usuário logado vê.
6. **Nenhuma chamada real de LLM em teste.** Fixtures gravadas.
7. Todo uso registra tokens e custo em `ai_usage`.

---

## 8. Fluxo SDD por ciclo do /loop

1. Ler `ROADMAP.md`, achar a próxima spec não concluída.
2. **Expandir** a spec: escrever `specs/NNN-slug.md` completo, seguindo `specs/000-TEMPLATE.md`.
3. Implementar **apenas** o escopo da spec. Fora de escopo é fora.
4. Escrever os testes declarados na spec.
5. `make test` — verde e dentro dos 300 s.
6. `make lint` — verde.
7. Marcar a spec como concluída no `ROADMAP.md`.
8. Commit atômico: `feat(NNN): <título>` ou `refactor(NNN): <título>`.
9. Push.

**Uma spec por ciclo.** Não adiante trabalho da próxima.
Se o ciclo não fechar (teste vermelho, orçamento estourado), **não marque como concluída** e não avance.

### Specs de refatoração (010, 020, …, 100)
Não entregam feature. Passam pente fino nas 9 anteriores:
- cobertura de teste faltando
- duplicação (aplicar regra dos 3 usos)
- violação de SOLID (router com query, service acoplado a integração)
- índices faltando, N+1, query lenta
- tipos frouxos (`Any`, `as`, `# type: ignore`)
- componente que devia estar em `components/domain/`
- tempo de suíte: se passou de 240 s, otimizar até voltar

Refatoração **não muda comportamento**. Testes existentes continuam passando sem edição.

---

## 9. Convenções

- Migrations: uma por spec, nome `NNN_<slug>`. Nunca editar migration já commitada.
- API: `/api/v1/<recurso>`, plural, snake_case nos campos JSON.
- Erros: RFC 7807 (`application/problem+json`).
- Datas na API: ISO 8601. Na UI: `DD/MM/AAAA`.
- Dinheiro: `Numeric(14,2)` no banco, string com vírgula na UI brasileira.
- Commits: Conventional Commits com o número da spec.
- Idioma: código e identificadores em **inglês**; UI, mensagens ao usuário e specs em **português**.

---

## 10. Comandos

```bash
make up            # sobe Postgres + Redis + MinIO
make migrate       # alembic upgrade head
make dev           # backend + frontend
make test          # 3 suítes em paralelo, falha se > 300 s
make lint          # ruff + black + mypy + eslint + tsc + prettier
make test-nightly  # perfilamento com 1,95 milhão de linhas — semeia, mede e limpa
```

Operação (spec 099, dentro do container):

```bash
rito db upgrade      rito db seed        rito health
rito tenant create --name --slug --admin-email
rito backup create   rito backup restore --input <arquivo> --yes
```

## 11. Os dois gates que não são aviso

O CI falha, não avisa, em qualquer um dos dois:

- **wall-clock de `make test` acima de 300 s** — impede o projeto de ficar lento sem
  ninguém notar;
- **orçamento de queries por endpoint** (`tests/integration/test_query_budget.py`) —
  impede o N+1 de entrar sem ninguém notar. Listagem cabe em 3 queries, detalhe em 5,
  timeline em 3, busca global em 4. A contagem inclui a autenticação e exclui o preâmbulo
  de RLS.

Perfilamento com volume real fica fora do PR (`make test-nightly`): 1,95 milhão de linhas
não cabem nos 300 s, e tempo medido em CI compartilhado oscila 30% entre execuções.

## 12. Depois das 100

O `ROADMAP.md` deixou de ser fila e virou histórico. Trabalho novo entra como spec 101 em
diante, no mesmo ciclo — e a cada 10, uma refatoração. Os dois gates continuam valendo;
são eles que impedem a spec 137 de desfazer o que a 098 comprou.
