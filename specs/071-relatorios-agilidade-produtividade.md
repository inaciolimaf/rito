# 071 — Relatórios: Agilidade e Produtividade

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 039 · **Status:** ⬜ pendente

---

## 1. Objetivo

Os dois painéis que o gestor abre para saber se a equipe está entregando no prazo e quem está
carregando o time.

## 2. Escopo

- Painel de Agilidade: concluídas em dia, em atraso, pendentes
- Tarefas com mais atraso e colaboradores com mais atraso
- Agilidade geral: média de cumprimento e média de atraso
- Painel de Produtividade: atribuídas, concluídas, atrasadas, prazo fatal em 5 dias
- Gráfico semanal de atribuídas × concluídas
- Ranking individual com os 4 critérios de 039

## 3. Fora de escopo

- Relatórios tabulares → 072 · BI → 074–077

## 4. Modelo de dados

Nenhuma tabela nova. Estende `user_monthly_scores` (039) e adiciona view de agilidade:

```sql
CREATE MATERIALIZED VIEW agility_daily AS
SELECT tenant_id, date_trunc('day', completed_at)::date AS day,
       COUNT(*) FILTER (WHERE deadline_date IS NULL OR completed_at::date <= deadline_date) AS on_time,
       COUNT(*) FILTER (WHERE deadline_date IS NOT NULL AND completed_at::date > deadline_date) AS late,
       AVG(EXTRACT(EPOCH FROM (completed_at - created_at))/86400) AS avg_days_to_complete,
       AVG(GREATEST(completed_at::date - deadline_date, 0)) FILTER (WHERE deadline_date IS NOT NULL) AS avg_delay_days
FROM post_users pu JOIN posts p ON p.id = pu.post_id
WHERE pu.completed_at IS NOT NULL
GROUP BY 1,2;
CREATE UNIQUE INDEX ux_agility_daily ON agility_daily (tenant_id, day);
```
Migration `071_agility_view.py`. Usa o `MaterializedAggregate` de 060.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/reports/agility?from=&to=&user_id=` | ADMINISTRADOR |
| GET | `/api/v1/reports/productivity?month=&user_id=` | ADMINISTRADOR |
| GET | `/api/v1/reports/productivity/weekly?week=` | ADMINISTRADOR |
| GET | `/api/v1/reports/most-delayed?limit=10` | ADMINISTRADOR |

## 6. Front-end

**Reutiliza:** `StatCard`, `DonutChart`, `BarChart`, `DataTable`, `FilterBar`, `UserScoreCard`
**Cria:** `AgilityPanel`, `ProductivityPanel`, `WeeklyChart`, `DelayedTasksCard`,
`DelayedUsersCard`
**Rota:** `/reports` (painel superior)

## 7. Regras de negócio

1. **Em dia** = concluída até `deadline_date`. Tarefa **sem** prazo fatal conta como em dia — não penalize quem não tinha prazo.
2. **Em atraso** = concluída depois do prazo fatal.
3. **Pendente** = não concluída, independentemente de estar vencida.
4. Agilidade geral: média de dias entre criação e conclusão, e média de dias de atraso entre as atrasadas.
5. Prazo fatal nos próximos 5 dias conta dias corridos a partir de hoje.
6. Gráfico semanal cobre segunda a sexta da semana corrente.
7. Tarefa privada entra nos agregados sem expor conteúdo.
8. Colaborador vê só os próprios números; ADMINISTRADOR vê todos.
9. Sem dado no período, o painel mostra estado vazio explicativo — não gráfico zerado sem contexto.
10. View refresca a cada 15 min; a defasagem é sinalizada.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | em dia, em atraso e pendente com seed determinístico | ~0,5 s |
| integração | **sem prazo fatal conta como em dia** | ~0,3 s |
| integração | médias de cumprimento e de atraso | ~0,4 s |
| integração | prazo fatal em 5 dias corridos | ~0,3 s |
| integração | gráfico semanal seg–sex | ~0,3 s |
| integração | privada agrega sem expor conteúdo | ~0,3 s |
| integração | Colaborador vê só os próprios | ~0,3 s |
| integração | período vazio → estado vazio | ~0,2 s |
| integração | **budget: painel ≤ 4 statements** | ~0,4 s |
| frontend | painel de agilidade renderiza | ~0,4 s |
| frontend | ranking com os 4 critérios | ~0,4 s |

**Total:** ~3,8 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(071): relatórios — agilidade e produtividade`
