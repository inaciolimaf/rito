# 012 — Usuários

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 011 · **Status:** ✅ concluída

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

**67 cargos, não 66 — a lista real do ADVBOX tem uma duplicata.** O levantamento
(`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` linha 365) rotula a seção "66 Cargos", mas a
lista enumerada tem "Assistente Jurídico" duas vezes — removendo a duplicata exata sobram
67 nomes únicos. Seedados os 67: o rótulo da fonte é uma contagem aproximada, a lista
enumerada é o levantamento de verdade (instrução do CLAUDE.md: consultar o ADVBOX para os
campos e regras reais, não inventar).

**`user_invitations` ganhou `occupation_id`/`financial_access`, que a seção 4 não
declarava.** O schema original só tinha `email`+`role`. Mas ADVBOX (`users/create`) mostra
que o cargo e o acesso financeiro são escolhidos no momento do convite/criação, não
depois — sem persistir os dois na própria invitation, essa escolha se perderia entre
convidar e aceitar (o `User` só nasce no aceite, ver próximo item). Adicionadas as duas
colunas, com FK e default consistentes com `users`.

**Convite cria o `User` só no aceite, não no convite (Design B).** A seção 4 não tem
`user_id` em `user_invitations` — se o `User` nascesse no convite, precisaria desse FK. A
ausência dele no schema é o sinal de que o desenho pretendido é: convite guarda só
e-mail/role/cargo/financeiro; `POST /invitations/accept` é quem cria a linha de `users`,
usando o `name`+`password` que o PRÓPRIO convidado fornece. Isso diverge um pouco do fluxo
literal do ADVBOX (`name` obrigatório já na criação, preenchido por quem convida) mas
segue o schema como a spec declarou.

**`POST /users/{id}/avatar` não estava na seção 5, mas a seção 6 pede um
`AvatarUploader`.** Um componente de upload sem endpoint de destino não faz sentido —
adicionado o endpoint (self ou ADMINISTRADOR, mesmo escopo de GET/PUT), reaproveitando a
mesma validação/redimensionamento do logotipo da conta (011). Isso motivou extrair
`app/domain/account/logo.py` para `app/core/image_processing.py` (renomeado
`process_image`/`InvalidImageError`, genérico) — é a mesma regra de negócio (PNG/JPG/SVG,
2 MB, 512px) em dois contextos; manter em `account/` e importar de `users/` seria
acoplamento entre domínios, duplicar seria repetir ~50 linhas idênticas.

**BaseRepository ganhou o keyset completo — resolve `docs/DIVIDA-TECNICA.md` #1.**
`GET /api/v1/users` é o primeiro endpoint de listagem real do projeto (`account`, na 011,
é 1:1, não precisou). `build_sorted_keyset_query` (ordena por uma coluna à escolha + `id`
como desempate, `WHERE (coluna, id) > (valor, id)` via `tuple_()`) e
`encode_cursor`/`decode_cursor` (base64) vivem ao lado do `build_keyset_query` antigo (só
`id`, usado só em teste) — sem alterá-lo, para não arriscar `tests/unit/test_base_repository.py`
sem necessidade.

**"Próprio usuário ou ADMINISTRADOR" não é so um `require_role`.** `require_role` só
expressa piso de hierarquia (GESTOR > ADMINISTRADOR > COLABORADOR), não "este usuário
específico ou aquele papel". `GET/PUT/POST avatar /users/{id}` usam
`require_role(COLABORADOR)` (satisfaz o scanner de permissão da spec 005/010) e depois
uma checagem manual (`_ensure_self_or_administrator`) que aceita o próprio id OU
ADMINISTRADOR/GESTOR — mesma hierarquia, sem duplicar `_ROLE_ORDER` (privado em
`core/permissions.py`).

**Frontend: conversão HH:MM ↔ formato da API para jornada.** `<input type="time">` nativo
trabalha em "HH:MM"; a API espera "HH:MM:SS" para `work_start`/`work_end` e duração ISO
8601 ("PT1H30M", o que Pydantic gera por padrão para `timedelta`) para `work_interval`.
`features/users/timeFormat.ts` faz as duas conversões nos dois sentidos — sem isso, o
`WorkScheduleField` não teria como preencher nem enviar esses três campos.

**UF brasileira validada pela primeira vez de verdade.** `state` em `accounts` (011) só
tinha `CHAR(2)` sem validação de conteúdo. OAB (`NNNNNN/UF`) precisa validar a UF de
verdade — `BRAZILIAN_UFS` (26 estados + DF) foi para `app/core/br_documents.py`, ao lado
de CPF/CNPJ (mesma categoria "validação de dado brasileiro"), reaproveitável quando
`accounts.state`/pessoas (016+) quiserem a mesma validação.

**Gaps conscientes, registrados em `docs/DIVIDA-TECNICA.md` #9 e #10** (não no escopo
desta spec — a seção "Front-end" não pede nenhum dos dois): não há página pública de
"aceitar convite" (o backend existe e está testado; falta infra de e-mail para o link
fazer sentido, e as duas coisas devem nascer juntas numa spec futura); `/settings/users`
não tem link de navegação ainda (só `/settings/users/:id` direto por URL) — `/settings`
continua sendo o placeholder genérico até uma spec desenhar a home de Configurações.

**Máximo de 25 jornadas e2e: continua 2/25.** O plano de testes da spec não pede e2e —
GET/PUT/convite/aceite já cobertos por integração, componentes por teste de frontend.

## 10. Definição de pronto

- [x] Migration `012_users_full.py` aplicada — occupations (67, seed idempotente por
      `id` fixo), colunas de RH/jornada em `users`, `user_invitations` com RLS, índices
      de FK (`occupation_id`, `invited_by`)
- [x] CRUD de usuários com RBAC (ADMINISTRADOR lista, GESTOR convida/inativa, próprio
      usuário ou ADMINISTRADOR lê/edita)
- [x] Convite por e-mail: expira em 7 dias, reenviar invalida o anterior, aceite cria a
      conta e ativa
- [x] OAB validada (formato + UF), obrigatória para cargo de advogado; jornada validada
      (fim > início, intervalo < jornada total); demissão ≥ admissão
- [x] Último GESTOR ativo não pode ser inativado; usuário não altera o próprio
      role/financial_access; salário oculto para quem não tem financial_access
- [x] `UserForm`, `InviteUserModal`, `WorkScheduleField`, `AvatarUploader` criados;
      `DataTable`/`FilterBar`/`FormModal`/`ConfirmDialog` reutilizados
- [x] Todos os testes do plano (seção 8) escritos, mais testes adicionais de cobertura
      de erro (404s, avatar inválido, senha fraca no aceite, busca textual na listagem)
- [x] `make lint` verde (ruff, black, mypy --strict, eslint, tsc, prettier)
- [x] `make test` verde, wall-clock ~28s (< 120s)
- [x] `test-timing.json` atualizado
- [x] `ROADMAP.md` → ✅
- [x] Commit `feat(012): usuários`
