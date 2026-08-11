# 055 — Financeiro: contas e cartões

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 054 · **Status:** ✅ concluída

---

## 1. Objetivo

Onde o dinheiro entra e sai. Contas bancárias e cartões de crédito, com o comportamento
particular do cartão: ciclo de fechamento e vencimento de fatura.

## 2. Escopo

- Tabela `bank_accounts` com 5 tipos
- Tabela `financial_institutions` com ~95 instituições (seed)
- Ciclo e vencimento para cartão
- Saldo inicial e conta padrão
- Cálculo de saldo atual
- Tela `Configurações > Financeiro > Contas e cartões`

## 3. Fora de escopo

- Lançamentos → 056 · Fluxo de caixa → 059 · Fatura de cartão como documento → fora do escopo

## 4. Modelo de dados

```sql
CREATE TYPE account_kind AS ENUM ('CORRENTE','POUPANCA','INVESTIMENTO','CARTAO_CREDITO','OUTRO');

CREATE TABLE financial_institutions (   -- global
  id SMALLINT PRIMARY KEY, name TEXT NOT NULL UNIQUE, compe_code TEXT
);

CREATE TABLE bank_accounts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  kind account_kind NOT NULL,
  name TEXT NOT NULL,
  institution_id SMALLINT REFERENCES financial_institutions(id),
  agency TEXT, account_number TEXT,
  cycle_day SMALLINT,        -- fechamento da fatura (só cartão)
  due_day SMALLINT,          -- vencimento da fatura (só cartão)
  initial_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
  is_default BOOLEAN NOT NULL DEFAULT false,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name),
  CHECK (kind <> 'CARTAO_CREDITO' OR (cycle_day BETWEEN 1 AND 31 AND due_day BETWEEN 1 AND 31)),
  CHECK (kind =  'CARTAO_CREDITO' OR (cycle_day IS NULL AND due_day IS NULL))
);
CREATE UNIQUE INDEX ux_accounts_default ON bank_accounts (tenant_id)
  WHERE is_default AND is_active;
```
RLS ligado. Migration `055_bank_accounts.py` + seed das instituições.

