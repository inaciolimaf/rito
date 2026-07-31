# 012 — Usuários

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 011 · **Status:** ⬜ pendente

---

## 1. Objetivo

Gestão completa de colaboradores: convite por e-mail, dados pessoais e de RH, cargo, OAB,
jornada de trabalho e meta de pontos do Taskscore.

## 2. Escopo

- Expansão de `users` com os campos do levantamento
- Tabela `occupations` com os **66 cargos** (seed)
- Convite por e-mail com link de ativação
- CRUD, ativação/inativação
- Toggle "Habilitar registro de acessos" (a tabela de log vem em 073)
- Telas `Configurações > Usuários`

## 3. Fora de escopo

- Times → 013
- Registro de acessos e livro de ponto → 073
- Certificado A1 (não haverá — sem raspagem de tribunal)

## 4. Modelo de dados

```sql
CREATE TABLE occupations (
  id    SMALLINT PRIMARY KEY,
  name  TEXT NOT NULL UNIQUE
);  -- global, sem tenant

ALTER TABLE users
  ADD COLUMN occupation_id   SMALLINT REFERENCES occupations(id),
  ADD COLUMN identification  TEXT,          -- CPF
  ADD COLUMN document        TEXT,          -- RG
  ADD COLUMN birthdate       DATE,
  ADD COLUMN number_ctps     TEXT,
  ADD COLUMN number_oab      TEXT,          -- formato "123456/SP"
  ADD COLUMN cellphone       TEXT,
  ADD COLUMN phone           TEXT,
  ADD COLUMN avatar_key      TEXT,
  ADD COLUMN salary          NUMERIC(12,2),
  ADD COLUMN admission_date  DATE,
  ADD COLUMN resignation_date DATE,
  ADD COLUMN work_start      TIME,
  ADD COLUMN work_interval   INTERVAL,
  ADD COLUMN work_end        TIME,
  ADD COLUMN points_goal     INTEGER,
  ADD COLUMN report_deadline BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN report_deleted  BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN is_responsible  BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE user_invitations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  email CITEXT NOT NULL, role user_role NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL, accepted_at TIMESTAMPTZ,
  invited_by UUID NOT NULL REFERENCES users(id)
);

ALTER TABLE accounts ADD COLUMN track_access_logs BOOLEAN NOT NULL DEFAULT false;
```
Migration `012_users_full.py` + seed dos 66 cargos.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/users?role=&status=&q=&cursor=` | ADMINISTRADOR |
| POST | `/api/v1/users/invite` | GESTOR |
| GET/PUT | `/api/v1/users/{id}` | próprio usuário ou ADMINISTRADOR |
| POST | `/api/v1/users/{id}/deactivate` | GESTOR |
| POST | `/api/v1/invitations/accept` | público (com token) |
| GET | `/api/v1/occupations` | autenticado |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `FormModal`, `ConfirmDialog`
**Cria:** `UserForm`, `InviteUserModal`, `WorkScheduleField`, `AvatarUploader`
**Rotas:** `/settings/users`, `/settings/users/:id`

Colunas: Nome · Perfil · Meta de pontos · Acesso financeiro · Cadastro

## 7. Regras de negócio

1. Convite expira em 7 dias; reenviar invalida o anterior.
2. Aceitar convite define a senha e ativa a conta.
3. E-mail já cadastrado no tenant → 409.
4. `number_oab` no formato `NNNNNN/UF`; UF validada. Obrigatório se o cargo for de advogado.
5. Jornada: `work_end` > `work_start`; intervalo menor que a jornada total.
6. `resignation_date` ≥ `admission_date`.
7. Inativar não apaga: usuário some das listas de atribuição mas o histórico permanece.
8. Não é possível inativar o **último** GESTOR ativo do tenant.
9. Usuário edita o próprio perfil, mas **não** o próprio `role` nem `financial_access`.
10. Salário só é visível para quem tem `financial_access` ≥ `READ_ONLY`.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | convite → aceite → login | ~0,6 s |
| integração | convite expirado → 400 | ~0,3 s |
| integração | e-mail duplicado no tenant → 409 | ~0,3 s |
| integração | mesmo e-mail em outro tenant é aceito | ~0,3 s |
| integração | inativar último GESTOR → 409 | ~0,3 s |
| integração | usuário não altera o próprio role | ~0,3 s |
| integração | salário oculto para `financial_access=NONE` | ~0,3 s |
| unit | validação de OAB (tabela de casos) | ~0,2 s |
| unit | validação de jornada | ~0,2 s |
| frontend | `UserForm` valida e submete | ~0,4 s |
| frontend | listagem filtra por perfil e status | ~0,4 s |

**Total:** ~3,6 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Seed dos 66 cargos idempotente · Commit `feat(012): usuários`
