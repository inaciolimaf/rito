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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Seed IBGE idempotente · Commit `feat(018): contatos — validação e endereço`