O índice único parcial garante **uma só conta padrão** por tenant — no banco, não na aplicação.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/bank-accounts?status=&kind=` | financial ≥ READ_ONLY |
| POST/PUT/DELETE | `/api/v1/bank-accounts[/{id}]` | financial = FULL |
| POST | `/api/v1/bank-accounts/{id}/set-default` | financial = FULL |
| GET | `/api/v1/bank-accounts/{id}/balance?at=` | financial ≥ READ_ONLY |
| GET | `/api/v1/financial-institutions?q=` | autenticado |

## 6. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `MoneyField`, `ConfirmDialog`
**Cria:** `BankAccountForm` (campos condicionais por tipo), `InstitutionSelect`,
`AccountBalanceCard`
**Rota:** `/settings/financial?tab=accounts`

## 7. Regras de negócio

1. `CARTAO_CREDITO` **exige** `cycle_day` e `due_day`; os demais tipos não podem tê-los (constraints).
2. Uma só conta padrão ativa por tenant (índice único parcial). Definir nova desmarca a anterior, em transação.
3. Saldo atual = `initial_amount` + entradas − saídas dos lançamentos **pagos** e não internos.
4. Cartão não tem saldo, tem **fatura**: soma dos lançamentos do ciclo corrente.
5. Ciclo do cartão: dia `cycle_day` do mês até o dia anterior do mês seguinte. Dia 31 em mês curto usa o último dia.
6. Conta com lançamento não pode ser excluída — só inativada.
7. Inativar conta padrão exige eleger outra antes → 409.
8. Nome único por tenant.
9. Saldo inicial é imutável depois do primeiro lançamento; alterar exige ajuste por lançamento.
10. Escrita exige `financial_access = FULL`.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD dos 5 tipos | ~0,5 s |
| integração | cartão sem ciclo → 422 | ~0,2 s |
| integração | conta corrente com ciclo → 422 | ~0,2 s |
| integração | **só uma padrão ativa** (tentativa concorrente) | ~0,4 s |
| integração | trocar padrão desmarca a anterior | ~0,3 s |
| integração | excluir conta com lançamento → 409 | ~0,3 s |
| integração | inativar padrão sem substituta → 409 | ~0,3 s |
| integração | saldo ignora internos e não pagos | ~0,4 s |
| unit | ciclo do cartão com dia 31 em fevereiro | ~0,2 s |
| integração | saldo inicial imutável após lançamento | ~0,3 s |
| frontend | formulário alterna campos por tipo | ~0,4 s |

**Total:** ~3,5 s

## 9. Descobertas

- **Regras 3/4/6/9 (saldo real, fatura, "conta em uso" e imutabilidade do saldo
  inicial) dependem de `lançamentos`, que só chega na spec 056.** Mesma situação já
  documentada em customer_origins (016)/stages (015)/action_groups (014)/financial_
  categories (054): a validação/estrutura fica pronta, mas o comportamento real (que
  depende de dados que ainda não existem) é adiado e testado como o que É hoje, não
  como será. Concretamente: `GET /bank-accounts/{id}/balance` devolve `initial_amount`
  puro; `DELETE` é incondicional; `PUT` aceita `initial_amount` livremente. Nada
  disso é bug — é o estado documentado até a 056 existir.
- **"~95 instituições" não tinha lista enumerada em `docs/ADVBOX-ESPECIFICACAO-
  COMPLETA.md`** (diferente das 61 categorias/59 etapas, que tinham). Buscados dados
  reais do Banco Central via BrasilAPI (`GET /api/banks/v1`, internet real do
  sandbox — mesmo recurso já usado pra IBGE na spec 018) e filtrados para nomes com
  "BCO"/"BANCO"/"CAIXA" + os 6 maiores bancos digitais cujo nome oficial não usa
  essas palavras (Nubank, PagBank, PicPay, Mercado Pago, Neon, Stone) — 129
  instituições reais e verificáveis, perto do "~95" aproximado da spec.
- **Bug real de concorrência encontrado e corrigido antes do commit.** Trocar a
  conta padrão (`set_default`/`create` com `is_default=true`) sem um `session.
  flush()` explícito entre desmarcar a conta antiga e marcar a nova deixava o
  SQLAlchemy livre para emitir os 2 `UPDATE`s no mesmo `executemany`, em qualquer
  ordem — como `ux_accounts_default` não é `DEFERRABLE`, a ordem errada (marcar a
  nova ANTES de desmarcar a antiga) violava a constraint mesmo o resultado final
  estando correto. Pego pelo teste de concorrência
  (`test_so_uma_padrao_ativa_mesmo_tentando_burlar_pelo_banco`) antes do merge —
  corrigido com `flush()` explícito nos dois pontos.
- **`JsonDecimal` virou o 3º domínio reaproveitando o mesmo alias** (lawsuits, crm,
  financial) — extraído de `lawsuits/schemas.py` para `app/core/schemas.py` (regra
  dos 3 usos, CLAUDE.md §6), com `lawsuits`/`crm` atualizados para importar do novo
  lugar central.
- **`card_cycle_range` (regra 5) foi pra `app/core/dates.py`**, o módulo único de
  datas do projeto (spec 040) — mesmo padrão de `add_business_days`/`next_occurrence`,
  reaproveitando `month_end`/`shift_month` já existentes em vez de recalcular.
- **Achado de processo, não de código:** um dev server de smoke test manual
  (Playwright, usado pra verificar a UI num browser real) ficou rodando na porta
  5173 depois de um `pkill` que não terminou o processo de verdade — o `run-tests.sh`
  seguinte, via `reuseExistingServer` do Playwright, reaproveitou esse processo
  zumbi (apontando pro backend de smoke test, não pro da suíte), derrubando as 9
  jornadas e2e por falha de login. Falso negativo, não regressão — confirmado com
  `ps aux`/`ss -ltnp`, corrigido matando o processo, e um rerun limpo saiu 100%
  verde. Documentado em memória (`feedback_dev_server_ports_e2e_collision`) pra não
  repetir: smoke test manual de UI não deve usar as portas 5173/8000.
- **UI verificada manualmente num browser real (Playwright).** Campos de fechamento/
  vencimento aparecem SÓ pra cartão de crédito (regra 1); busca assíncrona de
  instituição funcionando (unaccent — "ITAÚ" encontra "ITAÚ UNIBANCO S.A."); definir
  conta padrão atualiza a lista e o `AccountBalanceCard` no topo, mostrando "Fatura
  do ciclo" pra cartão vs. "Saldo" pros demais tipos.

## 10. Definição de pronto

- [x] Escopo implementado, nada além (lançamentos ficam pra 056; fluxo de caixa pra
      059; fatura como documento fica fora do escopo — nenhum tocado aqui)
- [x] Todas as regras de negócio COM DADO HOJE têm teste (11 testes de integração + 6
      unit cobrindo as regras 1, 2, 5, 7, 8, 10 com dado real; regras 3/4/6/9 testadas
      no comportamento atual — deferido, documentado, não pulado em silêncio)
- [x] Teste de isolamento por tenant — `bank_accounts`/`financial_institutions` são
      tabelas novas; `financial_institutions` é global (sem RLS, como `dre_groups`);
      `bank_accounts` tem RLS via `enable_rls_statements`, testado em
      `test_tenant_a_nao_ve_conta_de_tenant_b` (leitura E escrita — PUT por id de
      outro tenant → 404)
- [x] `make test` verde e wall-clock < 300 s (256 s — 796 backend, 147 frontend, 9
      e2e; nenhuma jornada e2e nova, dentro do orçamento de +4 s previsto no §8; um
      run anterior teve falsos negativos — flake de perf pré-existente em
      test_inbox_perf.py sob carga concorrente + contaminação de porta por um dev
      server de smoke test — ambos investigados, confirmados alheios a esta spec, e
      o rerun limpo saiu 100% verde)
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Unicidade da conta padrão garantida no banco — índice único parcial
      `ux_accounts_default`, testado direto contra o Postgres (raw SQL bypassando a
      aplicação) além do fluxo normal via API
- [x] Componentes reutilizáveis: `DataTable`/`FormModal`/`MoneyField`/`ConfirmDialog`
      reaproveitados sem duplicar; `BankAccountForm`/`InstitutionSelect`/
      `AccountBalanceCard` novos, do jeito que o §6 previa
- [x] Commit `feat(055): Financeiro — contas e cartões`
