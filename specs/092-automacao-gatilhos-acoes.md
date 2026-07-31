# 092 — Automação: gatilhos e ações

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 038 · **Status:** ⬜ pendente

---

## 1. Objetivo

Motor de automação no modelo **gatilho → ação → tempo**. Generaliza o workflow de 038: em vez
de só "mudou de etapa, cria tarefas", passa a ser qualquer evento disparando qualquer ação.

## 2. Escopo

- Tabelas de automação, gatilho, ação e execução
- Gatilhos: tarefa concluída, mudança de etapa, processo criado, intimação recebida, lançamento vencido
- Ações: criar tarefa, definir responsável, mudar etapa, notificar, aguardar condição
- Controle de tempo: imediato, N dias úteis ou corridos, condicionado
- Editor visual
- Log de execução

## 3. Fora de escopo

- Webhooks → 093 · Decisão por LLM → 094

## 4. Modelo de dados

```sql
CREATE TABLE automations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  trigger_kind TEXT NOT NULL,
  trigger_config JSONB NOT NULL DEFAULT '{}',   -- ex.: task_type_id, stage_id
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);
CREATE INDEX ix_automations_trigger ON automations (tenant_id, trigger_kind) WHERE is_active;

CREATE TABLE automation_actions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  automation_id UUID NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
  position SMALLINT NOT NULL,
  action_kind TEXT NOT NULL,
  action_config JSONB NOT NULL DEFAULT '{}',
  delay_kind TEXT NOT NULL DEFAULT 'immediate',  -- immediate | business_days | calendar_days | after_previous
  delay_value SMALLINT,
  condition JSONB,                                -- executa só se
  UNIQUE (automation_id, position)
);

CREATE TABLE automation_runs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  automation_id UUID NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
  trigger_payload JSONB NOT NULL,
  subject_type TEXT, subject_id UUID,
  status TEXT NOT NULL DEFAULT 'running',
  actions_completed SMALLINT NOT NULL DEFAULT 0,
  error TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);
CREATE INDEX ix_runs_automation ON automation_runs (automation_id, started_at DESC);
```
RLS nas três. Migration `092_automations.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/automations?status=` | ADMINISTRADOR |
| POST/PUT/DELETE | `/api/v1/automations[/{id}]` | GESTOR |
| POST | `/api/v1/automations/{id}/test` → simula sem executar | GESTOR |
| GET | `/api/v1/automations/{id}/runs?cursor=` | ADMINISTRADOR |
| POST | `/api/v1/automations/{id}/toggle` | GESTOR |

## 6. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `EntityPicker`, `ConfirmDialog`
**Cria:** `AutomationBuilder` (gatilho no topo, ações em sequência), `TriggerSelect`,
`ActionRow` (tipo + configuração + tempo + condição), `AutomationTestDialog`,
`RunsTimeline`
**Rota:** `/settings/automations`

## 7. Regras de negócio

1. Gatilhos disponíveis: `task.completed`, `lawsuit.stage_changed`, `lawsuit.created`,
   `publication.received`, `transaction.overdue`.
2. `trigger_config` restringe o gatilho — "tarefa concluída" pode valer só para um tipo de tarefa.
3. Ações são executadas **em sequência**, respeitando `position`.
4. `delay_kind = after_previous` encadeia: a ação só roda quando a anterior for concluída (útil para tarefa que depende de tarefa).
5. Dias úteis usam `app/core/dates.py` (040), com feriados.
6. `condition` avalia campos do sujeito antes de executar; falsa, a ação é pulada e registrada como tal.
7. **Proteção contra laço:** uma automação não dispara a si mesma, e a cadeia é limitada a 10 automações encadeadas por evento original.
8. Execução de ação é idempotente por `(run_id, position)` — reprocesso não duplica.
9. Falha em uma ação interrompe a execução e registra; as anteriores permanecem.
10. Teste simula tudo e mostra o que aconteceria, **sem persistir**.
11. Desativar não afeta execuções em andamento.
12. Automação de escrita respeita as permissões do **criador**, não de quem disparou.
13. Máximo de 20 ações por automação.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | os 5 gatilhos disparam (parametrizado) | ~0,7 s |
| integração | `trigger_config` restringe corretamente | ~0,4 s |
| integração | ações executam em sequência | ~0,4 s |
| integração | `after_previous` encadeia | ~0,4 s |
| integração | atraso em dias úteis pula feriado | ~0,3 s |
| integração | condição falsa pula e registra | ~0,3 s |
| integração | **automação não dispara a si mesma** | ~0,4 s |
| integração | **cadeia limitada a 10** | ~0,4 s |
| integração | reprocesso é idempotente | ~0,4 s |
| integração | falha interrompe e preserva as anteriores | ~0,4 s |
| integração | teste não persiste | ~0,3 s |
| integração | permissão é a do criador | ~0,3 s |
| integração | 21ª ação → 422 | ~0,2 s |
| frontend | builder monta gatilho e ações | ~0,5 s |

**Total:** ~5,4 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Proteção contra laço provada · Commit `feat(092): automação — gatilhos e ações`
