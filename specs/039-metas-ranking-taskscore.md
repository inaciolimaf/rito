# 039 — Metas, ranking e painel Taskscore

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 036 · **Status:** ⬜ pendente

---

## 1. Objetivo

Fechar o ciclo do Taskscore: pontos viram ranking, ranking vira meta, meta vira gestão. É a
tela que o gestor abre para saber quem está produzindo.

## 2. Escopo

- Meta mensal de pontos por usuário
- Meta mensal de fechamentos por grupo de ação
- Ranking com 4 critérios de ordenação
- Período mensal ou **ELTV** (vida toda)
- Gráfico mês atual × mês anterior × meta
- Painel no `/home` (aba Desempenho)

## 3. Fora de escopo

- Relatórios de gestão → 071–072 · BI → 074–077

## 4. Modelo de dados

```sql
CREATE TABLE closure_goals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  action_group_id UUID NOT NULL REFERENCES action_groups(id),
  monthly_target INTEGER NOT NULL CHECK (monthly_target >= 0),
  UNIQUE (tenant_id, action_group_id)
);
-- meta de pontos por usuário já existe: users.points_goal (spec 012)

CREATE MATERIALIZED VIEW user_monthly_scores AS
SELECT tenant_id, user_id,
       date_trunc('month', completed_at)::date AS month,
       COUNT(*) AS tasks_completed,
       COALESCE(SUM(points_earned),0) AS points,
       COUNT(*) FILTER (WHERE completed_at::date <= deadline_date) AS on_time,
       COUNT(*) FILTER (WHERE completed_at::date >  deadline_date) AS late
FROM post_users pu JOIN posts p ON p.id = pu.post_id
WHERE pu.completed_at IS NOT NULL
GROUP BY 1,2,3;
CREATE UNIQUE INDEX ux_ums ON user_monthly_scores (tenant_id, user_id, month);
```
Migration `039_goals_scores.py`. Refresh concorrente a cada 15 min e sob demanda.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET/PUT | `/api/v1/goals/closures` | GESTOR para escrever |
| PUT | `/api/v1/users/{id}/points-goal` | GESTOR |
| GET | `/api/v1/taskscore/me?period=` | autenticado |
| GET | `/api/v1/taskscore/ranking?sort=&period=` | ADMINISTRADOR |
| GET | `/api/v1/taskscore/chart?user_id=&granularity=monthly\|daily` | autenticado |

`sort`: `points` · `volume` · `late` · `engagement`
`period`: `YYYY-MM` ou `eltv`

## 6. Front-end

**Reutiliza:** `StatCard`, `DataTable`, `BarChart`, `FormModal`
**Cria:** `TaskscorePanel`, `UserScoreCard` (foto, nome, cargo, pontos, meta, barra),
`RankingTable`, `GoalsSettingsForm`, `ScoreChart`
**Rotas:** `/home?tab=analytics`, `/settings/goals`

## 7. Regras de negócio

1. Pontos vêm de `points_earned` em `post_users` — congelados na conclusão, imunes a mudança no catálogo.
2. Tarefa retroativa credita no mês de `completed_at`, não no mês corrente.
3. Alcance da meta = pontos ÷ `points_goal`. Sem meta → mostra "—", nunca 0%.
4. Critérios do ranking:
   - `points`: soma no período
   - `volume`: contagem de concluídas
   - `late`: concluídas depois do prazo fatal, decrescente
   - `engagement`: concluídas ÷ atribuídas no período
5. `eltv` soma desde a criação do usuário.
6. Colaborador vê o próprio desempenho; ranking completo exige ADMINISTRADOR.
7. Tarefa sem prazo fatal não conta como atrasada nem como no prazo.
8. Meta de fechamento é por grupo de ação e alimenta o widget da spec 028.
9. View materializada refresca a cada 15 min; concluir tarefa agenda refresh imediato.
10. Usuário inativo some do ranking do mês corrente, mas permanece no histórico.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | pontos somam por mês corretamente | ~0,4 s |
| integração | retroativa credita no mês certo | ~0,3 s |
| integração | mudar catálogo não altera histórico | ~0,3 s |
| integração | 4 critérios de ordenação | ~0,5 s |
| integração | ELTV soma desde a criação | ~0,3 s |
| integração | sem meta → "—" | ~0,2 s |
| integração | Colaborador não vê ranking → 403 | ~0,2 s |
| integração | sem prazo fatal não conta atraso | ~0,3 s |
| integração | refresh da view após conclusão | ~0,4 s |
| integração | inativo fora do mês corrente, presente no histórico | ~0,3 s |
| frontend | card mostra progresso da meta | ~0,4 s |
| frontend | gráfico compara atual × anterior × meta | ~0,4 s |

**Total:** ~4,0 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · View materializada com refresh concorrente · Commit `feat(039): metas, ranking e Taskscore`
