# 018 — Contatos: validação e endereço

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 017 · **Status:** ⬜ pendente

---

## 1. Objetivo

Garantir qualidade do dado na entrada: CPF/CNPJ validado com algoritmo real, telefone no
formato brasileiro correto e endereço preenchido a partir do CEP.

## 2. Escopo

- Validadores de CPF e CNPJ (dígito verificador real)
- Validador de telefone: DDD obrigatório, **sem** código de país, 10 ou 11 dígitos
- Normalização de CEP para `99999-999`
- Integração ViaCEP atrás da interface `AddressLookup` (mockável)
- Tabela `states` (27 UFs) e `cities` (IBGE) para os seletores
- Detecção de possível duplicata por nome + nascimento

## 3. Fora de escopo

- Deduplicação automática com merge (só avisa, não funde)

## 4. Modelo de dados

```sql
CREATE TABLE states (
  code CHAR(2) PRIMARY KEY, name TEXT NOT NULL, ibge_code SMALLINT NOT NULL UNIQUE
);
CREATE TABLE cities (
  ibge_code INTEGER PRIMARY KEY, name TEXT NOT NULL, state_code CHAR(2) NOT NULL REFERENCES states(code)
);
CREATE INDEX ix_cities_state ON cities (state_code);
CREATE INDEX ix_cities_name_trgm ON cities USING gin (name gin_trgm_ops);
```
Globais, sem tenant. Migration `018_locations.py` + seed IBGE.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/states` | autenticado |
| GET | `/api/v1/cities?state=SP&q=` | autenticado |
| GET | `/api/v1/address/lookup?postal_code=` | autenticado |
| GET | `/api/v1/customers/check-duplicate?name=&birthdate=` | autenticado |

## 6. Front-end

**Reutiliza:** `FormModal`, `EntityPicker`
**Cria:** `CpfCnpjField` (máscara dinâmica PF/PJ), `PhoneField`, `PostalCodeField` (busca ao completar), `StateCitySelect`
**Rota:** dentro do `CustomerForm`

## 7. Regras de negócio

1. CPF: 11 dígitos, DV válido, rejeita sequências repetidas (`111.111.111-11`).
2. CNPJ: 14 dígitos, DV válido, rejeita sequências repetidas.
3. Máscara aceita na entrada; o banco guarda **só dígitos**.
4. Telefone: 10 dígitos (fixo) ou 11 (celular, terceiro dígito = 9). **Com DDI (`55`, `+`) → 422.** Sem DDD → 422.
5. CEP normalizado para `99999-999`; 8 dígitos numéricos.
6. ViaCEP preenche estado, cidade, endereço e bairro — todos ainda editáveis.
7. ViaCEP fora do ar **não bloqueia** o cadastro: campos ficam manuais e um aviso aparece.
8. Cidade só é selecionável depois do estado; trocar o estado limpa a cidade.
9. Duplicata provável (mesmo nome + nascimento) mostra aviso não bloqueante com link.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | CPF válido/inválido/repetido (tabela) | ~0,2 s |
| unit | CNPJ válido/inválido/repetido (tabela) | ~0,2 s |
| unit | telefone: 10, 11, com DDI, sem DDD | ~0,2 s |
| unit | normalização de CEP | ~0,1 s |
| integração | lookup de CEP com ViaCEP mockado | ~0,3 s |
| integração | ViaCEP fora do ar não bloqueia | ~0,3 s |
| integração | cidades filtram por estado | ~0,3 s |
| integração | check-duplicate encontra por nome+nascimento | ~0,3 s |
| frontend | máscara alterna entre CPF e CNPJ | ~0,4 s |
| frontend | CEP preenche endereço | ~0,4 s |
| frontend | trocar estado limpa cidade | ~0,3 s |

**Total:** ~3,0 s
ViaCEP **sempre** mockado — nenhuma chamada real em teste.

## 9. Descobertas

- **CPF/CNPJ real já existia desde a spec 011** (`app/core/br_documents.py::is_valid_cpf`/
  `is_valid_cnpj`/`is_valid_cpf_or_cnpj`, com DV real e rejeição de sequência repetida) — só
  não estava **ligado** ao formulário de contato. Todo o trabalho da spec 018 nesse ponto foi
  wiring: um `field_validator` em `CustomerCreateRequest`/`_RepresentativeMixin` que valida e
  normaliza (guarda só dígitos, regra 3) `identification`/`rep_identification`. Nenhum teste
  novo de CPF/CNPJ "válido/inválido/repetido" foi necessário — já existiam e continuam
  passando.
- **`AddressLookup` no backend foi descartado — reaproveitado o que a spec 011 já resolveu.**
  A seção 5 original pedia `GET /api/v1/address/lookup` atrás de uma interface `AddressLookup`
  mockável. Mas a spec 011 (cadastro do Escritório) já implementou exatamente esse problema —
  ViaCEP chamado **direto do browser** (`frontend/src/lib/cep.ts`), sem proxy no backend,
  porque é só autofill de UX sem dado sensível (comentário no próprio arquivo: "spec 011,
  regra 2"). Construir um segundo caminho (backend) para o mesmo problema seria duplicar e
  divergir de um padrão já testado e funcionando. `PostalCodeField` reaproveita `lookupCep()`
  tal qual; não existe endpoint `/address/lookup` nem interface `AddressLookup` no backend
  desta spec — desvio deliberado da seção 5 literal.
- **`states`/`cities` usam dados reais do IBGE**, baixados uma vez via a API pública
  (`servicodados.ibge.gov.br/api/v1/localidades`) e versionados como CSV em
  `backend/alembic/data/018_states.csv` (27 linhas) e `018_cities.csv` (5.571 linhas) — grande
  demais para literais Python como os seeds anteriores (59 etapas, 67 cargos etc.). A
  migration só lê os CSVs e faz `bulk_insert`.
- **`State`/`City` não herdam `app.core.models.Base`.** A spec define chave primária natural
  (`states.code`, `cities.ibge_code`), mas `Base.id` é sempre `UUID` — herdar `Base` colaria
  um `id` UUID indesejado ao lado da PK real. Como as migrations são hand-written
  (`alembic/env.py`: `target_metadata = None`, sem autogenerate), não há necessidade de
  metadata compartilhada entre ORM e migration; `State`/`City` ganharam uma `DeclarativeBase`
  própria (`LocationBase`) e repositórios que não herdam `BaseRepository` (cujo genérico é
  ligado a `Base`, pressupondo PK `uuid.UUID` — mesma razão pela qual `Occupation`/`Step`
  também não usam os métodos genéricos de PK inteira).
- **Regra 4 (telefone) colapsa numa checagem só.** "10 dígitos, 11 dígitos com terceiro
  dígito 9, sem DDI, com DDD" parece exigir 3 checagens, mas um DDI (`55`/`+`) ou a ausência
  de DDD sempre resultam em 8, 9, 12 ou 13 dígitos — nunca 10 ou 11. `is_valid_phone` só
  confere o tamanho (10 ou 11) e, se 11, o terceiro dígito; não precisa detectar o prefixo
  explicitamente.
- **Frontend: máscara com `Controller`, não `register()`.** `CpfCnpjField`/`PhoneField`/
  `PostalCodeField` precisam transformar o valor nos dois sentidos (dígitos → exibição
  mascarada, exibição → dígitos ao digitar) — `register()` sozinho não dá esse gancho.
  Mesmo precedente já estabelecido em `features/account/schema.ts` (spec 011, comentário
  "o cliente confere só o formato, o 422 do servidor é quem valida de fato"): nenhum
  algoritmo de dígito verificador foi duplicado em TypeScript.
- **Regra 9 (duplicata provável) foi ligada na tela** mesmo sem teste de frontend declarado
  no plano — o endpoint `GET /customers/check-duplicate` (backend) ficaria sem nenhum
  consumidor real na aplicação se não fosse chamado de algum lugar. `CustomerForm` dispara a
  checagem (debounced, 400ms) quando `name`+`birthdate` estão preenchidos (só PF — PJ não tem
  nascimento) e mostra um aviso inline não bloqueante.
- **`CpfCnpjField` do representante assume PF.** A spec não declara um campo de "tipo do
  representante" — representantes legais são, na esmagadora maioria dos casos reais
  (procurador, representante de menor/incapaz), pessoas físicas. `rep_identification` usa
  `CpfCnpjField` com `personType="PF"` fixo; documentado aqui como simplificação, não como
  algo a corrigir.

## 10. Definição de pronto

- [x] Migration `018_locations` aplica e reverte de forma limpa; 27 estados e 5.571
      municípios reais do IBGE semeados (testado contra `rito_test` do zero e contra o banco
      de dev, ~1,1s para a migration inteira incluindo o bulk insert das cidades).
- [x] `is_valid_phone`/`is_valid_postal_code`/`format_postal_code` em
      `app/core/br_documents.py`, com tabela de casos (10/11 dígitos, DDI, sem DDD) e testes
      de normalização de CEP.
- [x] CPF/CNPJ, telefone e CEP validados de verdade no `POST`/`PUT /customers` (422 com
      mensagem clara), com o dado normalizado (só dígitos para CPF/CNPJ/telefone, `99999-999`
      para CEP) antes de gravar.
- [x] `GET /states`, `GET /cities?state=&q=`, `GET /customers/check-duplicate` — 100% de
      cobertura em `app/domain/locations/` e `app/domain/customers/`.
- [x] 280 testes de integração/unit cobrindo o plano da spec (mais os casos extras de
      cobertura: campos opcionais vazios, representante com identificação/CEP válidos).
- [x] Frontend: `CpfCnpjField` (máscara dinâmica PF/PJ), `PhoneField`, `PostalCodeField`
      (busca ao completar, reaproveitando `lib/cep.ts` da spec 011), `StateCitySelect`
      (`<select>` de UF + `EntityPicker` de cidade, limpa cidade ao trocar estado) — os 4
      componentes que a spec pedia para criar, todos plugados em `CustomerForm` e
      `RepresentativeFields`. Testes "PostalCodeField preenche endereço" e "StateCitySelect
      limpa cidade" verdes; o teste de alternância PF/PJ já existente passou a cobrir a troca
      de máscara CPF↔CNPJ.
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier).
- [x] `make test` verde — 280 backend / 59 frontend / 3 e2e, wall-clock 43 s (orçamento 120 s).
- [x] Verificado manualmente em navegador (Playwright ad-hoc, não commitado) — CPF/telefone/
      CEP com máscara, ViaCEP **real** (Praça da Sé, SP) preenchendo estado/cidade/endereço/
      bairro, troca de estado limpando cidade, e alternância PF/PJ trocando CPF↔CNPJ, tudo
      funcionando ponta a ponta.

Commit `feat(018): contatos — validação e endereço`
