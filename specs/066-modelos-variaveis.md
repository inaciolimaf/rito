# 066 — Modelos: engine de variáveis

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 065 · **Status:** ⬜ pendente

---

## 1. Objetivo

O que faz um modelo valer a pena: escrever a petição uma vez e gerar centenas preenchidas com
os dados reais de cada processo — inclusive valores e datas **por extenso**.

## 2. Escopo

- Catálogo de variáveis de cliente, processo, escritório e usuário
- Nó de variável no editor, com autocomplete
- Resolução com dados reais
- **Extenso** para datas e valores monetários
- Variável ausente sinalizada, nunca silenciosa
- Preview com processo escolhido

## 3. Fora de escopo

- Geração de PDF → 067 · Condicionais e laços (fora do escopo; sem lógica no modelo)

## 4. Modelo de dados

```sql
CREATE TABLE template_variables (        -- catálogo global
  key TEXT PRIMARY KEY,                  -- 'customer.name'
  label TEXT NOT NULL,
  category TEXT NOT NULL,                -- 'customer' | 'lawsuit' | 'account' | 'user'
  data_type TEXT NOT NULL,               -- 'text' | 'date' | 'money' | 'number'
  supports_extenso BOOLEAN NOT NULL DEFAULT false,
  description TEXT
);
```
Global, sem tenant. Migration `066_template_variables.py` + seed do catálogo.

**Catálogo** (conforme `docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §4.9):

- **Cliente:** `name`, `identification`, `document`, `birthdate`, `birthdate_extenso`,
  `marital_status`, `nationality`, `occupation`, `full_address`, `email`, `phone`,
  `mother_name`, `rep_name`, `rep_identification`, `rep_document`, `rep_full_address`
- **Processo:** `process_number`, `type`, `court`, `county`, `court_division`, `stage`,
  `responsible`, `fees_value`, `fees_value_extenso`, `case_value`, `case_value_extenso`,
  `filing_date`, `filing_date_extenso`, `archived_date`, `outcome`
- **Escritório:** `name`, `alternate_name`, `identification`, `full_address`, `phone`,
  `email`, `site`
- **Usuário:** `name`, `occupation`, `identification`, `oab`, `cellphone`

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/template-variables?category=` |
| POST | `/api/v1/templates/{id}/render` → `{lawsuit_id, customer_id?}` |
| POST | `/api/v1/templates/{id}/preview` → HTML com variáveis destacadas |

`render` devolve `{content, missing_variables[], warnings[]}`.

## 6. Front-end

**Reutiliza:** `EntityPicker`, `FormModal`
**Cria:** `VariableNode` (nó TipTap, exibido como chip), `VariablePicker` (autocomplete por `{{`),
`VariablePanel` (lista lateral por categoria), `RenderPreviewDialog`, `MissingVariablesAlert`
**Rota:** dentro do editor

## 7. Regras de negócio

1. Sintaxe `{{categoria.chave}}`; no editor é um **nó**, não texto — não quebra ao editar em volta.
2. Chave desconhecida é preservada literalmente e reportada em `warnings`.
3. Variável sem valor no registro entra em `missing_variables` e é renderizada como `______`
   (linha para preencher à mão), **nunca** como string vazia silenciosa.
4. **Extenso de dinheiro:** `1.234,56` → "um mil, duzentos e trinta e quatro reais e cinquenta e seis centavos". Trata zero, singular ("um real"), centavos sozinhos e milhões.
5. **Extenso de data:** `15/05/2026` → "quinze de maio de dois mil e vinte e seis".
6. Processo com múltiplas partes: `customer.*` usa a parte informada em `customer_id`; sem ela,
   usa o primeiro cliente do polo ativo. Ambiguidade vira `warning`.
7. `user.*` resolve pelo usuário que está gerando.
8. Endereço completo é montado a partir dos campos, omitindo os vazios sem deixar vírgula solta.
9. Render é **função pura** dado o contexto — testável sem banco.
10. Preview destaca em amarelo as variáveis resolvidas e em vermelho as ausentes.
11. Resolver o contexto inteiro é uma query só; nada de N+1 por variável.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | **extenso de dinheiro: tabela com 20 valores** | ~0,3 s |
| unit | extenso: zero, um real, só centavos, milhão | ~0,2 s |
| unit | **extenso de data: tabela com 12 datas** | ~0,2 s |
| unit | endereço sem vírgula solta com campos vazios | ~0,2 s |
| unit | chave desconhecida é preservada e avisada | ~0,1 s |
| unit | ausente vira `______` e entra em missing | ~0,2 s |
| integração | render com processo real preenche tudo | ~0,5 s |
| integração | múltiplas partes: usa a informada | ~0,3 s |
| integração | sem `customer_id` usa o polo ativo e avisa | ~0,3 s |
| integração | `user.*` resolve o gerador | ~0,2 s |
| integração | **contexto em 1 query** | ~0,4 s |
| frontend | autocomplete por `{{` | ~0,5 s |
| frontend | chip não quebra ao editar em volta | ~0,4 s |
| frontend | preview destaca resolvidas e ausentes | ~0,4 s |

**Total:** ~4,2 s

> O extenso é a parte que mais gera bug. As duas tabelas de casos não são negociáveis.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Extenso com 32 casos testados · Commit `feat(066): modelos — engine de variáveis`
