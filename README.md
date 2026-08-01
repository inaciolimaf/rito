# Rito

> **Todo processo tem um rito. O seu escritório também.**

Sistema de gestão jurídica para escritórios de advocacia brasileiros. SaaS multi-tenant,
com integração nativa aos dados oficiais do CNJ e camada de IA em todo o produto.

Construído com **Spec Driven Development**: 100 specs sequenciais, cada uma implementada,
testada e commitada em um ciclo fechado.

---

## Estado

🚧 **Spec 015 de 100 concluída.** Backend completo (multi-tenancy, RLS, autenticação,
RBAC) + frontend com login real, design system de domínio e o app shell navegável
(sidebar de 15 itens, busca global, breadcrumbs) + pipeline de testes com gate de 120s
executável (rede real bloqueada, contador de jornadas e2e, CI no GitHub Actions) + pente
fino de refatoração (99% de cobertura, índices de FK, `mypy --strict` e `tsc` verdes) +
cadastro do Escritório (CRUD, CPF/CNPJ validado, autofill de CEP via ViaCEP, upload de
logotipo com redimensionamento, storage S3/MinIO atrás de interface) + gestão de usuários
(convite por e-mail, 67 cargos, OAB, jornada de trabalho, RBAC fino de "próprio usuário ou
administrador", listagem paginada por keyset com filtros) + times/squads (CRUD, membros
reconciliados no PUT, abas Colaboradores/Times na mesma tela de Usuários) + grupos e tipos
de ação (taxonomia que classifica processos por área do direito, 6 grupos/10 tipos padrão,
responsável por intimações opcional por grupo, transferência em lote antes de excluir) +
fases e etapas (9 fases fixas do funil processual, 59 etapas configuráveis com estagnação
condicional e reordenação por drag-and-drop dentro da fase) — próxima é a 016 (Origem de
pessoas).

Acompanhe em [`ROADMAP.md`](./ROADMAP.md).

---

## O produto

| Módulo | O que faz |
|---|---|
| **Meu Painel** | Caixa de entrada de tarefas, Taskscore, metas, agenda do dia |
| **Agenda** | Mês/semana/dia + feed iCal para Google, Outlook e Apple |
| **Atividades** | Tarefas com prazo fatal, recorrência, múltiplos responsáveis |
| **CRM** | Kanban por fase processual, estagnação, workflow automático |
| **Contatos** | PF/PJ, representante legal, validação real de CPF/CNPJ |
| **Processos** | Timeline unificada, partes com polo, honorários, contingenciamento |
| **Intimações** | Captura automática do DJEN, roteamento para tarefa, cálculo de prazo |
| **Parceiros** | Rede de escritórios com compartilhamento de processos |
| **Modelos** | Editor rich text com variáveis automáticas e geração de PDF |
| **Financeiro** | Plano de contas DRE, fluxo de caixa, recorrência, parcelamento |
| **Relatórios** | Agilidade, produtividade e BI (estoque, safra, tempo, custos) |

---

## Integrações — só fontes oficiais

Sem raspagem de tribunal, sem certificado digital, sem manutenção de scraper.

### DJEN — Diário de Justiça Eletrônico Nacional
`comunicaapi.pje.jus.br/api/v1/comunicacao` · **sem autenticação**

Intimações e publicações de cobertura nacional, por OAB, CPF/CNPJ ou número de processo.
É a fonte **juridicamente válida** para contagem de prazo — pela Resolução CNJ 569/2024,
captura feita no sistema do tribunal não tem força de intimação.

### DataJud — Base de Dados do Poder Judiciário
`api-publica.datajud.cnj.jus.br` · **chave pública do CNJ**

Capa processual e movimentos com códigos padronizados nacionalmente, um alias por tribunal.

> Ambas foram testadas e respondem em produção. A chave do DataJud é pública e pode ser
> rotacionada pelo CNJ — fica em variável de ambiente, com alerta em 401.

---

## IA

Densa e transversal, mas com três regras rígidas:

1. **OpenRouter é o único gateway.** Modelo **selecionável pelo usuário** por feature — nunca hardcoded.
2. **Tool calling, não RAG.** Sem vector store, sem embeddings. O agente consulta o banco por ferramentas tipadas que respeitam RLS e RBAC.
3. **Escrita exige confirmação humana.** A IA propõe, a UI mostra preview, o usuário confirma, o sistema audita.

Orquestração com **LangGraph** (checkpoint em Postgres, interrupção para human-in-the-loop).

**Onde aparece:** copiloto global · resumo e classificação de intimação com cálculo de prazo ·
19 agentes de petição por área do direito · redação assistida no editor · extração de dados de
documentos · text-to-SQL guardrailed para métricas · next-best-action · detecção de risco ·
decisão por LLM dentro de automações.

---

## Stack

**Backend** — Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Alembic · PostgreSQL 16 (RLS) · Redis · Celery
**Frontend** — Vite · React 18 · TypeScript strict · Tailwind · shadcn/ui · TanStack Query
**IA** — OpenRouter · LangGraph
**Testes** — pytest · Vitest · Playwright

---

## Testes

**Wall-clock de `make test` < 120 s.** Gate de CI, não meta.

| Suíte | Estratégia | Teto |
|---|---|---|
| Backend | `pytest -n auto`, template DB + rollback | 45 s |
| Frontend | Vitest threads, jsdom | 30 s |
| E2E | Playwright sharded, **máx. 25 jornadas** | 60 s |

As três rodam **concorrentes**. Nenhum teste toca a rede — LLM, DJEN e DataJud usam fixtures gravadas.

---

## Começando

```bash
cp .env.example .env      # configure OPENROUTER_API_KEY e DATAJUD_API_KEY
make up                   # Postgres + Redis
make migrate
make seed                 # taxonomias padrão: 182 tribunais, 152 tarefas, 61 categorias...
make dev                  # backend :8000 · frontend :5173
```

```bash
make test    # 3 suítes em paralelo, falha se > 120s
make lint    # ruff + mypy + eslint + tsc
```

---

## Como este repositório é construído

Cada ciclo do `/loop`:

1. Lê o `ROADMAP.md` e pega a próxima spec pendente
2. **Expande** a spec em `specs/NNN-slug.md` (as specs são escritas just-in-time, com o código real em contexto)
3. Implementa só o escopo dela
4. Escreve os testes declarados
5. `make test` verde e dentro do orçamento
6. Marca concluída no roadmap e commita

A cada 10ª spec, um ciclo de refatoração: cobertura faltando, duplicação, SOLID, índices,
tipos frouxos — e devolver o wall-clock da suíte para baixo de 90 s.

**Documentos:**
[`CLAUDE.md`](./CLAUDE.md) — constituição de engenharia ·
[`ROADMAP.md`](./ROADMAP.md) — as 100 specs ·
[`specs/`](./specs) — detalhe de cada uma ·
[`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md`](./docs/ADVBOX-ESPECIFICACAO-COMPLETA.md) — levantamento de referência

---

## Licença

Privado.
