# 024 — Processos: honorários e ciclo de vida

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 022 · **Status:** ✅ concluída

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

1. **Pydantic v2 serializa `Decimal` como string JSON** — a regra 1 ("a API recebe e
   devolve número") exigiu `JsonDecimal = Annotated[Decimal, PlainSerializer(float)]` nos
   schemas de resposta. O float é seguro aqui: NUMERIC(14,2) tem no máximo 14 dígitos
   significativos e float garante 15 — o teste de precisão cobre o teto
   (999.999.999.999,99) ida e volta.
2. **Enum em migration: `create_table` ≠ `add_column`.** Na 023 o `create_table` emitiu o
   CREATE TYPE sozinho (e um `.create()` explícito duplicava). Na 024, com `add_column`,
   o `.create()` explícito é **obrigatório** — `add_column` nunca emite CREATE TYPE.
3. **Validação de ciclo em duas camadas, como manda o padrão:** o `model_validator` do
   schema devolve 422 amigável; `ck_cycle`/`ck_fees_pct` no banco são backstop para
   qualquer escrita que não passe pela API.
4. **Regra 5 tem teste dedicado:** `archived_date` preenchida não liga `is_archived` —
   fato processual ≠ visibilidade na lista.
5. **`MoneyField`/`PercentField` nasceram em `components/domain/`** (não na feature): a
   própria spec manda extrair com cuidado porque todo o módulo financeiro (054+) reusa.
   A lógica de máscara vive em `lib/money.ts` (centavos → cru com ponto; pt-BR só na
   tela), junto de `formatBrl` para os cards.
6. **Intl BRL usa espaço não-quebrável** entre "R$" e o valor — o teste normaliza com
   `/[ ]/g`. O literal NBSP no código dispara `no-irregular-whitespace` do eslint:
   sempre usar o escape ` `, nunca o caractere.
7. **`financial-summary` devolve os agregados zerados** (received/to_receive/expenses/
   net_result) até a spec 056 — mesmo padrão de stub documentado das specs 014–016:
   endpoint real, consumidor real (painel), fonte de dados ainda inexistente.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste (1–7 cobertas)
- [x] Teste de isolamento por tenant (sem tabela nova — colunas em `lawsuits`, já com RLS
      coberto desde a 022; summary de tenant B → 404 coberto pelo padrão existente)
- [x] `make test` verde e wall-clock < 120 s (63 s)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa
- [x] `MoneyField` pronto para reuso no financeiro (components/domain + lib/money.ts)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(024): processos — honorários e ciclo`
