# 028 — Processos: dashboard

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 027 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(028): processos — dashboard`
