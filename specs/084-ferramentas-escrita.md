# 084 — Ferramentas de escrita

**Fase:** 8 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 083 · **Status:** ⬜ pendente

---

## 1. Objetivo

A IA passa a **agir** no sistema — criar cliente, abrir processo, lançar tarefa, mudar etapa.
Com uma regra inegociável: **nada é gravado sem confirmação humana explícita**. O agente propõe,
a interface mostra exatamente o que vai acontecer, a pessoa aprova, o sistema audita.

## 2. Escopo

- Ferramentas de escrita para as operações principais
- Fluxo obrigatório propor → preview → confirmar → executar → auditar
- `AIActionPreview` mostrando o diff
- Log de auditoria imutável
- Desfazer quando aplicável
- Limites por operação

## 3. Fora de escopo

- Automação sem humano → 092/094 (e mesmo lá, com regra própria)
- Exclusão de registro — **a IA nunca apaga nada**

## 4. Modelo de dados

```sql
CREATE TYPE ai_action_status AS ENUM ('pending','approved','rejected','executed','failed','expired');

CREATE TABLE ai_actions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  thread_id UUID REFERENCES ai_threads(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id),
  tool_name TEXT NOT NULL,
  arguments JSONB NOT NULL,
  preview JSONB NOT NULL,               -- o que será criado/alterado
  before_state JSONB,                   -- estado anterior (update)
  status ai_action_status NOT NULL DEFAULT 'pending',
  affected_type TEXT, affected_id UUID,
  rejection_reason TEXT, error TEXT,
  decided_by UUID REFERENCES users(id),
  decided_at TIMESTAMPTZ, executed_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '1 hour',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_ai_actions_pending ON ai_actions (tenant_id, user_id, created_at DESC)
  WHERE status = 'pending';

CREATE TABLE ai_audit_log (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  action_id UUID NOT NULL REFERENCES ai_actions(id),
  user_id UUID NOT NULL REFERENCES users(id),
  tool_name TEXT NOT NULL,
  affected_type TEXT NOT NULL, affected_id UUID NOT NULL,
  before_state JSONB, after_state JSONB,
  model TEXT NOT NULL, thread_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_affected ON ai_audit_log (tenant_id, affected_type, affected_id);
```
RLS nas duas. `ai_audit_log` é **append-only** — sem UPDATE nem DELETE, garantido por regra no banco.
Migration `084_ai_actions.py`.

## 5. Catálogo de ferramentas de escrita

| Ferramenta | Operação |
|---|---|
| `create_customer` | novo contato |
| `update_customer` | atualizar contato |
| `create_lawsuit` | novo processo |
| `update_lawsuit` | atualizar processo |
| `move_lawsuit_stage` | mudar etapa |
| `create_task` | nova tarefa |
| `complete_task` | concluir tarefa |
| `create_transaction` | lançamento financeiro |
| `link_publication` | vincular intimação a processo |
| `apply_workflow` | aplicar workflow ao processo |

**Não existe ferramenta de exclusão.** Nenhuma.

## 6. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/ai/actions?status=pending` |
| GET | `/api/v1/ai/actions/{id}` |
| POST | `/api/v1/ai/actions/{id}/approve` |
| POST | `/api/v1/ai/actions/{id}/reject` → `{reason}` |
| GET | `/api/v1/ai/audit?affected_type=&affected_id=&cursor=` |

## 7. Front-end

**Reutiliza:** `ConfirmDialog`, `DataTable`
**Cria:** `AIActionPreview` (diff campo a campo, verde para novo, amarelo para alterado),
`PendingActionsList`, `AiAuditTrail` (histórico do que a IA fez num registro),
`AiBadge` (marca registro criado por IA)
**Rota:** dentro do copiloto (085) e em `/settings/ai?tab=audit`

## 8. Regras de negócio

1. **Nenhuma escrita acontece sem `approved`.** Chamar a ferramenta cria uma `ai_action` pendente e interrompe o grafo (082). Não existe caminho alternativo.
2. O preview mostra **exatamente** o que será gravado: em criação, todos os campos; em atualização, o diff antes/depois.
3. Só o usuário dono da ação aprova. Nem GESTOR aprova pelos outros.
4. Ação pendente expira em 1 h e vira `expired`.
5. Execução respeita **todas** as regras de negócio do service — a IA não é caminho paralelo. Validação que reprova humano reprova IA.
6. Execução usa a permissão do usuário. Sem permissão para a operação → a ação nasce já rejeitada, com motivo.
7. Toda execução grava em `ai_audit_log` com estado antes e depois, modelo usado e thread.
8. `ai_audit_log` é append-only. Tentativa de UPDATE ou DELETE falha no banco.
9. Registro criado por IA recebe badge visível na UI, permanentemente.
10. Desfazer: até 5 min após executar, e só se o registro não foi alterado depois.
11. Rejeição alimenta o contexto do agente — ele aprende com a recusa dentro daquele thread.
12. Máximo de 5 ações pendentes por thread — evita enxurrada de aprovações.
13. **Nenhuma ferramenta apaga registro.** Nem soft delete. Arquivamento é ação humana.

## 9. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | **ferramenta cria ação pendente, não grava** | ~0,5 s |
| integração | aprovar executa e audita | ~0,5 s |
| integração | rejeitar não grava nada | ~0,3 s |
| integração | outro usuário não aprova → 403 | ~0,3 s |
| integração | GESTOR também não aprova pelos outros | ~0,3 s |
| integração | expira em 1 h | ~0,3 s |
| integração | **execução respeita as regras do service** (categoria errada é barrada) | ~0,5 s |
| integração | sem permissão nasce rejeitada | ~0,4 s |
| integração | preview mostra o diff correto | ~0,4 s |
| integração | **`ai_audit_log` rejeita UPDATE e DELETE** | ~0,4 s |
| integração | desfazer em 5 min funciona | ~0,4 s |
| integração | desfazer após alteração → 409 | ~0,3 s |
| integração | 6ª ação pendente é barrada | ~0,3 s |
| **meta** | **nenhuma ferramenta de exclusão no registry** | ~0,2 s |
| frontend | preview destaca novo e alterado | ~0,5 s |

**Total:** ~5,6 s

> Os três testes marcados são o coração da segurança da camada de IA. O primeiro prova que a
> confirmação não é opcional; o penúltimo, que o histórico é imutável.

## 10. Definição de pronto

Checklist padrão · Nenhum caminho de escrita sem aprovação · Auditoria imutável · Commit `feat(084): ferramentas de escrita`
