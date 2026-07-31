# 014 — Grupos e tipos de ação

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 011 · **Status:** ⬜ pendente

---

## 1. Objetivo

A taxonomia que classifica processos por área do direito. O **grupo de ação** também define
quem recebe as intimações daquela área — é peça central do roteamento da spec 045.

## 2. Escopo

- Tabela `action_groups` com responsável por intimações (6 padrão)
- Tabela `lawsuit_types` vinculada a grupo (10 padrão)
- CRUD de ambos + transferência em lote antes de excluir
- Telas `Configurações > Grupos de ação` e `> Tipos de ação`

## 3. Fora de escopo

- Fases e etapas → 015
- Metas por grupo → 039

## 4. Modelo de dados

```sql
CREATE TABLE action_groups (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  publications_user_id UUID REFERENCES users(id),  -- responsável por intimações
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE lawsuit_types (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  action_group_id UUID NOT NULL REFERENCES action_groups(id),
  name TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);
CREATE INDEX ix_lawsuit_types_group ON lawsuit_types (action_group_id);
```
Migration `014_action_groups_types.py`.

**Seed de grupos (6):** ADMINISTRATIVO · CÍVEL · FINANCEIRO/RH · PENAL · PREVIDENCIÁRIO · TRABALHISTA

**Seed de tipos (10):** ACUSAÇÃO DE ESTELIONATO · ADMISSÃO DE FUNCIONÁRIO · APOSENTADORIA POR
IDADE · CONCESSÃO DE FÉRIAS · CONCESSÃO DE FOLGA · DEMISSÃO DE FUNCIONÁRIO · JUSTIFICAÇÃO DE
FALTA · NULIDADE DE LICITAÇÃO · RECLAMATÓRIA TRABALHISTA · REINTEGRAÇÃO DE POSSE

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/action-groups?status=&q=` | autenticado |
| POST/PUT/DELETE | `/api/v1/action-groups[/{id}]` | GESTOR |
| GET | `/api/v1/lawsuit-types?group_id=&status=&q=` | autenticado |
| POST/PUT/DELETE | `/api/v1/lawsuit-types[/{id}]` | GESTOR |
| POST | `/api/v1/lawsuit-types/transfer` | GESTOR — `{from_id, to_id}` |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `FormModal`, `ConfirmDialog`, `EntityPicker`
**Cria:** `TransferBeforeDeleteDialog` (reutilizado por 015 e 016)
**Rotas:** `/settings/action-groups`, `/settings/lawsuit-types`

## 7. Regras de negócio

1. Nome único por tenant, case-insensitive e sem acento na comparação (`unaccent`).
2. Tipo de ação **sempre** pertence a um grupo. Grupo é derivado do tipo no processo — nunca informado direto.
3. Excluir grupo ou tipo em uso exige **transferência**: os registros migram para o destino escolhido.
4. `publications_user_id` opcional. Vazio → intimação cai no responsável geral (spec 045).
5. Inativar mantém o histórico; o item some dos seletores de novos registros.
6. Só GESTOR escreve.
7. Transferência é transacional: ou migra tudo, ou nada.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD dos dois | ~0,5 s |
| integração | nome duplicado ignorando acento → 409 | ~0,3 s |
| integração | excluir tipo em uso sem transferir → 409 | ~0,3 s |
| integração | transferência migra e é transacional | ~0,5 s |
| integração | tipos filtrados por grupo | ~0,3 s |
| integração | Colaborador → 403 | ~0,2 s |
| integração | RLS entre tenants | ~0,3 s |
| frontend | seleção de tipo filtra pelo grupo | ~0,4 s |

**Total:** ~2,8 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Seeds idempotentes · Commit `feat(014): grupos e tipos de ação`
