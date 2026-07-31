# 094 — Automação com decisão por LLM

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 093, 082 · **Status:** ⬜ pendente

---

## 1. Objetivo

Nó de decisão inteligente dentro da automação: em vez de condição fixa em campo, o LLM analisa
o contexto e escolhe o ramo. Une o motor de 092 com o runtime de 082.

## 2. Escopo

- Ação `llm_decision` com ramos nomeados
- Contexto coletado por tool calling
- Ramificação condicional
- Registro do raciocínio
- Limite de custo por automação
- Fallback quando o LLM falha

## 3. Fora de escopo

- Escrita autônoma sem aprovação — a regra de 084 continua valendo

## 4. Modelo de dados

```sql
ALTER TABLE automation_actions
  ADD COLUMN branches JSONB;          -- {"nome_do_ramo": [action_ids]}

CREATE TABLE automation_decisions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  run_id UUID NOT NULL REFERENCES automation_runs(id) ON DELETE CASCADE,
  action_id UUID NOT NULL REFERENCES automation_actions(id),
  question TEXT NOT NULL,
  context_summary TEXT,
  chosen_branch TEXT,
  confidence NUMERIC(3,2),
  reasoning TEXT NOT NULL,
  model TEXT NOT NULL,
  tokens_used INTEGER,
  fell_back BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_decisions_run ON automation_decisions (run_id, created_at);

ALTER TABLE automations
  ADD COLUMN monthly_ai_budget_usd NUMERIC(10,2),
  ADD COLUMN current_month_spend_usd NUMERIC(10,2) NOT NULL DEFAULT 0;
```
RLS ligado. Migration `094_llm_decisions.py`.

## 5. Configuração da ação

```json
{ "action_kind": "llm_decision",
  "action_config": {
    "question": "Esta intimação exige resposta em até 5 dias?",
    "context_tools": ["get_lawsuit", "get_publication"],
    "branches": ["urgente", "normal", "sem_acao"],
    "default_branch": "normal",
    "min_confidence": 0.7 } }
```

## 6. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/automations/{id}/decisions?run_id=` |
| POST | `/api/v1/automations/{id}/decisions/simulate` → `{subject_id}` |
| PUT | `/api/v1/automations/{id}/ai-budget` → `{monthly_ai_budget_usd}` |

## 7. Front-end

**Reutiliza:** `AutomationBuilder`, `ActionRow`, `AgentStepsTimeline`
**Cria:** `LlmDecisionAction` (pergunta, ferramentas, ramos, confiança mínima),
`BranchEditor` (ações por ramo), `DecisionLogCard` (mostra o raciocínio),
`AiBudgetField`
**Rota:** dentro de `/settings/automations`

## 8. Regras de negócio

1. O nó de decisão escolhe **exatamente um** ramo entre os declarados. Resposta fora da lista aciona o `default_branch` e é registrada como anomalia.
2. Confiança abaixo de `min_confidence` também vai para o `default_branch`, registrando o motivo.
3. Contexto é coletado pelas ferramentas de **leitura** de 083. O nó de decisão **nunca** escreve.
4. `reasoning` é obrigatório na resposta do LLM e é sempre gravado — automação que decide sem explicar não é auditável.
5. Falha do LLM (timeout, erro, sem chave) → `default_branch`, `fell_back = true`, e a automação **continua**. Automação não pode parar por indisponibilidade de IA.
6. Orçamento mensal por automação: atingido, as execuções seguintes usam o `default_branch` sem chamar o LLM, com alerta ao GESTOR.
7. Máximo de **3 nós de decisão** por automação — mais que isso é regra de negócio disfarçada de IA.
8. Ramo pode conter as mesmas ações de 092, inclusive webhook.
9. Ramos aninhados não são permitidos: decisão dentro de ramo de decisão → 422.
10. Simulação roda a decisão sem executar as ações, mostrando o ramo escolhido e o raciocínio.
11. Ação de escrita dentro de um ramo segue as regras de 092 (permissão do criador), **não** cria `ai_action` — é automação configurada por humano, não proposta de agente. Isso é uma distinção deliberada e está documentada.
12. Toda decisão registra tokens e custo.

## 9. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | decisão escolhe o ramo e executa as ações dele | ~0,5 s |
| integração | resposta fora da lista → default, com anomalia | ~0,4 s |
| integração | confiança baixa → default com motivo | ~0,3 s |
| integração | **contexto usa só ferramentas de leitura** | ~0,4 s |
| integração | `reasoning` sempre gravado | ~0,2 s |
| integração | **falha do LLM cai no default e continua** | ~0,5 s |
| integração | sem chave de IA a automação continua funcionando | ~0,4 s |
| integração | orçamento estourado usa default sem chamar LLM | ~0,4 s |
| integração | 4º nó de decisão → 422 | ~0,2 s |
| integração | ramo aninhado → 422 | ~0,2 s |
| integração | simulação não executa ações | ~0,3 s |
| frontend | editor de ramos | ~0,4 s |

**Total:** ~4,2 s

## 10. Definição de pronto

Checklist padrão · IA indisponível nunca trava automação · Raciocínio sempre auditável · Commit `feat(094): automação com decisão por LLM`
