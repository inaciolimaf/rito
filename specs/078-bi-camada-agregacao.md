# 078 — BI: camada de agregação

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 077 · **Status:** ✅ concluída

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

- **`aggregate_registry.name` ficou UNIQUE, não PRIMARY KEY.** A `Base` da casa
  (`app/core/models.py`) já injeta `id` UUID como PK em todo modelo — manter o DDL
  literal da spec exigiria uma segunda `DeclarativeBase` só para duas tabelas. A
  unicidade de `name` (o que o FK do log e o refresh usam) está preservada.
- **Envelope `meta` é aditivo, sem aninhar `data`.** A especificação exemplifica
  `{ "data": ..., "meta": ... }`, mas as 14 respostas de BI já tinham contrato plano
  consumido por testes e pelos painéis do frontend. Cada resposta ganhou o campo
  `meta: {computed_at, staleness_seconds, is_stale}` no topo, ao lado dos campos
  existentes — contrato anterior intacto, regra §5 cumprida (`meta.staleness_seconds`
  em toda resposta de BI). Endpoints atrelados a view derivam `meta` do registry;
  endpoints de tempo real (portfolio, success-rate, success-trend) respondem
  `staleness_seconds: 0, is_stale: false`. O `staleness_hint` textual das specs
  074–077 foi mantido.
- **Invalidação por evento usa task Celery com countdown** (não há barramento de
  eventos no código — o padrão existente era `schedule_*_refresh` por domínio).
  `schedule_aggregate_refresh(event)` em `app/workers/aggregates.py` mapeia os 4
  eventos da regra 5 para as views afetadas (`EVENT_TO_VIEWS`) e agenda
  `refresh_aggregate_by_name` com countdown de 5 s (≤ 1 min, cobre o commit da
  request); broker fora nunca derruba a operação, e em `APP_ENV=test` é no-op
  (CLAUDE.md §3). Os hooks antigos (`schedule_scores_refresh`,
  `schedule_account_balances_refresh`) foram substituídos por este caminho único —
  reabrir tarefa e estornar lançamento disparam os mesmos eventos (`task.completed`,
  `transaction.paid`), pois desfazem a mutação. `lawsuit.closed`/`lawsuit.archived`
  disparam na TRANSIÇÃO (update, create já fechado/arquivado — importação — e soft
  delete). `EVENT_TO_VIEWS` espelha o `invalidate_on` do seed da migration 078 —
  mudou um, muda o outro (há teste de consistência).
- **Os 8 beats individuais viraram um único tick por minuto**
  (`aggregates-refresh-due`), que refresca sequencialmente (regra 10) só as views
  vencidas conforme o intervalo do registry — assim o intervalo virou dado
  (ajustável sem deploy) e todo refresh passa a ter log, duração e alerta >60 s
  (regra 9, `integration_alerts` com `tenant_id` NULL, deduplicado por view).
  Os workers de domínio (`bi_pipeline.py`, `scores.py`, …) mantêm só o wrapper
  async que os testes chamam direto.
- **Refresh manual é inline** (não enfileira): o endpoint executa
  `refresh_aggregate` com a MIGRATIONS_DATABASE_URL e devolve o status atualizado;
  falha volta como `last_error` no corpo, nunca como erro HTTP (regra 7). Throttle
  de 1/10 min por tenant via Redis (`check_and_increment`, mesmo padrão do
  recálculo de estagnação da 052).
- **Leitura do registry pela role de aplicação** usa `populate_existing` no
  repository: o refresh manual atualiza a linha por outra conexão (superusuário) e
  a identity map da request devolveria o estado de antes do refresh.
- **Testes de lentidão e falha sem sleep nem quebra de banco:** o relógio do worker
  (`monotonic`) e o SQL de refresh (`_refresh_view`) são pontos de monkeypatch —
  o teste de alerta simula 61 s e o de falha força exceção por nome de view.
- Custo medido: os 12 testes novos (2 meta + 9 integração + 1 frontend com 4 casos)
  rodam em ~5 s no backend e ~0,3 s no frontend; suíte completa segue < 300 s.

## 10. Definição de pronto

Checklist padrão · Nenhuma view fora do registry · Dado velho nunca vira erro · Commit `feat(078): BI — camada de agregação`
