# 096 — Busca global

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 027 · **Status:** ⬜ pendente

---

## 1. Objetivo

O backend da busca do header, cuja UI ficou pronta em 008. Atalho `/`, três facetas, resposta
em menos de 200 ms.

## 2. Escopo

- Busca unificada em contatos, processos e tarefas
- Facetas: Tudo · Pessoas · Processos
- Ranking por relevância
- Busca por número CNJ com e sem máscara
- Busca por CPF/CNPJ
- Histórico de buscas recentes

## 3. Fora de escopo

- Busca semântica (sem RAG) · Busca em conteúdo de documento → 064 tem a sua

## 4. Modelo de dados

```sql
ALTER TABLE customers ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    to_tsvector('portuguese', unaccent(coalesce(name,'') || ' ' ||
      coalesce(identification,'') || ' ' || coalesce(email,'')))
  ) STORED;
CREATE INDEX ix_customers_fts ON customers USING gin (search_vector);

ALTER TABLE lawsuits ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    to_tsvector('portuguese', unaccent(coalesce(process_number,'') || ' ' ||
      coalesce(protocol_number,'') || ' ' || coalesce(folder,'') || ' ' || coalesce(notes,'')))
  ) STORED;
CREATE INDEX ix_lawsuits_fts ON lawsuits USING gin (search_vector);

CREATE TABLE search_history (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  query TEXT NOT NULL,
  clicked_type TEXT, clicked_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_search_history ON search_history (user_id, created_at DESC);
```
Colunas geradas — o índice se mantém sozinho, sem trigger. Migration `096_search.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/search?q=&facet=all\|people\|lawsuits&limit=10` |
| GET | `/api/v1/search/recent?limit=5` |
| POST | `/api/v1/search/click` → `{query, type, id}` |

```json
{ "people":   { "items": [...], "total": 12 },
  "lawsuits": { "items": [...], "total": 3 },
  "tasks":    { "items": [...], "total": 0 },
  "took_ms": 45 }
```

## 6. Front-end

**Reutiliza:** `GlobalSearch` (de 008), `EmptyState`
**Cria:** `SearchResultGroup`, `SearchResultItem` (com destaque do termo),
`RecentSearches`
**Rota:** overlay global

## 7. Regras de negócio

1. Mínimo de 2 caracteres; abaixo disso, mostra as buscas recentes.
2. Detecção do tipo de entrada:
   - Só dígitos com 11 ou 14 → busca por CPF/CNPJ, exata
   - Padrão CNJ (com ou sem máscara) → busca por número de processo, exata
   - Resto → full-text
3. Full-text usa `tsvector` em português com `unaccent`.
4. Ranking: correspondência exata primeiro, depois `ts_rank`, depois recência.
5. Máximo de 10 resultados por faceta na resposta rápida; "ver todos" leva à listagem filtrada.
6. Só resultados que o usuário pode ver — RLS mais RBAC. Tarefa privada de terceiro nunca aparece.
7. Debounce de 250 ms no cliente.
8. Clique registra em `search_history`, alimentando as recentes e a ordenação futura.
9. Histórico é por usuário, limitado às 20 últimas.
10. **Meta de performance: p95 abaixo de 200 ms** com 100.000 contatos e 100.000 processos.
11. `took_ms` volta na resposta, para monitorar.
12. Busca vazia não é erro — devolve recentes.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | full-text encontra por nome parcial sem acento | ~0,3 s |
| integração | CPF com e sem máscara encontra | ~0,3 s |
| integração | CNJ com e sem máscara encontra | ~0,3 s |
| integração | facetas retornam grupos separados | ~0,3 s |
| integração | exata vem antes de parcial no ranking | ~0,4 s |
| integração | **RLS: não encontra dado de outro tenant** | ~0,4 s |
| integração | tarefa privada de terceiro não aparece | ~0,3 s |
| integração | menos de 2 caracteres devolve recentes | ~0,2 s |
| integração | clique registra no histórico | ~0,2 s |
| integração | histórico limitado a 20 | ~0,2 s |
| integração | **p95 < 200 ms com 100k registros** (marcado como lento) | ~1,0 s |
| frontend | debounce de 250 ms | ~0,3 s |
| frontend | destaque do termo no resultado | ~0,3 s |

**Total:** ~4,5 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · p95 medido com volume · Commit `feat(096): busca global`
