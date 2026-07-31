# 026 — Processos: timeline unificada

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 024 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Timeline em ≤ 3 queries · Commit `feat(026): processos — timeline unificada`
