# 011 — Escritório (account)

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 005 · **Status:** ✅ concluída

---

## 1. Objetivo

Cadastro do escritório dono do tenant: identificação, endereço, contatos, logotipo e fuso
horário. Esses dados alimentam as variáveis de modelo (spec 066) e o cabeçalho dos documentos.

## 2. Escopo

- Tabela `accounts` (1:1 com `tenants`)
- Campos do levantamento: razão social, nome fantasia, CPF/CNPJ, país, cidade, estado, CEP,
  endereço, bairro, celular, telefone, e-mail principal, e-mail financeiro, site, timezone
- Upload de logotipo
- Tela `Conta e assinatura > Dados da conta`

## 3. Fora de escopo

- Plano, assinatura e checkout (produto interno, fora do clone)
- Setores/unidades → spec 054 (centros de custo cobrem o caso)

## 4. Modelo de dados

```sql
CREATE TABLE accounts (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id       UUID NOT NULL UNIQUE REFERENCES tenants(id),
  name            TEXT NOT NULL,              -- razão social
  alternate_name  TEXT NOT NULL,              -- nome fantasia
  identification  TEXT NOT NULL,              -- CPF/CNPJ
  country         TEXT NOT NULL DEFAULT 'BRASIL',
  state           CHAR(2),
  city            TEXT,
  postal_code     TEXT,
  street          TEXT,
  region          TEXT,                       -- bairro
  cellphone       TEXT,
  phone           TEXT,
  email           CITEXT NOT NULL,
  email_admin     CITEXT NOT NULL,            -- financeiro
  site            TEXT,
  timezone        TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
  logo_key        TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
RLS ligado. Migration `011_accounts.py`.

Timezones aceitos (8): `America/Sao_Paulo`, `America/Noronha`, `America/Belem`,
`America/Manaus`, `America/Rio_Branco`, `Europe/Lisbon`, `Atlantic/Madeira`, `Atlantic/Azores`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/account` | qualquer autenticado |
| PUT | `/api/v1/account` | GESTOR |
| POST | `/api/v1/account/logo` | GESTOR (multipart) |

## 6. Front-end

**Reutiliza:** `FormModal` (layout inline), `ConfirmDialog`
**Cria:** `AccountForm`, `LogoUploader`
**Rota:** `/subscription/account`

## 7. Regras de negócio

1. CPF/CNPJ validado com algoritmo real; formato aceito com ou sem máscara, armazenado sem.
2. CEP no formato `99999-999`; consulta ViaCEP preenche estado, cidade, endereço e bairro.
3. Timezone restrito à lista de 8; valor fora dela → 422.
4. Logotipo: PNG/JPG/SVG, máx. 2 MB, redimensionado para 512 px no maior lado.
5. E-mail principal e financeiro podem ser iguais, mas ambos são obrigatórios.
6. Só GESTOR altera. Demais perfis leem.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | GET/PUT completo | ~0,3 s |
| integração | CNPJ inválido → 422 | ~0,2 s |
| integração | Colaborador → 403 no PUT | ~0,2 s |
| integração | timezone fora da lista → 422 | ~0,2 s |
| integração | RLS: tenant A não lê account de B | ~0,3 s |
| integração | upload de logo acima de 2 MB → 422 | ~0,3 s |
| frontend | `AccountForm` valida e submete | ~0,4 s |

**Total:** ~1,9 s

## 9. Descobertas

**Campos obrigatórios corrigidos contra o levantamento ADVBOX.** A seção 4 desta spec
declarava `state`/`city`/`postal_code`/`street`/`region`/`cellphone`/`phone` como
nullable, mas `docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` (linha 313) marca todos esses campos
como "obrig." no formulário real. Implementado como `NOT NULL` na migration, seguindo a
instrução de consultar o ADVBOX para os campos e regras reais.

**PUT faz criar-ou-atualizar (upsert).** A spec não define um endpoint de criação
separado, e não existe (ainda) nenhuma spec de onboarding/provisionamento de tenant que
crie a linha de `accounts` automaticamente. Decisão: `GET /account` devolve 404 antes do
primeiro `PUT`; `PUT /account` cria se não existir, atualiza se existir. Reavaliar se uma
spec futura de onboarding vier a criar a conta antecipadamente.

**FileStorage novo (CLAUDE.md §5, OCP) — MinIO como infra local, sem fake.** Como
Postgres/Redis, MinIO já vinha provisionado no `docker-compose.yml` desde a spec 001 —
os testes usam o serviço de verdade (bucket `rito-test` separado do de dev), nunca uma
implementação fake, seguindo o mesmo precedente estabelecido para infra local (spec 009).
`S3FileStorage` (boto3, síncrono, rodado via `asyncio.to_thread`) fica atrás da interface
`FileStorage` (Protocol) — trocar MinIO por S3 de produção não muda nenhum consumidor.
`public_url` gera uma URL presigned (7 dias) em vez de assumir bucket público — mais
seguro, sem precisar configurar bucket policy.

