# 079 — Parceiros

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 027 · **Status:** ⬜ pendente

---

## 1. Objetivo

Escritórios que trabalham juntos em processos — correspondente em outro estado, parceria de
captação, banca especializada. A funcionalidade mais delicada do produto do ponto de vista de
isolamento: é o **único caso em que dado atravessa a fronteira do tenant**.

## 2. Escopo

- Convite por e-mail e aceite
- Rede de parceiros
- Compartilhamento de processo com escopo restrito
- Demandas pendentes de cada lado
- Filtros e relatório da parceria

## 3. Fora de escopo

- Repasse financeiro automático entre escritórios (fora do escopo)
- Chat entre parceiros (usa comentário da tarefa compartilhada)

## 4. Modelo de dados

```sql
CREATE TYPE partnership_status AS ENUM ('PENDENTE','ATIVA','RECUSADA','ENCERRADA');

CREATE TABLE partnerships (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  requester_tenant_id UUID NOT NULL REFERENCES tenants(id),
  partner_tenant_id UUID REFERENCES tenants(id),     -- nulo até o aceite
  invited_email CITEXT NOT NULL,
  status partnership_status NOT NULL DEFAULT 'PENDENTE',
  token_hash TEXT UNIQUE,
  invited_by UUID NOT NULL REFERENCES users(id),
  accepted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (requester_tenant_id, invited_email)
);

CREATE TABLE shared_lawsuits (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  partnership_id UUID NOT NULL REFERENCES partnerships(id) ON DELETE CASCADE,
  owner_tenant_id UUID NOT NULL REFERENCES tenants(id),
  partner_tenant_id UUID NOT NULL REFERENCES tenants(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  can_view_financial BOOLEAN NOT NULL DEFAULT false,
  can_create_tasks BOOLEAN NOT NULL DEFAULT true,
  shared_by UUID NOT NULL REFERENCES users(id),
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (lawsuit_id, partner_tenant_id)
);
CREATE INDEX ix_shared_partner ON shared_lawsuits (partner_tenant_id) WHERE revoked_at IS NULL;
```
Migration `079_partnerships.py`.

**Política de RLS estendida** em `lawsuits`, `posts` e `lawsuit_parties`:
`SELECT` permite `tenant_id = current_tenant` **ou** existe `shared_lawsuits` ativo para o
processo com `partner_tenant_id = current_tenant`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/partnerships?status=` | ADMINISTRADOR |
| POST | `/api/v1/partnerships/invite` → `{email}` | GESTOR |
| POST | `/api/v1/partnerships/accept` → `{token}` | GESTOR |
| POST | `/api/v1/partnerships/{id}/end` | GESTOR |
| POST | `/api/v1/lawsuits/{id}/share` → `{partnership_id, can_view_financial, can_create_tasks}` | ADMINISTRADOR |
| DELETE | `/api/v1/lawsuits/{id}/share/{share_id}` | ADMINISTRADOR |
| GET | `/api/v1/partnerships/shared-with-me?report=&status=&steps[]=` | autenticado |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `StatCard`, `EntityPicker`, `ConfirmDialog`
**Cria:** `PartnersPage`, `InvitePartnerDialog`, `ShareLawsuitDialog` (com escopo explícito),
`SharedBadge`, `PartnerNetworkList`
**Rota:** `/partners`

Cards: Processos compartilhados ativos · Demanda pendente pelo escritório · Demanda pendente pelo parceiro

## 7. Regras de negócio

1. Parceria é **bilateral e simétrica** — aceita uma vez, vale para os dois lados.
2. Convite para e-mail sem conta no Rito envia convite de cadastro; a parceria fica `PENDENTE`.
3. Compartilhar é **por processo**, nunca a carteira inteira. Não existe "compartilhar tudo".
4. O parceiro enxerga: dados do processo, partes, timeline e tarefas. **Não** enxerga: outros processos, contatos não relacionados, financeiro (salvo `can_view_financial`), configurações, relatórios e BI.
5. `can_create_tasks` permite ao parceiro criar tarefa no processo compartilhado; sem isso, é só leitura.
6. Revogar o compartilhamento corta o acesso imediatamente; o que o parceiro criou permanece.
7. Encerrar a parceria revoga **todos** os compartilhamentos, dos dois lados.
8. Tarefa criada por parceiro é marcada com a origem e aparece nas duas caixas de entrada.
9. Parceiro **nunca** vê valor financeiro sem `can_view_financial`, mesmo com `financial_access = FULL` no tenant dele.
10. "Demanda pendente pelo parceiro" = tarefas atribuídas ao parceiro, não concluídas.
11. Toda ação de compartilhamento é auditada.
12. Processo compartilhado exibe badge permanente, para ninguém esquecer que há terceiro olhando.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | convite → aceite → parceria ativa | ~0,5 s |
| integração | convite para e-mail sem conta fica pendente | ~0,3 s |
| integração | compartilhar dá acesso ao processo | ~0,4 s |
| integração | **parceiro NÃO vê outros processos do dono** | ~0,5 s |
| integração | **parceiro NÃO vê contatos não relacionados** | ~0,4 s |
| integração | **parceiro NÃO vê financeiro sem permissão** | ~0,4 s |
| integração | parceiro com `can_view_financial` vê | ~0,3 s |
| integração | parceiro sem `can_create_tasks` não cria → 403 | ~0,3 s |
| integração | revogar corta o acesso na hora | ~0,4 s |
| integração | revogar preserva o que o parceiro criou | ~0,3 s |
| integração | encerrar parceria revoga tudo dos dois lados | ~0,4 s |
| integração | tarefa de parceiro aparece nas duas inboxes | ~0,4 s |
| integração | **parceiro não acessa BI nem relatórios do dono** | ~0,4 s |
| frontend | diálogo mostra o escopo do compartilhamento | ~0,4 s |

**Total:** ~5,4 s

> Os cinco testes marcados são de **vazamento entre tenants**. São os mais importantes do
> projeto inteiro — um furo aqui expõe carteira de cliente a concorrente.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Todos os testes de vazamento passando · Auditoria completa · Commit `feat(079): parceiros`
