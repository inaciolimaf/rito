# 026 — Processos: timeline unificada

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 024 · **Status:** ✅ concluída

---

## 1. Objetivo

A tela mais consultada do sistema: tudo que aconteceu no processo, em ordem cronológica, num
só lugar — tarefas, andamentos do tribunal, movimentações manuais, intimações e lançamentos
financeiros, cada tipo podendo ser ligado ou desligado.

## 2. Escopo

- Tabela `lawsuit_movements` (movimentações manuais e automáticas)
- View/query de agregação da timeline
- Toggles por tipo de evento
- Paginação cronológica
- Componente de timeline

## 3. Fora de escopo

- Tarefas → 032 · Publicações → 042 · Financeiro → 056
  *(a timeline já prevê os slots; eles ficam vazios até essas specs)*

## 4. Modelo de dados

```sql
CREATE TYPE movement_origin AS ENUM ('TRIBUNAL','MANUAL');

CREATE TABLE lawsuit_movements (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  origin movement_origin NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  title TEXT NOT NULL,
  body TEXT,
  header TEXT,                       -- "TJSP - Tribunal de Justiça"
  external_code INTEGER,             -- código do movimento na tabela do CNJ
  external_id TEXT,                  -- id no DataJud, para dedupe
  raw_payload JSONB,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, lawsuit_id, external_id)
);
CREATE INDEX ix_movements_lawsuit ON lawsuit_movements (lawsuit_id, occurred_at DESC);
CREATE INDEX ix_movements_origin  ON lawsuit_movements (tenant_id, origin);
```
RLS ligado. Migration `026_lawsuit_movements.py`.

**Agregação da timeline** — union de 5 fontes, normalizadas para
`(occurred_at, kind, id, title, summary, actor, metadata)`:
`task` · `movement_auto` · `movement_manual` · `publication` · `transaction`

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/lawsuits/{id}/timeline?kinds=task,movement_auto&cursor=&limit=` |
| POST | `/api/v1/lawsuits/{id}/movements` (manual) |
| PUT/DELETE | `/api/v1/lawsuits/{id}/movements/{mid}` (só `origin=MANUAL`) |

## 6. Front-end

**Reutiliza:** `EmptyState`, `ConfirmDialog`, `FormModal`
**Cria:** `LawsuitTimeline`, `TimelineItem` (variante por `kind`), `TimelineFilters` (5 toggles),
`AddMovementModal`
**Rota:** `/lawsuits/:id` (aba principal)

## 7. Regras de negócio

1. Ordenação por `occurred_at` decrescente; empate desempata por `kind` e depois por `id` — ordenação **estável**.
2. Toggles são combináveis; nenhum marcado → timeline vazia com aviso, não a lista completa.
3. Movimentação com `origin=TRIBUNAL` é **imutável** pela UI: sem editar, sem excluir.
4. Movimentação manual é editável e excluível por quem criou ou por ADMINISTRADOR.
5. `external_id` único por processo — reprocessar o DataJud não duplica.
6. Paginação keyset por `(occurred_at, id)`.
7. Preferência de toggles é persistida por usuário.
8. A timeline **nunca** faz N+1: a agregação é uma query única com union.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | timeline agrega as 5 fontes na ordem certa | ~0,6 s |
| integração | toggles filtram por tipo | ~0,4 s |
| integração | nenhum toggle → vazio | ~0,2 s |
| integração | ordenação estável com mesmo timestamp | ~0,3 s |
| integração | paginação keyset não repete nem pula | ~0,4 s |
| integração | editar movimento do tribunal → 403 | ~0,2 s |
| integração | editar movimento manual funciona | ~0,2 s |
| integração | `external_id` duplicado → 409 | ~0,2 s |
| integração | **budget de queries: timeline ≤ 3 statements** | ~0,4 s |
| integração | RLS entre tenants | ~0,3 s |
| frontend | toggles persistem | ~0,4 s |
| frontend | item renderiza variante por tipo | ~0,4 s |

**Total:** ~4,0 s

## 9. Descobertas

1. **A agregação é um UNION ALL de um select por `kind`** — os slots `task`/
   `publication`/`transaction` não entram no union enquanto as tabelas não existem
   (specs 032/042/056); ligar cada fonte depois é acrescentar um select. Pedir um kind
   sem fonte retorna vazio, coerente com a regra 2.
2. **Keyset com ordem mista não cabe em tupla:** `ORDER BY occurred_at DESC, kind ASC,
   id ASC` tem direções diferentes por coluna, então a comparação de tupla do
   `build_sorted_keyset_query` não serve — o predicado é o desdobramento lexicográfico
   exato (3 ramos OR). Cursor codifica `(occurred_at, kind, id)` em JSON+base64.
3. **`total` é uma query separada sem o filtro de cursor** — `COUNT(*) OVER()` na query
   da página contaria só o restante após o cursor (o total mudaria entre páginas).
   Budget medido: 3 statements (get do processo + contagem + página) com 11 itens —
   regra 8 validada por teste que ignora o `set_config` do contexto de tenant.
4. **Regra 7 virou infra genérica:** `users.preferences JSONB` (na mesma migration) +
   `GET/PUT /users/me/preferences` com merge raso por chave. A primeira consumidora é
   `lawsuit_timeline_kinds`; futuras preferências de UI reutilizam sem migration.
5. **Regra 5 testada no mecanismo, não no HTTP:** o endpoint de movimentações é manual
   (não recebe `external_id`), então a dedupe é validada direto na UNIQUE — o mapeamento
   para 409 chega com a sync do DataJud (spec 047), único caminho que escreve
   movimentações TRIBUNAL. O teste documenta isso em docstring.
6. **O e2e roda contra o banco de DEV (`rito`)**, não o de teste — migration nova
   precisa ser aplicada nos dois bancos, senão o `global-setup.ts` quebra com
   `UndefinedColumnError` (aconteceu nesta spec: `users.preferences`).
7. **`_get_movement_or_404`/`_get_party_or_404` consultam o processo de novo** em vez de
   reutilizar o detalhe — custo de 1 query extra por request, aceitável; se a spec 030
   (refatoração) quiser, dá para fundir.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste (1–8; regra 5 no mecanismo — ver 9.5)
- [x] Teste de isolamento por tenant (`test_timeline_isolada_entre_tenants`)
- [x] `make test` verde e wall-clock < 120 s (63 s)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa
- [x] Timeline em ≤ 3 queries (teste de budget)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(026): processos — timeline unificada`
