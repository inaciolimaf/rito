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

- **`process_image` (spec 011) precisou virar parametrizável.** Regra 6 pede limites
  diferentes dos já usados por logo (spec 011) e avatar (spec 012): 5 MB/400px/sem SVG, contra
  2 MB/512px/com SVG dos outros dois. Em vez de duplicar a função (regra dos 3 usos: este é o
  3º chamador), `app/core/image_processing.py::process_image` ganhou parâmetros opcionais
  (`max_size_bytes`, `max_dimension_px`, `allowed_content_types`, `invalid_format_message`),
  todos com default idêntico ao comportamento anterior — logo/avatar não mudaram nada, só o
  upload de foto de contato passa seus próprios valores explicitamente.
- **Bug pego na verificação manual em navegador (não em teste automatizado):**
  `DialogContent` (`components/ui/dialog.tsx`, usado por `FormModal`/`ConfirmDialog` em todo o
  app) não tinha `max-height` nem scroll — um formulário tão grande quanto o de contato (30+
  campos) ficava com metade dos campos inacessíveis, sem como rolar até eles nem confirmar a
  seleção de origem no `EntityPicker` (a lista de opções ficava fora da área visível e não
  scrollável). Como nenhum modal anterior era grande o suficiente para expor isso, o bug era
  latente desde a spec 007. Corrigido com `max-h-[85vh] overflow-y-auto` no `DialogContent` —
  afeta todo modal do app (mudança mínima, verificada contra os testes existentes de
  `FormModal`/`ConfirmDialog`/`a11y`, todos continuam verdes sem edição).
- **"Sem origem → 422" não precisou de exceção customizada.** `origin_id` é campo obrigatório
  sem default no schema Pydantic — a ausência já vira 422 automático antes de chegar no
  service. Diferente das specs 014/015 (onde havia um teste explícito para "grupo/fase
  inexistente" apontado por um id que não existe), a spec 017 só pede testar a AUSÊNCIA de
  origem, não a referência a um id inválido — por isso não há uma `OriginNotFoundError`
  dedicada aqui. Uma referência a um `origin_id`/`marital_status_id` que não existe de fato
  vira `IntegrityError` não tratada (500) — aceitável porque a única forma de enviar esses
  campos pela UI é via `EntityPicker`/`<select>`, que só oferecem ids reais.
- **Regra 2 (alternar PF↔PJ limpa campos exclusivos) é aplicada nos dois lados.** No frontend,
  um `useEffect` no `CustomerForm` limpa os campos de PF assim que `type` muda para `PJ`
  (cobre a UX, testado). No backend, `CustomerService.create`/`update` também força esses
  campos para `None` quando `type == PJ`, **independente do que o cliente enviar** — garante
  que a regra vale mesmo se alguém chamar a API direto, não só via formulário.
- **Sem listagem ainda (spec 019).** A rota `/customers` desta spec só hospeda o modal de
  criação/edição (seção 6: "Rota: modal sobre /customers") — não há grid, paginação nem
  filtros; o card do último contato criado/editado na sessão existe só para dar acesso ao
  upload de foto e ao botão "Editar" sem precisar de uma lista de verdade.
- **`EntityPicker` para `origin_id`, `<select>` nativo para `marital_status_id`/`gender`** —
  origem é uma lista que cresce livremente (CRUD da spec 016), estado civil e sexo são listas
  fixas pequenas (6 e 2 valores), mesmo critério já usado nas specs 014/015/016.

## 10. Definição de pronto

- [x] Migration `017_customers` aplica e reverte de forma limpa (testada contra `rito_test` do
      zero e contra o banco de dev).
- [x] 6 estados civis semeados (tabela global e imutável, mesmo padrão de `occupations`/`steps`).
- [x] RLS ligado em `customers` (não em `marital_statuses`, que é global) + teste de isolamento
      entre tenants.
- [x] CRUD completo (PF e PJ), soft delete via `is_archived`, upload de foto com limites
      próprios (5 MB/400px/PNG+JPG), unicidade de `identification` por tenant via índice
      parcial, índice trigram para busca por nome.
- [x] 255 testes de integração cobrindo o plano da spec (mais os casos extras de cobertura:
      renomear identification duplicada, gender inválido, limpeza de campos PF→PJ, foto
      inválida/grande demais/contato inexistente) — 100% de cobertura em
      `app/domain/customers/`.
- [x] Frontend: `CustomerForm` (alternância PF/PJ), `RepresentativeFields`, `PhotoUploader` —
      os 3 componentes que a spec pedia para criar. Testes "alternar PF/PJ mostra e limpa
      campos" e "representante abre e valida" verdes (~1,1 s no total).
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier).
- [x] `make test` verde — 255 backend / 57 frontend / 3 e2e, wall-clock 43 s (orçamento 120 s).
- [x] Verificado manualmente em navegador (Playwright ad-hoc, não commitado) — CRUD PF/PJ,
      upload de foto e alternância PF/PJ funcionando ponta a ponta (achado e corrigido o bug
      do `DialogContent` durante essa verificação).

Commit `feat(017): contatos — modelo e CRUD`
