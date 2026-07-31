# 024 — Processos: honorários e ciclo de vida

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 022 · **Status:** ⬜ pendente

---

## 1. Objetivo

Os campos financeiros e as datas que marcam o ciclo do processo. São a base de todo o BI das
specs 074–077 — rentabilidade, safra, tempo médio e custo dependem exclusivamente daqui.

## 2. Escopo

- Valor da causa, valor dos honorários, percentual
- Contingenciamento (3 níveis)
- Datas de ciclo: fechamento, trânsito em julgado, arquivamento
- Resultado (ganho / perdido / acordo)
- Painel de resumo financeiro no processo

## 3. Fora de escopo

- Lançamentos financeiros → 056
- Cálculo de rentabilidade → 076

## 4. Modelo de dados

```sql
CREATE TYPE contingency_level AS ENUM ('PROVAVEL','POSSIVEL','REMOTA');
CREATE TYPE lawsuit_outcome  AS ENUM ('GANHO','PERDIDO','ACORDO');

ALTER TABLE lawsuits
  ADD COLUMN case_value       NUMERIC(14,2),   -- valor da causa (fees_expec)
  ADD COLUMN fees_value       NUMERIC(14,2),   -- honorários (fees_money)
  ADD COLUMN fees_percentage  NUMERIC(5,2),
  ADD COLUMN contingency      contingency_level,
  ADD COLUMN closure_date     DATE,            -- fechamento do contrato
  ADD COLUMN transit_date     DATE,            -- trânsito em julgado
  ADD COLUMN archived_date    DATE,            -- arquivamento
  ADD COLUMN outcome          lawsuit_outcome,
  ADD CONSTRAINT ck_fees_pct  CHECK (fees_percentage IS NULL OR fees_percentage BETWEEN 0 AND 100),
  ADD CONSTRAINT ck_cycle     CHECK (
        (transit_date  IS NULL OR closure_date IS NULL OR transit_date  >= closure_date)
    AND (archived_date IS NULL OR transit_date IS NULL OR archived_date >= transit_date));

CREATE INDEX ix_lawsuits_closure  ON lawsuits (tenant_id, closure_date)  WHERE closure_date  IS NOT NULL;
CREATE INDEX ix_lawsuits_transit  ON lawsuits (tenant_id, transit_date)  WHERE transit_date  IS NOT NULL;
CREATE INDEX ix_lawsuits_archived ON lawsuits (tenant_id, archived_date) WHERE archived_date IS NOT NULL;
CREATE INDEX ix_lawsuits_outcome  ON lawsuits (tenant_id, outcome)       WHERE outcome       IS NOT NULL;
```
Migration `024_lawsuit_financials.py`.

## 5. Contratos de API

Campos incorporados a `POST`/`PUT /lawsuits/{id}`.

| Método | Rota |
|---|---|
| GET | `/api/v1/lawsuits/{id}/financial-summary` |

Retorna: valor da causa, honorários contratados, recebido, a receber, despesas, resultado
líquido — os três últimos zerados até a spec 056.

## 6. Front-end

**Reutiliza:** `FormModal`, `StatCard`
**Cria:** `MoneyField` (máscara `999.999,99`), `PercentField`, `ContingencySelect`,
`LawsuitFinancialPanel`

`MoneyField` e `PercentField` são reutilizados por todo o módulo financeiro — extraia com cuidado.

## 7. Regras de negócio

1. Valores em `NUMERIC(14,2)`. A UI usa vírgula decimal; a API recebe e devolve número.
2. `fees_percentage` entre 0 e 100.
3. Ordem cronológica obrigatória: fechamento ≤ trânsito em julgado ≤ arquivamento (constraint).
4. `outcome` só é aceito se `closure_date` estiver preenchida — resultado exige processo fechado.
5. Preencher `archived_date` **não** arquiva o registro (`is_archived`): são coisas distintas — uma é fato processual, a outra é visibilidade na lista.
6. Contingenciamento é opcional e não afeta cálculo nenhum aqui; é insumo do BI.
7. Valores negativos → 422.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | salvar e ler valores monetários sem perda de precisão | ~0,3 s |
| integração | percentual acima de 100 → 422 | ~0,2 s |
| integração | trânsito anterior ao fechamento → 422 | ~0,3 s |
| integração | arquivamento anterior ao trânsito → 422 | ~0,3 s |
| integração | outcome sem fechamento → 422 | ~0,2 s |
| integração | valor negativo → 422 | ~0,2 s |
| unit | `MoneyField` formata e parseia ida e volta | ~0,2 s |
| frontend | painel financeiro renderiza zerado | ~0,3 s |

**Total:** ~2,0 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · `MoneyField` pronto para reuso no financeiro · Commit `feat(024): processos — honorários e ciclo`
