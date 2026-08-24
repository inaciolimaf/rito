# 076 — BI: Tempo e Honorários

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 075 · **Status:** ✅ concluída

---

## 1. Objetivo

Quanto tempo se investe e quanto valor se gera em cada processo, ao longo do ciclo completo.
Responde a pergunta que define precificação: "esse tipo de ação compensa?".

## 2. Escopo

- Média de honorários por processo e média mensal
- **Tempo perdido**: meses de processo sem receita
- Quatro ciclos: prospecção, produção, execução, rotação completa
- Tempo médio por fase e por grupo de ação
- Rentabilidade mensal por tipo de ação
- Relatórios filtráveis

## 3. Fora de escopo

- Custos → 077 · Precificação sugerida por IA → 089

## 4. Modelo de dados

```sql
CREATE MATERIALIZED VIEW bi_lawsuit_cycles AS
SELECT l.tenant_id, l.id AS lawsuit_id, l.action_group_id, l.lawsuit_type_id,
       l.outcome, l.closure_date, l.fees_value,
       -- prospecção: criação → fechamento do contrato
       (l.closure_date - l.created_at::date) AS prospecting_days,
       -- produção: fechamento → trânsito em julgado
       (l.transit_date - l.closure_date) AS production_days,
       -- execução: trânsito → arquivamento
       (l.archived_date - l.transit_date) AS execution_days,
       -- rotação completa: criação → arquivamento
       (l.archived_date - l.created_at::date) AS full_cycle_days,
       COALESCE((SELECT SUM(t.amount) FROM transactions t
                 WHERE t.lawsuit_id = l.id AND t.kind='RECEITA'
                   AND NOT t.is_internal AND t.payment_date IS NOT NULL), 0) AS revenue
FROM lawsuits l WHERE l.closure_date IS NOT NULL;
CREATE UNIQUE INDEX ux_bi_cycles ON bi_lawsuit_cycles (tenant_id, lawsuit_id);
```
Migration `076_bi_cycles.py`. Refresh a cada 8 h.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/bi/time-fees?outcome=&from=&to=&action_group_id=` |
| GET | `/api/v1/bi/time-fees/by-group` |
| GET | `/api/v1/bi/time-fees/by-type?lawsuit_type_id=` |
| GET | `/api/v1/bi/time-fees/lost-time` |

## 6. Front-end

**Reutiliza:** `StatCard`, `BarChart`, `DataTable`, `FilterBar`, `MoneyField`
**Cria:** `TimeFeesPanel`, `CycleBarChart` (4 cores: verde prospecção, azul claro produção,
azul escuro execução, vermelho rotação), `LostTimeCard`, `ProfitabilityTable`
**Rota:** `/reports?tab=time-fees`

## 7. Regras de negócio

1. Os 4 ciclos, em dias:
   - **Prospecção:** criação → `closure_date`
   - **Produção:** `closure_date` → `transit_date`
   - **Execução:** `transit_date` → `archived_date`
   - **Rotação completa:** criação → `archived_date`
2. Ciclo com data faltando fica **nulo**, não zero. Zero significa "no mesmo dia" e é diferente de "não sei".
3. Média de honorários = soma de `fees_value` ÷ processos no filtro.
4. Média mensal = honorários ÷ meses de duração do processo. Processo longo e barato derruba a média — é justamente o que o indicador quer mostrar.
5. **Tempo perdido** = soma dos meses de processos com `revenue = 0` e ciclo maior que zero.
6. `revenue` vem de lançamentos de receita **pagos**, não internos, vinculados ao processo.
7. Filtro por resultado (todos, ganhos, perdidos) recalcula tudo.
8. Rentabilidade mensal por tipo = média de (`fees_value` ÷ meses) dos processos daquele tipo.
9. Tipo com menos de 5 processos exibe aviso de amostra pequena.
10. Gráfico por grupo mostra os 4 ciclos lado a lado.
11. Exige ADMINISTRADOR ou GESTOR e `financial_access ≥ READ_ONLY` — a aba mostra dinheiro.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | **os 4 ciclos com datas completas** | ~0,3 s |
| unit | ciclo com data faltando é nulo, não zero | ~0,2 s |
| integração | média de honorários por processo | ~0,3 s |
| integração | média mensal penaliza processo longo e barato | ~0,4 s |
| integração | tempo perdido soma só os sem receita | ~0,4 s |
| integração | `revenue` ignora não pago e interno | ~0,4 s |
| integração | filtro por resultado recalcula | ~0,4 s |
| integração | rentabilidade por tipo | ~0,4 s |
| integração | menos de 5 processos → aviso | ~0,2 s |
| integração | `financial_access = NONE` → 403 | ~0,3 s |
| frontend | gráfico com as 4 cores dos ciclos | ~0,4 s |

**Total:** ~3,7 s

## 9. Descobertas

1. **Mesma divergência estrutural das 074/075: `lawsuits` não tem `action_group_id`.**
   O SQL literal do §4 referencia a coluna, mas desde a spec 022 (regra 2) o grupo é
   derivado do tipo de ação — a view faz `JOIN lawsuit_types lt ON lt.id =
   l.lawsuit_type_id`, cardinalidade e semântica preservadas. Já a tabela
   `transactions` existe com exatamente as colunas citadas no §4 (spec 056:
   `kind`/`is_internal`/`payment_date`/`lawsuit_id`/`amount`) — nenhum ajuste de nome
   necessário, ao contrário do que o briefing sugeria verificar.
2. **A view é por processo, não agregada.** Diferente de `bi_pipeline_monthly` (074)
   e `bi_vintage` (075), `bi_lawsuit_cycles` tem uma linha por processo fechado e os 4
   ciclos já calculados — as agregações (médias, somas) ficam nas queries do repository
   sobre a view barreira, o que permite os filtros da regra 7 sem refresh. Como todo o
   painel deriva da matview, **todos** os 4 endpoints carregam a defasagem de 8 h e o
   `staleness_hint` — não há consulta tempo real nesta spec.
3. **Regra 2 vem de graça do Postgres — e do NULLIF.** Subtração de datas com NULL
   resulta NULL, exatamente "nulo ≠ zero". Na média mensal (regra 4) e na rentabilidade
   (regra 8), `fees_value ÷ (full_cycle_days ÷ 30)` usaria divisão por zero quando a
   rotação é zero (criação e arquivamento no mesmo dia): o `NULLIF(full_cycle_days, 0)`
   torna a expressão NULL e o AVG a descarta — processo com rotação zero não entra na
   média mensal (dividir por zero dias daria ∞, valor inventado). A definição canônica
   dos ciclos em Python (`compute_cycle_days` no service) existe para os 2 testes de
   unidade do plano; o SQL da matview espelha a mesma aritmética.
4. **`outcome` na view barreira exige o tipo enum no Table Core.** Declarada como
   `String`, o filtro `outcome = 'GANHO'` quebrava com `operator does not exist:
   lawsuit_outcome = character varying` — a coluna foi declarada com
   `PGENUM(LawsuitOutcome, create_type=False)` e o filtro passa o membro do enum.
5. **Recorte vazio → médias None, nunca zero.** A spec define nulo para ciclo
   (regra 2) mas não diz o que `avg_fees` vale sem processos no filtro; adotado o
   mesmo idioma da regra 11 das specs 074/075 (divisão por zero → None → "—" na UI).
   Honorários não declarados (`fees_value` NULL) contam como zero no numerador e
   entram no denominador — leitura literal da regra 3 ("soma ÷ processos no filtro").
6. **Filtros só no endpoint principal.** O §5 declara `outcome`/`from`/`to`/
   `action_group_id` só em `/bi/time-fees`; `by-group`, `by-type` (só
   `lawsuit_type_id`) e `lost-time` não recebem os demais filtros. A regra 7 ("filtro
   por resultado recalcula tudo") foi coberta no endpoint principal, que é quem tem o
   parâmetro no contrato.
7. **Tab da URL é `time-fees`, não `tempo`.** A 074 criou o placeholder `?tab=tempo`
   no BiTabs; a spec 076 fixa a rota `/reports?tab=time-fees`. O valor da aba foi
   renomeado (label continua "Tempo e Honorários") e a aba foi habilitada; `custos`
   segue desabilitada até a 077 — mesma decisão da 075 com `safra`→`vintage` (§9.6).
8. **`CycleBarChart` não usa o `BarChart` de domínio** — o BarChart tem uma série por
   rótulo e a regra 10 pede 4 ciclos lado a lado por grupo; barras agrupadas em SVG
   puro com as 4 cores fixas da spec (verde/azul claro/azul escuro/vermelho), lacuna
   nos ciclos nulos (mesmo motivo do SuccessTrendChart da 075). `MoneyField` (§6) não
   coube: o painel é somente leitura, sem formulário — dinheiro sai por `formatBrl`.
9. **Testes além do plano, de novo.** CLAUDE.md §4 exige prova de isolamento para
   estrutura nova com dado de tenant; a matview não tem RLS (o isolamento é da view
   barreira `bi_lawsuit_cycles_visible`), então `test_tenant_a_nao_ve_ciclos_de_
   tenant_b`. E `test_ciclos_por_grupo_lado_a_lado` cobre a regra 10 no backend (o
   plano só a cobria no frontend) e a regra 2 no SQL (AVG ignora nulos). Total: 2
   unitários + 11 de integração + 3 de frontend.
10. **Minuto 36 no beat.** Os refreshes de 8 h das 074/075 rodam nos minutos 21 e 51;
    o da 076 ficou no minuto 36 para os três REFRESH CONCURRENTLY não concorrerem
    (mesmo cuidado documentado na 075).

## 10. Definição de pronto

- [x] Escopo implementado, nada além (migration 076, worker + beat 8h no minuto 36, 4 endpoints com dupla permissão, 4 componentes de front na rota `/reports?tab=time-fees`)
- [x] Todas as regras de negócio com teste (1–11; regra 2 com caso de unidade dedicado e verificação no SQL via regra 10 — ver 9.9)
- [x] Nulo distinguido de zero (ciclo sem data → NULL na view e na API; "—" na UI)
- [x] Dupla permissão testada (Gestor com `financial_access=NONE` e Colaborador com FULL → 403 nos 4 endpoints)
- [x] Teste de isolamento por tenant (`test_tenant_a_nao_ve_ciclos_de_tenant_b` — ver 9.9)
- [x] `make test` com as 3 suítes verdes — ver test-timing.json
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Componentes reutilizados conforme §6 (StatCard nos indicadores, DataTable na ProfitabilityTable, FilterBar nos filtros); BarChart e MoneyField não couberam — ver 9.8
- [x] `ROADMAP.md` atualizado para ✅
- [ ] Commit `feat(076): BI — tempo e honorários` (neste ciclo o commit fica com o orquestrador)
