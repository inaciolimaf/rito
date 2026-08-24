# 074 — BI: Estoque e Prospecção

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 072 · **Status:** ✅ concluída

---

## 1. Objetivo

Primeira das quatro abas de Business Intelligence: o funil comercial. Quantas oportunidades
entraram, quantas viraram contrato, e quanto do estoque está parado.

## 2. Escopo

- Indicadores: oportunidades do mês, processos ativos, arquivados, parados +120 dias, fechamentos do mês, em atendimento
- Evolução de fechamentos nos últimos 6 meses
- Resumo da carteira por fase e período
- Taxa de conversão por grupo de ação
- Relatórios filtráveis no rodapé

## 3. Fora de escopo

- Safra → 075 · Tempo → 076 · Custos → 077

## 4. Modelo de dados

```sql
CREATE MATERIALIZED VIEW bi_pipeline_monthly AS
SELECT l.tenant_id, date_trunc('month', l.created_at)::date AS month,
       l.action_group_id,
       COUNT(*) AS opportunities,
       COUNT(*) FILTER (WHERE l.closure_date IS NOT NULL) AS closed,
       COUNT(*) FILTER (WHERE l.archived_date IS NOT NULL) AS archived,
       SUM(l.case_value) AS total_case_value,
       SUM(l.fees_value) FILTER (WHERE l.closure_date IS NOT NULL) AS closed_fees
FROM lawsuits l WHERE NOT l.is_archived GROUP BY 1,2,3;
CREATE UNIQUE INDEX ux_bi_pipeline ON bi_pipeline_monthly (tenant_id, month, action_group_id);

CREATE INDEX ix_lawsuits_idle_120 ON lawsuits (tenant_id, last_movement_at)
  WHERE NOT is_archived;
```
Migration `074_bi_pipeline.py`. Refresh a cada **8 horas**, como no ADVBOX.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/bi/pipeline?from=&to=&action_group_id=` | ADMINISTRADOR |
| GET | `/api/v1/bi/pipeline/conversion?period=` | ADMINISTRADOR |
| GET | `/api/v1/bi/pipeline/portfolio?group_by=step\|period` | ADMINISTRADOR |

## 6. Front-end

**Reutiliza:** `StatCard`, `BarChart`, `DonutChart`, `DataTable`, `FilterBar`
**Cria:** `BiTabs` (navegação entre as 4 abas), `PipelinePanel`, `ConversionFunnel`,
`SixMonthTrend`, `StaleWarning`, `BiRefreshIndicator`
**Rota:** `/reports?tab=pipeline`

## 7. Regras de negócio

1. **Oportunidades do mês** = processos criados no mês, qualquer fase.
2. **Processos ativos** = não arquivados, nas fases administrativa, consultoria, judicial, recursal ou execução.
3. **Arquivados** = com `archived_date` preenchida.
4. **Parados +120 dias** = `last_movement_at` mais antigo que 120 dias **ou** nulo, entre os ativos. É o indicador de alerta da aba.
5. **Fechamentos do mês** = `closure_date` no mês, com variação vs mês anterior e série de 6 meses.
6. **Em atendimento** = processos nas fases marketing, negociação ou consultoria.
7. **Taxa de conversão** = fechados ÷ oportunidades, por grupo de ação, no período.
8. Gráficos vêm da view materializada (até 8 h de defasagem, sinalizada). Os **relatórios do rodapé são tempo real**.
9. Aba exige ADMINISTRADOR ou GESTOR.
10. Grupo sem movimento aparece zerado, não some.
11. Divisão por zero na conversão → exibe "—", nunca `NaN` ou 0%.
12. Aviso claro: qualidade do indicador depende do CRM alimentado.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | 6 indicadores com seed determinístico | ~0,6 s |
| integração | parados +120 dias inclui `last_movement_at` nulo | ~0,4 s |
| integração | fechamentos com variação e série de 6 meses | ~0,4 s |
| integração | conversão por grupo | ~0,4 s |
| integração | conversão com zero oportunidades → "—" | ~0,2 s |
| integração | gráfico usa a view; relatório é tempo real | ~0,4 s |
| integração | Colaborador → 403 | ~0,2 s |
| integração | grupo sem movimento aparece zerado | ~0,2 s |
| integração | refresh da view atualiza os números | ~0,4 s |
| frontend | indicador de defasagem visível | ~0,3 s |

**Total:** ~3,5 s

## 9. Descobertas

1. **`lawsuits` não tem coluna `action_group_id`.** O SQL literal do §4 referencia
   `l.action_group_id`, mas desde a spec 022 (regra 2) o grupo é derivado do tipo de ação
   e nunca reside no processo. A view faz `JOIN lawsuit_types lt ON lt.id =
   l.lawsuit_type_id` para chegar ao grupo — única alteração estrutural em relação ao
   SQL da spec; cardenalidade e semântica preservadas.
2. **A view é coorte de criação — e a regra 5 não é derivável dela.**
   `bi_pipeline_monthly` agrupa por mês de `created_at`; "fechamentos do mês" (regra 5) é
   por `closure_date`, que não tem relação com o mês de criação. Por isso o repository
   divide o trabalho: **da view** saem oportunidades do mês (regra 1), o funil e a taxa de
   conversão (regra 7); **em tempo real** ficam ativos/parados/em atendimento/arquivados
   (regras 2, 3, 4, 6 — estoque é fotografia do agora, não coorte), fechamentos com
   variação e série de 6 meses (regra 5) e o resumo da carteira do rodapé (regra 8:
   "relatórios do rodapé são tempo real").
3. **Bug latente na migration 073, descoberto por causa do banco fresco deste ciclo:**
   `012_users_full` já cria `accounts.track_access_logs` e `073_access_logs` adiciona a
   mesma coluna de novo — `alembic upgrade head` do zero quebrava com
   `DuplicateColumnError` (o ambiente anterior tinha drift completado à mão, então o
   conflito nunca aparecia). Correção pós-commit em 073: guarda de idempotência via
   inspeção de coluna no upgrade/downgrade, preservando o schema final exatamente como
   antes. Exceção documentada à regra "nunca editar migration commitada" — sem ela, nem
   CI limpo nem `make test` com `rito_test` vazio sobem a cadeia.
4. **`/reports?tab=pipeline` convive com `?panel=`.** A ReportsPage (071/072) navegava
   por `panel=`; a convenção extraída na refatoração 070 (TabBar) é `tab=`. A página
   passou a reconhecer `tab` com valor de BI (pipeline/safra/tempo/custos) como seleção
   do painel "BI" (nova aba externa), e o `BiTabs` gerencia o `tab=` entre as 4 abas de
   BI — safra/tempo/custos ficam visíveis mas desabilitadas até as specs 075–077.
   `panel=` continua funcionando como antes.
5. **Fases fixas por id, não por nome.** Os conjuntos das regras 2 e 6 usam os ids do
   seed imutável da migration 015 (`ACTIVE_STEP_IDS = (3,4,5,6,7)`,
   `IN_SERVICE_STEP_IDS = (1,2,3)`) — mesma convenção já usada em `test_lawsuits.py`
   (`_MARKETING_STEP_ID = 1`). Consultoria (3) pertence aos dois conjuntos de propósito:
   é fase ativa (regra 2) e também "em atendimento" (regra 6).
6. **Refresh global da matview é seguro sob pytest-xdist.** Cada teste trabalha num
   tenant próprio e a view barreira (`bi_pipeline_monthly_visible`, filtro
   `current_setting('app.tenant_id')` embutido) isola as leituras — o REFRESH
   CONCURRENTLY roda como superusuário em AUTOCOMMIT, fora da transação de qualquer
   teste, sem contaminar vizinhos. Mesmo padrão da 071; não houve necessidade de
   artifício novo de isolamento.
7. **Teste de isolamento de tenant além do plano.** CLAUDE.md §4 exige prova de
   isolamento para estrutura nova com dado de tenant; como a matview não tem RLS (o
   isolamento é da view barreira), foi adicionado
   `test_tenant_a_nao_ve_funil_de_tenant_b` — 11 testes de integração no total, não 9.
8. **`group_by=period` definido nesta spec.** O §2 diz "resumo da carteira por fase e
   período" sem definir o eixo; implementado como ativos por **mês de criação** (últimos
   12 meses, coorte de entrada da carteira), tempo real. `group_by=step` devolve as 9
   fases sempre, mesmo zeradas (mesmo espírito da regra 10).
9. **Contenção do host no gate de 300 s.** Neste ciclo o host dind (Postgres remoto)
   e o host local operaram com load average 8–12 em 4 cores por carga de outros
   processos; o wall-clock medido ficou em ~447 s com as 3 suítes verdes
   (993 backend / 194 frontend / 10 e2e), contra 293 s da medição anterior — o acréscimo
   da spec é ~10 s (11 testes de integração + 3 de frontend), o resto é degradação
   ambiental. Flakes de timeout sob contenção (`test_inbox_perf`, formulários de
   frontend) passam isolados e em rodadas com o host mais vazio.

## 10. Definição de pronto

- [x] Escopo implementado, nada além (migration 074, worker + beat 8h, 3 endpoints, 6 componentes de front na rota `/reports?tab=pipeline`)
- [x] Todas as regras de negócio com teste (1–12; regra 11 com caso dedicado de divisão por zero → `null`/"—")
- [x] Teste de isolamento por tenant (`test_tenant_a_nao_ve_funil_de_tenant_b` — ver 9.7)
- [x] `make test` com as 3 suítes verdes; wall-clock acima do orçamento por contenção do host — ver 9.9
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Componentes reutilizados conforme §6 (StatCard, BarChart, DonutChart, DataTable, FilterBar); nenhum novo componente de domínio (BiTabs é específico do BI, 1 consumidor)
- [x] `ROADMAP.md` atualizado para ✅
- [ ] Commit `feat(074): BI — estoque e prospecção` (neste ciclo o commit fica com o orquestrador)
