# 082 — Runtime LangGraph

**Fase:** 8 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 081 · **Status:** ⬜ pendente

---

## 1. Objetivo

Orquestração de agentes com LangGraph, com o recurso que torna a IA segura neste produto:
**interrupção para confirmação humana**. O grafo pausa, persiste o estado, espera o usuário
aprovar e retoma de onde parou.

## 2. Escopo

- Runtime LangGraph integrado ao `LLMProvider` de 081
- Checkpointer em Postgres
- Interrupção e retomada (human-in-the-loop)
- Observabilidade de passos
- Timeout e cancelamento
- Grafo base reutilizável pelos agentes

## 3. Fora de escopo

- Ferramentas concretas → 083/084 · Agentes específicos → 085+

## 4. Modelo de dados

```sql
CREATE TABLE ai_threads (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID NOT NULL REFERENCES users(id),
  graph_name TEXT NOT NULL,
  feature_key TEXT NOT NULL,
  title TEXT,
  status TEXT NOT NULL DEFAULT 'running',   -- running | waiting_human | done | error | cancelled
  context JSONB NOT NULL DEFAULT '{}',      -- tela, processo, cliente
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_threads_user ON ai_threads (tenant_id, user_id, updated_at DESC);

CREATE TABLE ai_checkpoints (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  thread_id UUID NOT NULL REFERENCES ai_threads(id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  step SMALLINT NOT NULL,
  node TEXT NOT NULL,
  state JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (thread_id, step)
);

CREATE TABLE ai_steps (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  thread_id UUID NOT NULL REFERENCES ai_threads(id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  step SMALLINT NOT NULL,
  node TEXT NOT NULL,
  kind TEXT NOT NULL,                        -- 'llm' | 'tool' | 'interrupt' | 'end'
  input JSONB, output JSONB,
  duration_ms INTEGER, error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_steps_thread ON ai_steps (thread_id, step);
```
RLS nas três. Migration `082_langgraph.py`.

## 5. Contratos internos

```python
class AgentGraph(Protocol):
    name: str
    async def invoke(self, thread: AiThread, input: dict) -> GraphResult: ...
    async def resume(self, thread: AiThread, human_input: dict) -> GraphResult: ...

@dataclass
class GraphResult:
    status: Literal['done','waiting_human','error']
    output: dict | None
    pending_action: PendingAction | None   # o que espera confirmação
```

## 6. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/ai/threads` → `{graph_name, input, context}` |
| GET | `/api/v1/ai/threads?cursor=` |
| GET | `/api/v1/ai/threads/{id}` |
| POST | `/api/v1/ai/threads/{id}/resume` → `{approved, human_input}` |
| POST | `/api/v1/ai/threads/{id}/cancel` |
| GET | `/api/v1/ai/threads/{id}/steps` |
| GET | `/api/v1/ai/threads/{id}/stream` (SSE) |

## 7. Front-end

**Reutiliza:** `EmptyState`, `ConfirmDialog`
**Cria:** `AiThreadProvider`, `useAiThread`, `AgentStepsTimeline` (o que o agente fez),
`PendingActionCard`
**Rota:** consumido por 085+

## 8. Regras de negócio

1. Checkpoint a cada nó — falha no meio retoma do último ponto, sem refazer tudo.
2. Nó que precisa de aprovação **interrompe** o grafo: status vira `waiting_human` e o estado é persistido.
3. Retomada exige `approved`. Recusa encerra o thread como `cancelled`, registrando o motivo.
4. Thread em `waiting_human` expira em 24 h e vira `cancelled` por job.
5. Timeout de 5 min por nó, 15 min por execução.
6. Cancelar interrompe na próxima fronteira de nó — sem matar operação em andamento no meio.
7. Todo passo é registrado em `ai_steps`, com entrada e saída. **É o que permite auditar o que o agente fez.**
8. Entrada e saída de passo têm tamanho limitado a 100 KB; acima disso, guarda referência.
9. Máximo de 25 passos por execução — protege contra laço infinito.
10. Erro em nó é registrado e o grafo decide: repetir, desviar ou falhar. Nunca falha silencioso.
11. Thread pertence ao usuário; outro usuário do mesmo tenant não lê, exceto ADMINISTRADOR em auditoria.
12. Retenção de 90 dias para threads concluídos.

## 9. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | grafo simples executa e termina | ~0,4 s |
| integração | **interrompe, persiste e retoma após aprovação** | ~0,6 s |
| integração | recusa encerra como cancelado com motivo | ~0,4 s |
| integração | falha no meio retoma do último checkpoint | ~0,5 s |
| integração | expira após 24 h em espera | ~0,3 s |
| integração | timeout de nó interrompe | ~0,4 s |
| integração | cancelamento respeita a fronteira do nó | ~0,4 s |
| integração | 26º passo é barrado | ~0,3 s |
| integração | passo grande guarda referência | ~0,3 s |
| integração | thread de outro usuário → 403 | ~0,3 s |
| integração | ADMINISTRADOR audita thread alheio | ~0,2 s |
| integração | RLS nas três tabelas | ~0,4 s |
| frontend | timeline de passos renderiza | ~0,4 s |

**Total:** ~4,9 s
LLM sempre mockado; grafos de teste usam nós determinísticos.

## 10. Definição de pronto

Checklist padrão · Interrupção e retomada provadas · Todo passo auditável · Commit `feat(082): runtime LangGraph`