**CPF/CNPJ e ViaCEP: mesma decisão de "fonte única" da política de senha (spec 009).**
O algoritmo completo de dígito verificador (`app/core/br_documents.py`) só existe no
backend; o frontend confere só o tamanho (11/14 dígitos) e deixa o 422 do servidor ser a
validação de verdade — evita duplicar um algoritmo não-trivial em TypeScript. ViaCEP
(regra 2) é chamado direto do browser (CORS já permite), não via backend — é só autofill
de UX, sem dado sensível, sem necessidade de auditoria; mockado via MSW nos testes
(nenhum teste toca rede real, nem para essa chamada "inofensiva").

**Bug real no FastAPI descoberto ao escrever o router: `test_permission_coverage.py`
estava silenciosamente cego.** O `pyproject.toml` fixa `fastapi>=0.115` sem teto — o `uv
sync` já vinha resolvendo `0.141.1`, que trocou `include_router` para um mecanismo de
resolução preguiçosa (`_IncludedRouter`). Isso quebrou o scanner do teste de cobertura de
permissão (spec 005): `candidate_app.routes` deixou de conter `APIRoute` diretamente para
QUALQUER rota incluída via `include_router` (ou seja, toda rota real do app, já que
`/auth` e agora `/account` só existem assim) — o scanner (`isinstance(route, APIRoute)`)
sempre encontrava zero rotas e passava vazio, não porque não havia violação, mas porque
não achava rota nenhuma. O teste negativo (`test_scanner_catches_a_route_without_permission`)
não pegou isso porque registrava rotas DIRETO no app de prova (sem `include_router`),
testando um caminho que a produção nunca usa. Corrigido usando
`fastapi.routing.iter_route_contexts` (função pública, não prefixada com `_`, que resolve
o caminho com prefixo aplicado mesmo atrás de `_IncludedRouter`) e reescrevendo o teste
negativo para também usar `include_router`, replicando o caminho real. Sem esse achado,
as 3 rotas novas de `/account` (e teoricamente qualquer rota futura) não estariam sendo
verificadas pela regra 5 do CLAUDE.md.

**Extensão do `apiRequest` para `FormData`.** O upload de logo precisava de multipart, mas
o cliente único de API (`lib/api.ts`, decisão da spec 006) sempre fazia
`JSON.stringify(body)` e fixava `Content-Type: application/json`. Em vez de criar um
segundo caminho de requisição (duplicando retry de refresh/parsing de erro), `apiRequest`
agora detecta `body instanceof FormData` e pula o JSON.stringify/Content-Type nesse caso —
mantém um cliente só, como a decisão original pedia.

**Dependência nova: sessão de domínio autenticada.** Nenhuma rota de domínio existia antes
de 011 — só `/auth` (pré-JWT, tenant por header) e rotas RBAC sintéticas de teste. Rotas
de domínio de verdade precisam do tenant do JWT do usuário logado, não do header. Criada
`get_session_for_current_user` em `app/domain/auth/deps.py` (não em `core/deps.py`, mesma
exceção deliberada já usada por `core/permissions.py` desde a spec 005: essa dependência
depende de `get_current_user`, que é de domínio).

**Pillow e boto3-stubs adicionados.** `pillow` para redimensionar o logotipo (regra 4,
único jeito de processar imagem sem reinventar um decodificador PNG/JPEG à mão);
`boto3-stubs[s3]` como dev-dependency para o `mypy --strict` tipar as chamadas do boto3
sem precisar de `# type: ignore` espalhado.

**`enable_rls_statements()` cria índice redundante em `accounts` — pulado.**
`accounts.tenant_id` já é `UNIQUE` (1:1 com `tenants`), o que cria seu próprio índice; a
migration usa `enable_rls_statements("accounts")[:-1]` para pular só o último statement
(o `CREATE INDEX` que duplicaria isso), evitando o índice redundante que o checklist da
spec 010 cobra.

**Nenhuma jornada e2e nova.** O plano de testes da spec (seção 8) não pede e2e para esta
feature — GET/PUT/upload já são cobertos por integração, e o componente por teste de
frontend. Máximo de 25 jornadas: continua 2/25.

## 10. Definição de pronto

- [x] Migration `011_accounts.py` aplicada, RLS ligado, sem índice redundante
- [x] `GET`/`PUT /api/v1/account` e `POST /api/v1/account/logo` implementados com RBAC
      (GESTOR escreve, qualquer autenticado lê)
- [x] CPF/CNPJ validado com algoritmo real (`app/core/br_documents.py`)
- [x] CEP validado no formato `99999-999`; ViaCEP preenche estado/cidade/endereço/bairro
      no frontend (autofill client-side, nunca bloqueia o usuário)
- [x] Logotipo: PNG/JPG/SVG, máx. 2 MB, redimensionado a 512px no maior lado (raster);
      SVG passa direto (vetorial)
- [x] `AccountForm`/`LogoUploader` criados; `FormModal`/`ConfirmDialog` reutilizados
      (mapApiErrorToFields e o dialog de confirmação ao trocar logotipo)
- [x] Todos os testes do plano (seção 8) escritos, mais 22 testes adicionais de cobertura
      de erro (CEP inválido, logo sem conta, bucket novo no MinIO, algoritmo de CPF/CNPJ,
      redimensionamento)
- [x] `make lint` verde (ruff, black, mypy --strict, eslint, tsc, prettier)
- [x] `make test` verde, wall-clock ~25-28s (< 120s)
- [x] `test-timing.json` atualizado
- [x] `ROADMAP.md` → ✅
- [x] Commit `feat(011): escritório (account)`
