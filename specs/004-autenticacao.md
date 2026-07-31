# 004 — Autenticação

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 003 · **Status:** ⬜ pendente

---

## 1. Objetivo

Usuário faz login com e-mail e senha, recebe access + refresh token, e o tenant passa a ser
resolvido pelo token — não mais por header.

## 2. Escopo

- Tabela `users` (mínima; campos de RH e cargo entram em 012)
- Hash Argon2id
- `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me`
- Rotação de refresh token com detecção de reuso
- Recuperação de senha por e-mail (token de uso único, expira em 1 h)
- Política de senha: mínimo 8, com número, minúscula, maiúscula e caractere especial
- Dependency `get_current_user` que também seta o contexto de tenant

## 3. Fora de escopo

- RBAC e perfis → 005
- Cadastro completo de usuário e convite → 012
- Tela de login → 006

## 4. Modelo de dados

```sql
CREATE TABLE users (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id      UUID NOT NULL REFERENCES tenants(id),
  email          CITEXT NOT NULL,
  password_hash  TEXT,
  name           TEXT NOT NULL,
  is_active      BOOLEAN NOT NULL DEFAULT true,
  last_login_at  TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);

CREATE TABLE refresh_tokens (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id   UUID NOT NULL REFERENCES tenants(id),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  TEXT NOT NULL UNIQUE,
  family_id   UUID NOT NULL,
  expires_at  TIMESTAMPTZ NOT NULL,
  revoked_at  TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE password_reset_tokens (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id   UUID NOT NULL REFERENCES tenants(id),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  TEXT NOT NULL UNIQUE,
  expires_at  TIMESTAMPTZ NOT NULL,
  used_at     TIMESTAMPTZ
);
```

RLS ligado nas três. E-mail é único **por tenant** — a mesma pessoa pode estar em dois escritórios.

Migration: `alembic/versions/004_auth.py`

## 5. Contratos de API

| Método | Rota | Entrada | Saída |
|---|---|---|---|
| POST | `/api/v1/auth/login` | `{email, password}` | `200 {access_token, refresh_token, expires_in}` · `401` |
| POST | `/api/v1/auth/refresh` | `{refresh_token}` | `200 {access_token, refresh_token}` · `401` |
| POST | `/api/v1/auth/logout` | `{refresh_token}` | `204` |
| GET | `/api/v1/auth/me` | — | `200 {id, name, email, tenant}` |
| POST | `/api/v1/auth/forgot-password` | `{email}` | `202` (sempre, para não revelar cadastro) |
| POST | `/api/v1/auth/reset-password` | `{token, password}` | `204` · `400` |

Claims do access token: `sub`, `tenant_id`, `exp`, `iat`, `jti`. TTL 15 min. Refresh: 30 dias.

## 6. Front-end

Nenhum (a tela vem em 006).

## 7. Regras de negócio

1. Senha fraca é rejeitada com `422` listando quais critérios falharam.
2. Login inválido retorna `401` genérico — nunca distingue "e-mail não existe" de "senha errada".
3. `forgot-password` sempre retorna `202`, exista ou não o e-mail.
4. Refresh rotaciona: o token antigo é revogado e um novo é emitido.
5. **Reuso de refresh token revogado invalida a família inteira** e força novo login.
6. Usuário inativo não autentica, mesmo com senha correta.
7. Token de reset é de uso único e expira em 1 h.
8. `get_current_user` seta `app.tenant_id` a partir do claim — o cliente não escolhe mais o tenant.
9. Rate limit no login: 5 tentativas por minuto por e-mail + IP.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | login → refresh → logout | `tests/integration/test_auth_flow.py` | ~0,6 s |
| integração | senha errada → 401 genérico | idem | ~0,3 s |
| integração | reuso de refresh revoga a família | `tests/integration/test_token_reuse.py` | ~0,5 s |
| integração | usuário inativo não loga | idem | ~0,3 s |
| integração | mesmo e-mail em dois tenants coexiste | `tests/integration/test_auth_tenant.py` | ~0,4 s |
| integração | token do tenant A não acessa dado do tenant B | idem | ~0,4 s |
| integração | reset de senha usa token uma única vez | `tests/integration/test_password_reset.py` | ~0,5 s |
| integração | rate limit no login | idem | ~0,4 s |
| unit | política de senha (tabela de casos) | `tests/unit/test_password_policy.py` | ~0,2 s |
| unit | Argon2 verifica e rejeita | `tests/unit/test_hashing.py` | ~0,3 s |

**Total estimado:** ~3,9 s

> Argon2 é intencionalmente lento. Nos testes, use parâmetros reduzidos via settings —
> os parâmetros de produção ficam validados por um único teste dedicado.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

- [ ] Ciclo completo funcionando
- [ ] Detecção de reuso testada
- [ ] Parâmetros do Argon2 reduzidos só em teste
- [ ] Commit `feat(004): autenticação`
