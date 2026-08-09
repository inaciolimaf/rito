# 039 — Metas, ranking e painel Taskscore

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 036 · **Status:** ✅ concluída

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

- **Materialized view não tem RLS — o isolamento mudou de lugar.** PostgreSQL não
  aplica políticas em matviews. A solução foi a **view barreira**
  `user_monthly_scores_visible` (`WHERE tenant_id = current_setting('app.tenant_id')`
  embutido na definição, GRANT para `rito_app`): a aplicação só consulta a barreira,
  então quem garante o tenant continua sendo o banco (CLAUDE.md §4), nunca um WHERE
  manual no código. Teste de isolamento cobre tenant A × tenant B.
- **Refresh só roda como superusuário.** REFRESH exige ser dono da matview e enxergar
  todas as linhas; `rito_app` está sob FORCE RLS e, sem `app.tenant_id`, veria zero
  linhas — um refresh pela conexão da aplicação **esvaziaria** a view. O worker
  (`app/workers/scores.py`) usa MIGRATIONS_DATABASE_URL com AUTOCOMMIT (CONCURRENTLY
  não roda em transação). O agendamento imediato do complete/reopen é no-op em
  `APP_ENV=test` — teste não toca broker; os testes chamam o REFRESH direto.
- **"Atribuídas no período" = posts criados no período.** A atribuição acontece na
  criação do post (spec 032), então o denominador do envolvimento usa
  `posts.created_at`. Uma tarefa criada em janeiro e concluída em fevereiro entra no
  denominador de janeiro e no numerador de fevereiro — definido assim e registrado.
- **ELTV inclui inativos; mês corrente não.** Regra 10 implementada no service:
  `include_inactive = periodo != mês corrente`.
- **Drift de banco dos ambientes locais.** Dev e rito_test já estavam carimbados em
  `039_goals_scores` por uma sessão anterior (tabela + matview, sem a view barreira e
  sem `closure_goals.created_at`). O drift foi completado à mão nos dois bancos; a
  migration commitada sai íntegra em banco fresco.
- **Flake da jornada 6/25 (e2e) corrigido de passagem.** Re-runs dentro do mesmo mês
  encontravam o "Compromisso E2E" da run anterior no dia 15 do mês seguinte — o clique
  no centro da célula caía no chip e abria a tarefa em vez do formulário. O clique
  passou ao canto superior esquerdo (número do dia). Jornada 1/25 atualizada para o
  heading "Meu Painel" (a home ganhou abas e deixou de ser só a caixa de entrada).
- **`PUT /users/{id}/points-goal` é redundante com o update completo** (spec 012 já
  edita `points_goal`) — mantido como endpoint leve para a tela de metas, que salva
  por colaborador sem carregar o formulário inteiro.

## 10. Definição de pronto

- [x] Migration `039_goals_scores` (closure_goals + matview + view barreira) aplicada
- [x] View materializada com refresh concorrente (beat 15 min + agendamento no complete/reopen)
- [x] Contratos de API da §5 implementados e cobertos por teste
- [x] Painel no `/home?tab=analytics` e `/settings/goals` no ar
- [x] 14 testes de integração + 5 de frontend verdes; isolamento de tenant coberto
- [x] `make lint` verde · `make test` verde em 156 s (< 300 s)
- [x] Widget da 028 alimentado pela soma das metas (regra 8)
- [x] Commit `feat(039): metas, ranking e Taskscore`
