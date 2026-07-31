# 013 — Times (squads)

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 012 · **Status:** ⬜ pendente

---

## 1. Objetivo

Agrupar colaboradores em times para atribuir tarefa ao grupo inteiro de uma vez, em vez de
selecionar pessoa por pessoa.

## 2. Escopo

- Tabelas `squads` e `squad_members`
- CRUD com seleção múltipla de membros
- Aba `Configurações > Usuários > Times`

## 3. Fora de escopo

- Atribuição de tarefa a time → 032 (aqui só o cadastro)

## 4. Modelo de dados

```sql
CREATE TABLE squads (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE squad_members (
  squad_id UUID NOT NULL REFERENCES squads(id) ON DELETE CASCADE,
  user_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  PRIMARY KEY (squad_id, user_id)
);
```
RLS nas duas. Migration `013_squads.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/squads?status=&q=&cursor=` | autenticado |
| POST | `/api/v1/squads` | ADMINISTRADOR |
| GET/PUT/DELETE | `/api/v1/squads/{id}` | ADMINISTRADOR |

`PUT` recebe `member_ids[]` completo e reconcilia (não é patch incremental).

## 6. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `ConfirmDialog`
**Cria:** `SquadForm` (nome + lista de checkboxes de colaboradores)
**Rota:** `/settings/users?tab=squads`

Colunas: Nome do time · Membros (contagem + avatares) · Cadastro

## 7. Regras de negócio

1. Nome único por tenant.
2. Time pode existir vazio, mas a UI avisa.
3. Remover membro **não** apaga o usuário nem as tarefas já atribuídas a ele.
4. Inativar usuário o remove das listas de atribuição, mas ele permanece no time.
5. Excluir time não afeta tarefas já criadas a partir dele.
6. `PUT` com `member_ids[]` reconcilia: adiciona os novos, remove os ausentes.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD completo | ~0,4 s |
| integração | nome duplicado → 409 | ~0,2 s |
| integração | reconciliação de membros no PUT | ~0,4 s |
| integração | excluir time não apaga usuários | ~0,3 s |
| integração | RLS entre tenants | ~0,3 s |
| frontend | `SquadForm` seleciona múltiplos | ~0,4 s |

**Total:** ~2,0 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(013): times (squads)`
