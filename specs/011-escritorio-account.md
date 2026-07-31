# 011 — Escritório (account)

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 005 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão do `CLAUDE.md` §8 · Commit `feat(011): escritório (account)`
