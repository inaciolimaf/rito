# 028 — Processos: dashboard

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 027 · **Status:** ✅ concluída

---

## 1. Objetivo

Painel de topo da tela de processos: quanto o escritório tem em andamento, quanto fechou e como
está distribuído no funil.

## 2. Escopo

- Cards: processos ativos, fechamentos do mês (com variação), arquivados no mês
- Gráfico de volume por fase
- Widget de meta de fechamentos (a meta em si vem em 039)
- Endpoint de agregação com cache curto

## 3. Fora de escopo

- BI aprofundado → 074–077 · Metas → 039

## 4. Modelo de dados

Nenhuma tabela nova. Agregação sobre `lawsuits`, usando os índices de 024 e 027.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/lawsuits/stats?month=YYYY-MM` |

```json
{ "active": {"value":128,"delta_pct":4.2},
  "closed_this_month": {"value":12,"delta_pct":-8.3,"previous":13},
  "archived_this_month": {"value":5,"delta_pct":0},
  "volume_by_step": [{"step":"Judicial","count":64,"pct":50.0}],
  "closure_goal": {"target":20,"achieved":12,"pct":60.0} }
```

## 6. Front-end

**Reutiliza:** `StatCard`, `BarChart`, `DonutChart`, `EmptyState`
**Cria:** `LawsuitStatsPanel`, `GoalProgress`
**Rota:** topo de `/lawsuits`, recolhível

## 7. Regras de negócio

1. Variação compara com o mesmo período do mês anterior.
2. Mês anterior zerado e atual positivo → variação exibida como "novo", não como ∞.
3. Ativos = não arquivados e sem `archived_date`.
4. Fechamentos do mês contam por `closure_date`, não por `created_at`.
5. Volume por fase considera só ativos e soma 100%.
6. Meta não configurada → widget convida a configurar (link para 039).
7. Cache de 5 minutos por tenant e mês, invalidado ao criar, fechar ou arquivar processo.
8. Cards clicáveis levam à listagem já filtrada.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | stats com seed determinístico | ~0,5 s |
| integração | variação vs mês anterior | ~0,3 s |
| integração | mês anterior zerado → "novo" | ~0,2 s |
| integração | volume por fase soma 100% | ~0,3 s |
| integração | cache invalida ao fechar processo | ~0,4 s |
| integração | **budget: stats ≤ 4 statements** | ~0,3 s |
| frontend | card sem meta mostra convite | ~0,3 s |
| frontend | clicar no card navega com filtro | ~0,3 s |

**Total:** ~2,6 s

## 9. Descobertas

- **"Ativos" histórico é aproximado.** `is_archived` não tem data — o `previous` do card
  de ativos é reconstruído por `created_at`/`archived_date`. Um soft-delete (DELETE da
  API) sem `archived_date` some do valor atual mas continua contado no "mês anterior".
  Aceito: o número histórico é uma referência de tendência, não um fato contábil. Se a
  spec 030 quiser precisão, a trilha é materializar `archived_at` no soft-delete.
- **Fechado sem arquivamento continua "ativo"** (regra 3 + visão `active` da 027): o
  card de ativos inclui processos com `closure_date` e sem `archived_date`. Coerente com
  a listagem — ciclo de vida do ADVBOX só tira do ativo no arquivamento.
- **`delta_pct` None é "novo"** (regra 2). A UI traduz None+valor>0 para "novo este mês"
  e None+valor=0 para "sem movimento" — nunca ∞ nem "+100%" inventado (o cálculo local
  do `StatCard` não saberia distinguir; por isso o card recebe o rótulo pronto via a
  nova prop `variation`, sem mudar o comportamento default — os 3 testes antigos do
  `StatCard` passaram sem edição).
- **Cache:** Redis 5 min por `(tenant, mês)`; invalidação no create/update/delete toca o
  mês corrente **e** os meses das datas de ciclo (fechamento retroativo muda o card do
  mês passado). `setex` está deprecado no redis-py ≥ 2.6 — usar `set(..., ex=)`.
- **Protocol estrutural:** para o `Redis` satisfazer `StatsCache` sem cast, o Protocol
  precisa espelhar as assinaturas do redis-py (parâmetro `name`, retorno `Awaitable`,
  não `async def`/`Coroutine`).
- **DonutChart não usado.** A spec listava BarChart+DonutChart como reuso; com 9 fases,
  o donut vira roleta de cores ilegível — o volume por fase ficou só no BarChart
  horizontal com o percentual no rótulo.
- **Orçamento folgado:** 2 statements (agregados condicionais numa query + volume por
  fase noutra), abaixo do teto de 4.
- `/lawsuits/stats` precisa ser registrado **antes** de `/lawsuits/{lawsuit_id}` no
  router — senão "stats" casa como UUID e vira 422 de path.

## 10. Definição de pronto

- [x] Spec escrita seguindo o template (já existia do ciclo de planejamento)
- [x] Escopo implementado: endpoint `/lawsuits/stats` com cache, 3 cards + volume por
      fase + widget de meta, painel recolhível no topo de `/lawsuits`
- [x] Testes do plano escritos e verdes (8 backend, 3 frontend)
- [x] `make lint` verde
- [x] `make test` verde em 81 s (< 120 s)
- [x] `test-timing.json` atualizado
- [x] ROADMAP marcado ✅
- [x] Commit `feat(028): processos — dashboard`
