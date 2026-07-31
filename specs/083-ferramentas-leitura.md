# 083 — Ferramentas de leitura

**Fase:** 8 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 082 · **Status:** ⬜ pendente

---

## 1. Objetivo

Como o agente enxerga os dados do escritório. **Sem RAG, sem embeddings, sem vector store** —
o contexto vem de ferramentas tipadas que consultam o banco, respeitando RLS e RBAC do usuário
que pediu.

Essa escolha tem uma consequência boa: o agente nunca responde com dado desatualizado de índice,
e nunca vê o que o usuário não veria.

## 2. Escopo

- Registry de ferramentas com schema JSON derivado de Pydantic
- Ferramentas de leitura para todos os módulos
- Propagação de identidade e tenant
- Limite de linhas e truncamento
- Registro de cada chamada

## 3. Fora de escopo

- Ferramentas de escrita → 084 · RAG — **proibido pelo `CLAUDE.md`**

## 4. Modelo de dados

```sql
CREATE TABLE ai_tool_calls (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  thread_id UUID REFERENCES ai_threads(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id),
  tool_name TEXT NOT NULL,
  arguments JSONB NOT NULL,
  result_summary TEXT,
  row_count INTEGER,
  duration_ms INTEGER,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_tool_calls_thread ON ai_tool_calls (thread_id, created_at);
```
RLS ligado. Migration `083_tool_calls.py`.

## 5. Catálogo de ferramentas de leitura

| Ferramenta | O que retorna |
|---|---|
| `search_customers` | contatos por nome, CPF/CNPJ, cidade, origem |
| `get_customer` | ficha completa + processos vinculados |
| `search_lawsuits` | processos pelos filtros de 027 |
| `get_lawsuit` | processo completo com partes e valores |
| `get_lawsuit_timeline` | timeline unificada (026) |
| `search_tasks` | tarefas por responsável, período, status, tipo |
| `get_inbox` | caixa de entrada do usuário |
| `search_publications` | intimações por período, tribunal, processo |
| `get_publication` | inteiro teor |
| `search_transactions` | lançamentos pelos filtros de 059 |
| `get_financial_summary` | saldo, previsto, realizado, atrasados |
| `get_lawsuit_financials` | financeiro de um processo |
| `get_productivity` | Taskscore por usuário e período |
| `get_bi_metrics` | indicadores das 4 abas de BI |
| `list_taxonomies` | grupos, tipos, fases, etapas, categorias, origens |
| `get_current_context` | tela atual, processo ou cliente aberto |

## 6. Contratos internos

```python
@tool(name="search_lawsuits", description="...")
class SearchLawsuitsInput(BaseModel):
    query: str | None = None
    stage_id: UUID | None = None
    responsible_id: UUID | None = None
    limit: int = Field(default=20, le=50)

class SearchLawsuitsOutput(BaseModel):
    items: list[LawsuitSummary]
    total: int
    truncated: bool
```

## 7. Regras de negócio

1. **Toda ferramenta executa no contexto do usuário que pediu.** Mesma sessão, mesmo `app.tenant_id`, mesmo RBAC. O agente não tem privilégio próprio.
2. Ferramenta financeira exige `financial_access ≥ READ_ONLY` do **usuário**; sem isso, retorna erro tipado que o agente comunica em linguagem natural.
3. Tarefa privada de terceiro nunca aparece, nem em agregado detalhado.
4. Limite rígido de 50 linhas por chamada. Excedeu → `truncated = true` e o agente é instruído a refinar.
5. Saída tem teto de 20 KB; acima disso, resume e sinaliza.
6. Toda chamada é registrada com argumentos, contagem de linhas e duração.
7. Ferramenta **nunca** recebe SQL cru — só parâmetros tipados. Text-to-SQL é outra coisa, tem guardrail próprio e vem em 089.
8. Erro em ferramenta vira mensagem estruturada para o LLM, não exceção — o agente precisa poder se corrigir.
9. Schema JSON é derivado do Pydantic, nunca escrito à mão.
10. Ferramenta é implementada sobre os **services** de domínio (preparados em 070), não com query própria.
11. Máximo de 10 chamadas de ferramenta por passo do grafo.
12. Registry é montado por decorator; ferramenta nova aparece sozinha no catálogo.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | schema JSON derivado do Pydantic | ~0,2 s |
| unit | registry descobre por decorator | ~0,2 s |
| integração | **cada ferramenta respeita o tenant** (parametrizado, 16 ferramentas) | ~1,2 s |
| integração | **ferramenta financeira com `NONE` → erro tipado** | ~0,4 s |
| integração | tarefa privada de terceiro não aparece | ~0,4 s |
| integração | limite de 50 linhas com `truncated` | ~0,3 s |
| integração | saída acima de 20 KB é resumida | ~0,3 s |
| integração | chamada registrada em `ai_tool_calls` | ~0,3 s |
| integração | erro vira mensagem estruturada, não exceção | ~0,3 s |
| integração | 11ª chamada no mesmo passo é barrada | ~0,3 s |
| **meta** | **nenhuma ferramenta usa SQL cru** (grep) | ~0,2 s |
| **meta** | **nenhum vector store ou embedding no projeto** (grep) | ~0,2 s |

**Total:** ~4,3 s

> O teste parametrizado de isolamento é o mais importante: **16 ferramentas × verificar que o
> agente não vê dado de outro tenant.** Uma ferramenta que ignore RLS é vazamento com cara de feature.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · 16 ferramentas com teste de isolamento · Zero RAG no projeto · Commit `feat(083): ferramentas de leitura`
