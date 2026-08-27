# 095 — API pública v1

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +7 s
**Depende de:** 059, 048 · **Status:** ✅ concluída

---

## 1. Objetivo

API REST para integradores. Espelha o escopo da API do ADVBOX (22 endpoints), com autenticação
por token de tenant, rate limit e documentação OpenAPI.

## 2. Escopo

- Tokens de API por tenant, com escopo
- Endpoints de leitura e escrita nos recursos principais
- Rate limit
- Paginação, filtros e ordenação
- OpenAPI e página de documentação
- Log de uso

## 3. Fora de escopo

- Webhooks de entrada · GraphQL · SDK cliente

## 4. Modelo de dados

```sql
CREATE TABLE api_tokens (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,                  -- 8 primeiros caracteres, para identificar
  scopes TEXT[] NOT NULL DEFAULT '{}',   -- 'read:customers', 'write:lawsuits'...
  allowed_ips INET[],
  last_used_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE api_requests (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  token_id UUID REFERENCES api_tokens(id) ON DELETE SET NULL,
  method TEXT NOT NULL, path TEXT NOT NULL,
  status_code SMALLINT NOT NULL, duration_ms INTEGER,
  ip_address INET,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_api_requests_token ON api_requests (token_id, created_at DESC);
```
RLS ligado. Migration `095_api_tokens.py`.

## 5. Endpoints públicos

**Base:** `/api/public/v1` · **Auth:** `Authorization: Bearer <token>`

| Recurso | Endpoints |
|---|---|
| Settings | `GET /settings` |
| Customers | `GET /customers` · `POST /customers` · `GET /customers/{id}` · `GET /customers/birthdays` |
| Lawsuits | `GET /lawsuits` · `POST /lawsuits` · `GET /lawsuits/{id}` · `PUT /lawsuits/{id}` · `GET /lawsuits/{id}/history` · `GET /lawsuits/{id}/movements` · `POST /lawsuits/{id}/movements` · `GET /last-movements` |
| Tasks | `GET /posts` · `POST /posts` |
| Publications | `GET /publications` |
| Transactions | `GET /transactions` · `POST /transactions` · `GET /transactions/{id}` · `PUT /transactions/{id}` |
| Documents | `GET /documents` · `GET /documents/{id}/download` |

`GET /settings` devolve os ids de referência da conta — usuários, origens, tipos de tarefa,
etapas, tipos de processo e dados financeiros — no mesmo espírito do endpoint do ADVBOX.

**Rate limit:** 30 GET/min · 500 POST/dia por rota · 500 PUT/dia. Excedido → `429` com `Retry-After`.

## 6. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `ConfirmDialog`, `StatCard`
**Cria:** `ApiTokensPage`, `CreateTokenDialog` (token exibido uma vez),
`ScopeSelector`, `ApiUsagePanel`, `ApiDocsPage` (Swagger UI embutido)
**Rota:** `/settings/api`

## 7. Regras de negócio

1. Token é gerado uma vez e **exibido uma única vez**. Armazenado só como hash.
2. Escopos por recurso e operação; token sem o escopo → `403` dizendo qual falta.
3. `allowed_ips` opcional; preenchido, restringe a origem.
4. Token expirado ou revogado → `401`.
5. Rate limit por token, com contadores em Redis. Headers `X-RateLimit-Limit`, `-Remaining` e `-Reset` em toda resposta.
6. Requisições da API pública **respeitam RLS** — o tenant vem do token.
7. Erros no formato RFC 7807, iguais aos da API interna.
8. Paginação por cursor; `limit` máximo de 1.000, padrão 100.
9. Toda requisição é registrada em `api_requests`; retenção de 30 dias.
10. Escrita pela API pública passa pelas **mesmas validações** dos services — sem atalho.
11. OpenAPI gerado a partir do código, servido em `/api/public/v1/openapi.json`.
12. Versionamento no caminho. `v1` não sofre mudança quebrando contrato.
13. `last_used_at` atualizado de forma assíncrona, para não onerar a requisição.
14. Máximo de 10 tokens ativos por tenant.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | token válido autentica e resolve o tenant | ~0,4 s |
| integração | token inválido, expirado e revogado → 401 | ~0,4 s |
| integração | escopo faltando → 403 com detalhe | ~0,3 s |
| integração | `allowed_ips` restringe | ~0,3 s |
| integração | **rate limit GET → 429 com Retry-After** | ~0,5 s |
| integração | headers de rate limit em toda resposta | ~0,3 s |
| integração | **token do tenant A não lê dado de B** | ~0,5 s |
| integração | escrita respeita as validações do service | ~0,5 s |
| integração | paginação por cursor, limite de 1.000 | ~0,4 s |
| integração | erro em RFC 7807 | ~0,2 s |
| integração | requisição registrada | ~0,3 s |
| integração | 11º token → 422 | ~0,2 s |
| **meta** | **OpenAPI válido e cobrindo todas as rotas** | ~0,4 s |
| frontend | token exibido uma vez | ~0,3 s |

