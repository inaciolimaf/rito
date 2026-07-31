# 047 — DataJud: andamentos

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 046, 026 · **Status:** ⬜ pendente

---

## 1. Objetivo

Manter a timeline do processo atualizada com os movimentos oficiais do tribunal, sem raspagem.
É o que alimenta as visões "parado há +90 dias" e o campo `last_movement_at`.

## 2. Escopo

- Task Celery agendada + gatilho manual por processo
- Sincronização só de processos **cadastrados** com número CNJ válido
- Incremental por `dataHoraUltimaAtualizacao`
- Persistência em `lawsuit_movements` com `origin = TRIBUNAL`
- Atualização de `last_movement_at`
- Enriquecimento da capa (órgão julgador, classe, assuntos, data de ajuizamento)

## 3. Fora de escopo

- Descoberta de processos novos por OAB — o Rito não faz isso, por escolha de escopo
- Análise de movimento por IA → 089

## 4. Modelo de dados

```sql
ALTER TABLE lawsuits
  ADD COLUMN datajud_last_sync_at TIMESTAMPTZ,
  ADD COLUMN datajud_last_update  TIMESTAMPTZ,   -- dataHoraUltimaAtualizacao do CNJ
  ADD COLUMN datajud_not_found_count SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN judging_organ TEXT,
  ADD COLUMN filing_date DATE,
  ADD COLUMN cnj_class_code INTEGER,
  ADD COLUMN cnj_class_name TEXT;

CREATE TABLE lawsuit_subjects (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  code INTEGER NOT NULL, name TEXT NOT NULL,
  UNIQUE (lawsuit_id, code)
);

CREATE INDEX ix_lawsuits_datajud_due ON lawsuits (tenant_id, datajud_last_sync_at NULLS FIRST)
  WHERE process_number IS NOT NULL AND NOT is_archived;
```
Migration `047_datajud_sync.py`.

## 5. Fluxo

```
para cada processo com número CNJ, não arquivado, ordenado por datajud_last_sync_at:
  resolve o alias pelo tribunal (ou infere pelo número — spec 025)
  consulta o DataJud
  se não encontrado:
    incrementa datajud_not_found_count; ao chegar em 5, pausa e alerta
  senão:
    para cada movimento com dataHora > datajud_last_update:
      insere em lawsuit_movements (external_id = id do movimento)
    atualiza capa, last_movement_at, datajud_last_update, datajud_last_sync_at
```

## 6. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/lawsuits/{id}/sync-movements` — manual |
| GET | `/api/v1/lawsuits/{id}/sync-status` |

## 7. Regras de negócio

1. Só processos com `process_number` válido e não arquivados entram na fila.
2. Deduplicação por `(tenant_id, lawsuit_id, external_id)` — reprocessar não duplica movimento.
3. Incremental por `dataHoraUltimaAtualizacao`: se o CNJ não mudou nada, a sincronização termina sem escrever.
4. `nivelSigilo > 0` → nada é persistido e o processo é marcado como não sincronizável.
5. Processo não encontrado 5 vezes seguidas é pausado, com alerta — número errado ou tribunal sem cobertura.
6. Movimento do tribunal é **imutável** na UI (regra já definida em 026).
7. `last_movement_at` é atualizado pela trigger de 027 — não escreva na mão.
8. Capa só sobrescreve campo que estiver **vazio** no Rito. Dado digitado pelo usuário vence o do CNJ.
9. Rate limit respeitado; a fila é processada em lotes.
10. Sincronização manual de processo já em andamento → 409.
11. Falha em um processo não interrompe o lote.
12. `filing_date` do CNJ não sobrescreve `process_date` — são coisas diferentes (ajuizamento × requerimento).

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | primeira sync traz todos os movimentos | ~0,5 s |
| integração | **rodar duas vezes não duplica** | ~0,4 s |
| integração | incremental ignora movimento antigo | ~0,4 s |
| integração | sem mudança não escreve nada | ~0,3 s |
| integração | segredo de justiça não persiste | ~0,3 s |
| integração | 5 não-encontrados pausa e alerta | ~0,4 s |
| integração | capa não sobrescreve campo preenchido | ~0,4 s |
| integração | `filing_date` não toca `process_date` | ~0,2 s |
| integração | `last_movement_at` atualiza pela trigger | ~0,3 s |
| integração | falha em um não interrompe o lote | ~0,4 s |
| integração | sync manual concorrente → 409 | ~0,3 s |
| integração | movimento aparece na timeline | ~0,3 s |
| integração | processo arquivado fora da fila | ~0,2 s |

**Total:** ~4,4 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Idempotência provada · Dado do usuário nunca sobrescrito · Commit `feat(047): DataJud — andamentos`
