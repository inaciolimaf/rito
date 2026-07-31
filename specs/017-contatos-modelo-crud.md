# 017 — Contatos: modelo e CRUD

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 016 · **Status:** ⬜ pendente

---

## 1. Objetivo

O cadastro de pessoas — clientes, partes contrárias, terceiros. Pessoa física e jurídica no
mesmo modelo, com bloco opcional de representante legal.

## 2. Escopo

- Tabela `customers` com todos os campos do levantamento
- Discriminador PF/PJ
- Bloco de representante legal (embutido na mesma tabela, prefixo `rep_`)
- Tabela `marital_statuses` (6 valores)
- CRUD + upload de foto
- Modal de criação/edição

## 3. Fora de escopo

- Validação de CPF/CNPJ e ViaCEP → 018
- Listagem, filtros e dashboard → 019
- Nuvem de documentos do contato → 063

## 4. Modelo de dados

```sql
CREATE TYPE person_type AS ENUM ('PF','PJ');

CREATE TABLE marital_statuses (
  id SMALLINT PRIMARY KEY, name TEXT NOT NULL UNIQUE
);  -- CASADO(A), DIVORCIADO(A), SEPARADO(A), SOLTEIRO(A), UNIÃO ESTÁVEL, VIÚVO(A)

CREATE TABLE customers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  type person_type NOT NULL DEFAULT 'PF',
  name TEXT NOT NULL,
  identification TEXT,                     -- CPF/CNPJ, sem máscara
  document TEXT,                           -- RG
  origin_id UUID NOT NULL REFERENCES customer_origins(id),
  notes TEXT,
  birthdate DATE,
  marital_status_id SMALLINT REFERENCES marital_statuses(id),
  occupation TEXT,
  gender TEXT,                             -- 'F' | 'M'
  nationality TEXT,
  mother_name TEXT,
  cellphone TEXT, phone TEXT, email CITEXT,
  country TEXT NOT NULL DEFAULT 'BRASIL',
  postal_code TEXT, state CHAR(2), city TEXT, street TEXT, region TEXT,
  number_pis TEXT, number_ctps TEXT, number_cid TEXT,
  photo_key TEXT,
  has_representative BOOLEAN NOT NULL DEFAULT false,
  rep_name TEXT, rep_identification TEXT, rep_document TEXT, rep_birthdate DATE,
  rep_country TEXT, rep_state CHAR(2), rep_city TEXT,
  rep_street TEXT, rep_region TEXT, rep_postal_code TEXT,
  is_archived BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (NOT has_representative OR rep_name IS NOT NULL)
);
CREATE UNIQUE INDEX uq_customers_identification
  ON customers (tenant_id, identification) WHERE identification IS NOT NULL;
```
RLS ligado. Migration `017_customers.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| POST | `/api/v1/customers` | COLABORADOR |
| GET/PUT | `/api/v1/customers/{id}` | COLABORADOR |
| DELETE | `/api/v1/customers/{id}` | ADMINISTRADOR (soft delete → `is_archived`) |
| POST | `/api/v1/customers/{id}/photo` | COLABORADOR |
| GET | `/api/v1/marital-statuses` | autenticado |

## 6. Front-end

**Reutiliza:** `FormModal`, `EntityPicker`, `ConfirmDialog`
**Cria:** `CustomerForm` (com alternância PF/PJ), `RepresentativeFields`, `PhotoUploader`
**Rota:** modal sobre `/customers`

Campos por tipo:
- **PF:** RG, nascimento, estado civil, profissão, sexo, nacionalidade, nome da mãe, PIS, CTPS, CID
- **PJ:** oculta os acima; `identification` vira CNPJ e o rótulo muda para Razão social

## 7. Regras de negócio

1. `name` e `origin_id` são obrigatórios em ambos os tipos.
2. Alternar PF↔PJ limpa os campos exclusivos do tipo anterior.
3. `identification` é único por tenant quando informado (índice parcial permite vários nulos).
4. `has_representative = true` exige `rep_name` (constraint no banco).
5. Exclusão é **soft** (`is_archived`); contato com processo vinculado nunca é apagado de fato.
6. Foto: PNG/JPG, máx. 5 MB, redimensionada para 400 px.
7. `gender` aceita só `F` ou `M`.
8. Nome é armazenado como digitado e indexado com `unaccent` + `pg_trgm` para busca.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD PF completo | ~0,5 s |
| integração | CRUD PJ completo | ~0,4 s |
| integração | sem origem → 422 | ~0,2 s |
| integração | CPF duplicado no tenant → 409 | ~0,3 s |
| integração | mesmo CPF em outro tenant é aceito | ~0,3 s |
| integração | dois contatos sem identification coexistem | ~0,3 s |
| integração | representante sem nome → 422 | ~0,2 s |
| integração | delete arquiva em vez de apagar | ~0,3 s |
| integração | RLS entre tenants | ~0,3 s |
| frontend | alternar PF/PJ mostra e limpa campos | ~0,5 s |
| frontend | representante abre e valida | ~0,4 s |

**Total:** ~3,7 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(017): contatos — modelo e CRUD`
