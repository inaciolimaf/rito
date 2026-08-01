# 004 — Autenticação

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 003 · **Status:** ✅ concluída

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

- **`X-Tenant-Id` continua obrigatório em TODOS os endpoints pré-autenticação** (login,
  refresh, logout, forgot-password, reset-password), não só no login. A spec mostra os
  contratos de entrada sem nenhum campo de tenant no corpo (`{email, password}`,
  `{refresh_token}`, etc.) — como e-mail só é único *por tenant* e `users`/`refresh_tokens`/
  `password_reset_tokens` têm RLS `FORCE`, não existe forma de localizar a linha certa sem
  saber o tenant antes da query (não dá pra "descobrir" o tenant a partir de uma chave
  globalmente única sem antes ligar `app.tenant_id`, e ligar via bypass de RLS violaria a
  regra 6 da 003). A leitura mais coerente com o resto do desenho: o front-end sempre sabe o
  tenant atual (subdomínio/seleção de escritório) e manda o header até obter um JWT válido;
  só a partir daí (`get_current_user`) o tenant passa a vir do claim, como a regra 8 pede.
- **Papel de aplicação de verdade importa de novo aqui.** `Base.type_annotation_map` precisou
  mapear `datetime` → `DateTime(timezone=True)` — sem isso o SQLAlchemy infere coluna "naive"
  a partir de `Mapped[datetime]`, e o asyncpg rejeita qualquer `datetime.now(UTC)` (tz-aware)
  contra ela. Isso também estava latente desde a 003 em `Tenant`/futuros campos de data —
  corrigido na `Base` de uma vez, não por tabela.
- **Revogação de família precisa de commit explícito.** Quando o `/auth/refresh` detecta
  reuso, `revoke_family()` roda dentro da MESMA transação da requisição (`get_session` da
  003 commita no sucesso e faz rollback em qualquer exceção). Como a resposta desse caso é
  sempre um 401 (uma exceção de domínio convertida em `HTTPException`), o rollback automático
  desfaria a revogação — o efeito de segurança mais importante do fluxo desapareceria
  silenciosamente. `AuthService.refresh()` chama `await self.session.commit()` explicitamente
  logo após `revoke_family`, antes de levantar a exceção; testado com 4 chamadas HTTP em
  sequência (login → refresh → reuso do token antigo → tentativa com o token rotacionado,
  que também precisa estar morto).
- **`X-Tenant-Id`/header nos testes vs. JWT no `/me`.** `test_auth_tenant.py` cobre os dois
  ângulos da regra 8: mesmo e-mail em dois tenants (isolados só pelo header) e "o token só
  resolve seu próprio tenant" (via `/auth/me`, que ignora qualquer header e usa só o claim).
- **Sem envio real de e-mail.** `forgot_password` gera e guarda o hash do token e devolve o
  token bruto só para quem chamou o *service* diretamente — o router HTTP nunca repassa esse
  valor na resposta (sempre 202 sem corpo), senão a rota vira um oráculo de "esse e-mail
  existe". Envio de e-mail de verdade (SMTP, template) fica para uma spec de notificações —
  não há infraestrutura de e-mail no projeto ainda e a 004 não detalhou nenhuma. O teste de
  reset usa o token chamando `AuthService.forgot_password` fora do HTTP, já que não existe
  outra forma de obter o token bruto sem um servidor de e-mail fake.
- **`app/core/errors.py` ganhou uma convenção nova**: `HTTPException(detail={"detail": "...",
  "errors": [...]})` agora é reconhecido pelo handler RFC 7807 e vira `errors` no corpo da
  resposta — usado por `WeakPasswordError` (422 do reset-password) para listar cada critério
  de senha que falhou, igual ao formato que `RequestValidationError` já usava. Reutilizável
  por qualquer spec futura que precise de 422 com lista de erros de negócio (não só de schema).
- `User` ficou em `app/domain/users/` (não em `app/domain/auth/`) mesmo só com os campos
  mínimos de login — a 012 (Usuários) vai *adicionar* colunas na mesma tabela/módulo, não
  criar um novo. `RefreshToken`/`PasswordResetToken` (efêmeros, só de auth) ficaram em
  `app/domain/auth/`.
- Nenhum RBAC, tela de login ou cadastro de usuário foi implementado — confirma o "fora de
  escopo" da spec (005, 006, 012 respectivamente).

## 10. Definição de pronto

- [x] Ciclo completo funcionando (login → `/me` → refresh → logout, testado ponta a ponta)
- [x] Detecção de reuso testada (reuso revoga a família inteira, incluindo o token que ainda
      era válido)
- [x] Parâmetros do Argon2 reduzidos só em teste (`ARGON2_TIME_COST`/`MEMORY_COST` via
      `TEST_*`; teste dedicado garante que o *default* da `Settings` continua em 3/65536)
- [x] Commit `feat(004): autenticação`
