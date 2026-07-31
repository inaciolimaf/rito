# 089 — IA analítica

**Fase:** 8 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 085, 078 · **Status:** ⬜ pendente

---

## 1. Objetivo

Três capacidades analíticas: perguntar métrica em linguagem natural, receber recomendação de
próxima ação por processo e ser avisado de risco antes que vire problema.

## 2. Escopo

- Text-to-SQL **guardrailed** para métricas
- Next-best-action por processo
- Detecção de risco: prazo, estagnação, inadimplência, carteira
- Painel de insights

## 3. Fora de escopo

- Previsão de resultado por machine learning (fora do escopo)
- Alteração automática de dado (nunca)

## 4. Modelo de dados

```sql
CREATE TABLE ai_sql_queries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID NOT NULL REFERENCES users(id),
  question TEXT NOT NULL,
  generated_sql TEXT NOT NULL,
  was_allowed BOOLEAN NOT NULL,
  rejection_reason TEXT,
  row_count INTEGER,
  duration_ms INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai_insights (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  kind TEXT NOT NULL,                  -- 'deadline_risk' | 'stagnation' | 'overdue' | 'portfolio'
  severity TEXT NOT NULL,              -- 'info' | 'warning' | 'critical'
  subject_type TEXT, subject_id UUID,
  title TEXT NOT NULL, body TEXT NOT NULL,
  suggested_action JSONB,
  dismissed_by UUID REFERENCES users(id),
  dismissed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_insights_open ON ai_insights (tenant_id, severity, created_at DESC)
  WHERE dismissed_at IS NULL;

CREATE VIEW ai_allowed_metrics AS ...;   -- allowlist: só colunas agregáveis, sem PII
```
RLS ligado. Migration `089_ai_analytics.py`.

## 5. Guardrails do text-to-SQL

Camadas, todas obrigatórias:

1. **Allowlist de tabelas e colunas** — só a view `ai_allowed_metrics` e as views de BI. Tabelas com dado pessoal não estão na lista.
2. **Somente `SELECT`** — parser de AST rejeita qualquer outro comando. Não é regex.
3. **Sem subquery em tabela fora da allowlist.**
4. Execução em conexão **read-only**, com o `tenant_id` já setado.
5. `LIMIT` obrigatório, máximo de 1.000 linhas — injetado se ausente.
6. `statement_timeout` de 5 s.
7. SQL gerado é **exibido ao usuário** antes de rodar.
8. Toda tentativa é registrada, inclusive as rejeitadas.

## 6. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/ai/analytics/ask` → `{question}` |
| GET | `/api/v1/ai/insights?kind=&severity=&dismissed=false` |
| POST | `/api/v1/ai/insights/{id}/dismiss` |
| GET | `/api/v1/lawsuits/{id}/next-best-action` |
| POST | `/api/v1/ai/insights/refresh` (ADMINISTRADOR) |

## 7. Front-end

**Reutiliza:** `DataTable`, `StatCard`, `CopilotPanel`, `AIActionPreview`
**Cria:** `AskMetricsBox`, `SqlPreview` (SQL destacado, com explicação em português),
`InsightsPanel`, `InsightCard`, `NextActionCard`
**Rotas:** `/reports?tab=insights`, card em `/lawsuits/:id`

## 8. Regras de negócio

1. Pergunta ambígua devolve pedido de esclarecimento, não SQL chutado.
2. SQL fora da allowlist é rejeitado com explicação em português; a tentativa é registrada.
3. O usuário **vê o SQL** antes da execução e pode cancelar.
4. Resultado é apresentado como tabela e como frase resumo.
5. Text-to-SQL exige ADMINISTRADOR; métricas financeiras exigem também `financial_access ≥ READ_ONLY`.
6. **Next-best-action** por processo considera: etapa atual, tempo parado, última movimentação,
   tarefas pendentes, prazos e situação financeira. Sugere ação concreta com justificativa.
7. A sugestão pode virar tarefa — pelo fluxo de aprovação de 084, nunca direto.
8. Insights são gerados por job diário e podem ser dispensados individualmente.
9. Tipos de insight: prazo em risco, processo estagnado, inadimplência relevante, concentração de carteira.
10. Insight dispensado não volta pelos próximos 30 dias.
11. Insight crítico aparece no painel inicial de quem é responsável.
12. Todo insight aponta o registro que o originou — nada de alerta genérico.

## 9. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | pergunta simples gera SQL válido e roda | ~0,5 s |
| integração | **`DROP`/`DELETE`/`UPDATE` são rejeitados pelo parser** | ~0,4 s |
| integração | **tabela fora da allowlist é rejeitada** | ~0,4 s |
| integração | **subquery em tabela proibida é rejeitada** | ~0,4 s |
| integração | `LIMIT` é injetado quando ausente | ~0,3 s |
| integração | timeout de 5 s interrompe | ~0,3 s |
| integração | **conexão read-only impede escrita mesmo se o SQL passar** | ~0,4 s |
| integração | tentativa rejeitada é registrada | ~0,2 s |
| integração | ambiguidade pede esclarecimento | ~0,3 s |
| integração | financeiro sem permissão → 403 | ~0,3 s |
| integração | next-best-action considera os 5 sinais | ~0,5 s |
| integração | sugestão vira tarefa pelo fluxo de aprovação | ~0,4 s |
| integração | insight dispensado não volta em 30 dias | ~0,3 s |
| frontend | SQL exibido antes de executar | ~0,4 s |

**Total:** ~5,1 s

> As quatro camadas de guardrail marcadas precisam de teste independente. Um guardrail que
> depende de outro para funcionar não é guardrail.

## 10. Definição de pronto

Checklist padrão · 4 camadas de guardrail testadas isoladamente · SQL sempre visível · Commit `feat(089): IA analítica`
