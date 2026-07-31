# 078 — BI: camada de agregação

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 077 · **Status:** ⬜ pendente

---

## 1. Objetivo

As quatro abas de BI criaram views materializadas soltas. Esta spec transforma isso em
infraestrutura: refresh coordenado, invalidação por evento, defasagem visível e degradação
graciosa quando a view está velha.

## 2. Escopo

- Registro central de agregados
- Orquestração de refresh (8 h para BI, 15 min para produtividade, 10 min para saldo)
- Invalidação por evento
- Metadados de defasagem expostos na API
- Refresh manual com throttle
- Fallback quando a view falha

## 3. Fora de escopo

- Novas métricas · Data warehouse externo (fora do escopo)

## 4. Modelo de dados

```sql
CREATE TABLE aggregate_registry (
  name TEXT PRIMARY KEY,                -- 'bi_pipeline_monthly'
  refresh_interval_seconds INTEGER NOT NULL,
  invalidate_on TEXT[] NOT NULL DEFAULT '{}',   -- eventos de domínio
  last_refresh_at TIMESTAMPTZ,
  last_refresh_duration_ms INTEGER,
  last_error TEXT,
  is_enabled BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE aggregate_refresh_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL REFERENCES aggregate_registry(name),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  rows_affected BIGINT,
  error TEXT
);
CREATE INDEX ix_refresh_log ON aggregate_refresh_log (name, started_at DESC);
```
Global, sem tenant — as views são compartilhadas e filtradas por `tenant_id` na leitura.
Migration `078_aggregate_registry.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/aggregates/status` | ADMINISTRADOR |
| POST | `/api/v1/aggregates/{name}/refresh` | GESTOR |

Toda resposta de BI passa a incluir:
```json
{ "data": {...}, "meta": { "computed_at": "...", "staleness_seconds": 1240, "is_stale": false } }
```

## 6. Front-end

**Reutiliza:** `StatCard`, `DataTable`
**Cria:** `StalenessIndicator` (relógio com tooltip "atualizado há X"), `AggregateStatusPanel`,
`RefreshButton` (com throttle visível)
**Rota:** `/settings/integrations?tab=aggregates`

## 7. Regras de negócio

1. Todo agregado é declarado no registry — view materializada fora dele reprova no teste de cobertura.
2. Intervalos: BI 8 h · produtividade e agilidade 15 min · saldo diário 10 min.
3. `REFRESH MATERIALIZED VIEW CONCURRENTLY` sempre — exige índice único, que é verificado por teste.
4. Invalidação por evento agenda refresh em até 1 min, sem bloquear a operação que disparou.
5. Eventos de invalidação: `lawsuit.closed`, `transaction.paid`, `task.completed`, `lawsuit.archived`.
6. `is_stale = true` quando a defasagem passa de 2× o intervalo configurado.
7. View com falha no último refresh serve o dado antigo **com aviso**, nunca erro — BI velho é melhor que BI ausente.
8. Refresh manual: 1 por agregado a cada 10 min por tenant.
9. Refresh que passa de 60 s gera alerta — a view precisa de otimização.
10. Refresh de todos os agregados é sequencial, nunca paralelo, para não saturar o banco.
11. Falha em um agregado não impede os outros.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| **meta** | **toda view materializada está no registry** | ~0,3 s |
| **meta** | **toda view tem índice único (exigência do concurrently)** | ~0,3 s |
| integração | refresh concorrente não bloqueia leitura | ~0,5 s |
| integração | evento agenda refresh sem bloquear | ~0,4 s |
| integração | `is_stale` a partir de 2× o intervalo | ~0,3 s |
| integração | falha serve dado antigo com aviso | ~0,4 s |
| integração | refresh manual 2× em 10 min → 429 | ~0,3 s |
| integração | refresh lento gera alerta | ~0,3 s |
| integração | falha em um não impede os outros | ~0,4 s |
| integração | `meta.staleness_seconds` em toda resposta de BI | ~0,3 s |
| frontend | indicador de defasagem com tooltip | ~0,3 s |

**Total:** ~3,8 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Nenhuma view fora do registry · Dado velho nunca vira erro · Commit `feat(078): BI — camada de agregação`