**Total:** ~5,0 s

## 9. Descobertas

- **A busca do token é a única consulta que não pode passar pelo RLS** — o tenant é
  justamente o que ela descobre. A saída foi uma função `SECURITY DEFINER`
  (`api_token_lookup`), o mesmo padrão que a 079 usou para leitura entre escritórios, e
  não afrouxar a política da tabela: uma política mais permissiva valeria para toda
  consulta a `api_tokens`, inclusive as que já sabem o tenant.
- **Os schemas públicos são próprios, não os internos reaproveitados.** É o custo de um
  arquivo (`app/public/schemas.py`) para comprar a regra 12: os schemas internos mudam
  quando a UI muda, e a v1 pública não pode quebrar porque alguém renomeou um campo numa
  tela.
- **Dois bugs de plataforma apareceram, e os dois eram anteriores à spec.** O handler de
  erro RFC 7807 descartava os headers da `HTTPException` — então `Retry-After` no 429 e
  `WWW-Authenticate` no 401 nunca chegavam ao cliente, coisa que só dói em API para
  máquina. E `paginate_keyset` comparava `timestamptz` com o texto do cursor, o que
  estourava na SEGUNDA página de qualquer listagem ordenada por data. Os dois foram
  corrigidos no lugar certo, e valem para a API interna também.
- **`last_used_at` é atualizado depois da resposta sair.** É a regra 13, e o motivo é
  concreto: um `UPDATE` no caminho crítico faria toda LEITURA da API custar uma escrita —
  e o integrador que varre a base a cada dez minutos pagaria isso mil vezes por dia.
- **O log usa sessão própria, e é por isso que ele existe.** A requisição que falhou é a
  que mais interessa registrar; gravar na sessão da própria requisição significaria perder
  exatamente esses registros no rollback.
- **`allowed_ips` responde 401, não 403.** Um 403 diria ao IP recusado que o token é
  válido, transformando a restrição de origem num oráculo para quem roubou a credencial.
- **O 403 de escopo diz QUAL escopo falta.** São sete recursos e onze escopos; um "acesso
  negado" seco obrigaria o integrador a adivinhar, e adivinhar termina em pedir todos os
  escopos "para garantir" — que é o oposto do que escopo existe para fazer.
- **O OpenAPI público é filtrado, com fecho transitivo dos `$ref`.** Servir o schema
  inteiro exporia trezentos endpoints internos a quem tem um token de integração. Filtrar
  só os caminhos não bastava: um `$ref` que não resolve quebra qualquer gerador de
  cliente, então o documento carrega os schemas referenciados e os schemas DELES, até o
  ponto fixo.
- **O contrato virou teste meta com a lista escrita à mão.** Gerar a expectativa a partir
  do código faria o teste concordar com qualquer coisa. Do jeito que ficou, endpoint que
  some e endpoint que aparece sem passar pela spec quebram o CI — inclusive o "só um
  endpointzinho a mais", que é superfície que alguém vai usar e que depois não pode sumir.
- **Revogar não apaga.** O log aponta para o token, e apagar a linha transformaria o
  histórico em `token_id` nulo — o oposto de auditoria.
- **O download devolve 302 para URL assinada.** Streamar o binário pela API gastaria banda
  e memória do Rito para entregar o que o object storage entrega melhor; a URL expira em
  cinco minutos, como no download da UI.

## 10. Definição de pronto

- [x] Checklist padrão
- [x] Isolamento por token provado — listagem e acesso direto, os dois pelo RLS
- [x] OpenAPI completo — 22 endpoints, com schemas que se bastam
- [x] Commit `feat(095): API pública v1`
