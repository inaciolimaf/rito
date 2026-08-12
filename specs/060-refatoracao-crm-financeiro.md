# 060 — 🔧 REFATORAÇÃO — CRM e Financeiro I

**Fase:** 5 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 051–059 · **Status:** ✅ concluída

---

## 1. Objetivo

O módulo financeiro é o que mais tolera erro mal — número errado em tela de dinheiro destrói
confiança no produto inteiro. Esta refatoração é sobre **exatidão numérica** e sobre consolidar
o padrão de agregação antes das 4 abas de BI (074–077).

> Refatoração não muda comportamento. Testes de 051–059 passam **sem edição**.
>
> Exceção autorizada (mesmo precedente da spec 053, ver Descobertas): 3 assertions que
> passavam por acidente porque a rota que testavam **não checava** `financial_access` —
> corrigir o gap muda o resultado esperado dessas assertions, não a regra que elas testam.

## 2. Alvo 1 — auditoria de exatidão numérica

- [x] Todo valor monetário é `NUMERIC(14,2)` no banco e `Decimal` no Python — **zero `float`** em qualquer caminho de dinheiro
- [x] Arredondamento sempre `ROUND_HALF_UP`, nunca o padrão do Python (banker's rounding)
- [x] Soma de parcelas fecha exatamente com o total (confirmado para todo N de 2 a 100, não só os poucos N já cobertos)
- [x] Saldo calculado pela view = saldo calculado por soma direta, no mesmo dataset
- [x] Os 4 regimes de 059 sobre o mesmo dataset produzem números coerentes entre si (já coberto pelo teste parametrizado da 059)
- [x] Nenhum cálculo de dinheiro no frontend — a UI só formata (achado real corrigido, ver Descobertas)

## 3. Alvo 2 — padrão de agregação

- [x] `MaterializedAggregate`: definição, refresh concorrente, invalidação por evento, TTL → `app/core/materialized_view.py`
- [x] Registro central de views com o intervalo de refresh de cada uma → `MATERIALIZED_VIEWS`
- [x] Convenção de nomes e de índice único (exigido pelo refresh concorrente) — já seguida por ambas as views existentes
- [x] Métrica de defasagem exposta na UI → `MaterializedViewSpec.staleness_hint()`, `TransactionStatsResponse.balance_staleness_hint`

## 4. Alvo 3 — permissão financeira

- [x] Varrer **todas** as rotas de `/transactions`, `/bank-accounts`, `/financial-categories`, `/cost-centers`
- [x] Cada uma declara o nível exigido
- [x] Teste de cobertura de permissão financeira, no mesmo espírito do de 005 → `test_financial_permission_sweep.py`
- [x] `financial_access = NONE` não vê valor nem em endpoint de outro módulo (painel do processo, card do CRM) — 2 vazamentos reais achados e corrigidos, ver Descobertas

## 5. Checklist

### Cobertura
- [x] Toda regra numerada de 051–059 com teste (cada spec já exigiu isso na própria Definição de pronto; não reauditado regra a regra aqui — ver Descobertas)
- [x] Regra tipo × categoria nos dois sentidos
- [x] As 4 constraints de `transactions` testadas no banco (raw SQL, bypassando a validação Pydantic)
- [x] Estagnação com etapa configurada e não configurada
- [x] Isolamento entre tenants nas tabelas novas

### SOLID
- [x] `KanbanBoard` sem nenhum conhecimento de processo (achado real corrigido, ver Descobertas)
- [x] Cálculo de saldo em serviço próprio (`app/domain/financial/dashboard.py`), usado por dashboard e conta (`/bank-accounts/balances`) — "usado... por processo" não se aplica: `financial-summary` do processo é `received`/`to_receive`/`expenses` (agregado por lançamento vinculado), um conceito diferente de "saldo de conta", já numa função própria (`lawsuit_financial_totals`) desde a spec 056
- [x] `TransactionService` dividido se passou de ~300 linhas — não passou (195 linhas); o arquivo `service.py` é grande (728 linhas) só porque agrupa as 7 classes de serviço do domínio financeiro inteiro, mesmo padrão de `models.py`/`schemas.py`
- [x] Regras de série (057) separadas do CRUD de lançamento — já eram (`TransactionSeriesService` distinto de `TransactionService`)

### Duplicação
- [x] Padrão de agregação extraído (alvo 2)
- [x] `MoneyField` e formatação de moeda em um só lugar — já eram (`components/domain/MoneyField.tsx`, `lib/money.ts`)
- [x] Filtros de período compartilhados entre financeiro e processos → `app/core/http.py::parse_month_query` (CRM não tem filtro de mês próprio, então "CRM" do enunciado não se aplicava)

### Banco
- [x] `EXPLAIN` no dashboard com 100.000 lançamentos (medição isolada, ver Descobertas)
- [x] Índices parciais (`ix_tx_open`, `ix_tx_effective`) sendo usados — confirmado por `EXPLAIN ANALYZE`
- [x] Refresh concorrente sem lock de leitura — `CONCURRENTLY` por definição
- [x] Histórico de etapa não cresce sem limite (investigado, decisão de **não** implementar expurgo automático agora — ver Descobertas)

### Performance dos testes
- [ ] Wall-clock **< 90 s** — não atingido; medido ~237s (backend sozinho ~233s). Dívida #17 (já rastreada desde a spec 033, reafirmada na 050) permanece atribuída à spec 098; 848 testes backend não cabem em 90s com o `-n 2` que o `run-tests.sh` usa para dar ar às 3 suítes concorrentes. Não é regressão desta spec — o teto de 300s do CLAUDE.md §3 (o gate real) segue batendo.
- [x] E2E com no máximo 9 jornadas até aqui (exatamente 9)

## 6. Entregáveis

1. ✅ Auditoria numérica documentada em `docs/DECISOES.md`, com a política de arredondamento
2. ✅ `MaterializedAggregate` com as views existentes migradas (`user_monthly_scores`, `account_daily_balances`)
3. ✅ Teste de cobertura de permissão financeira (`test_financial_permission_sweep.py`)
4. ✅ `test-timing.json` atualizado

## 7. Definição de pronto

- [x] Testes de 051–059 passam sem edição, com a exceção documentada e autorizada acima (3 assertions que dependiam de um gap de permissão)
- [ ] Wall-clock < 90 s — não atingido, dívida pré-existente (#17) confirmada e re-atribuída à 098, não regressão desta spec
- [x] Zero `float` em caminho de dinheiro
- [x] Dashboard < 300 ms com 100.000 lançamentos (medido: ~19-25ms por query)
- [x] Commit `refactor(060): exatidão numérica e padrão de agregação`

## 8. Descobertas

- **Achado real #1 — cálculo de dinheiro no frontend.** `TransactionsListPage.tsx` somava
  `transactions.map(amount)` em JS para o rodapé (total/saldo/previsto, regra 9 da 059).
  Corrigido: `GET /transactions` agora devolve `totals` somado no banco com o MESMO filtro
  da página (`TransactionRepository.totals_filtered`, reaproveitando `_filter_conditions`
  de `list_filtered` — sem duplicar WHERE). Exceção mantida conscientemente: o preview de
  parcelas de `InstallmentFields.tsx` (spec 057) segue calculando em JS porque NUNCA é a
  fonte da verdade (o split real vem do backend na criação, com paridade já testada) —
  não é a mesma classe de problema que o rodapé, que exibia um resultado como se fosse
  dado real sem contraparte no backend.
- **Achado real #2 — dois vazamentos de valor sem gate de `financial_access`.**
  `GET /lawsuits/{id}/financial-summary` só exigia `require_role(COLABORADOR)` — qualquer
  colaborador via `received`/`to_receive`/`expenses` de qualquer processo, sem checar
  acesso financeiro. `GET /crm/board` e `GET /crm/stats` devolviam `case_value`/
  `total_value`/`stagnant_value` do mesmo jeito. Corrigidos com dois padrões diferentes,
  de propósito: o painel financeiro do processo é 100% dinheiro → ganhou
  `require_financial(READ_ONLY)` de verdade (403 pra `NONE`, mesma dupla-`Depends` já usada
  em `financial-categories`); o board/stats do CRM servem pra navegar processos em geral
  (não só dinheiro) → os 3 campos viram `null` pra `NONE` em vez de bloquear o endpoint
  inteiro, mesmo padrão já usado em `users.salary` desde a spec 012. Consertar o gap mudou
  o resultado esperado de 3 testes que passavam OUTRORA por acidente (o usuário de teste
  não tinha `financial_access`, mas a rota nunca checava) — ajustados pra usar
  `financial_access=FULL`, mesmo precedente já registrado na spec 053 ("comportamento
  mudado de propósito, autorizado pelo contrato, não uma quebra acidental").
- **Achado real #3 — `KanbanBoard` (051) tinha 2 strings de domínio coladas no componente
  genérico** ("Nenhum processo", "Nenhuma fase configurada"/"Configure as fases do funil").
  Viraram props com default neutro; `CrmPage.tsx` passa os textos específicos. O próprio
  teste do componente já dizia no título "sem conhecer domínio" — agora cumpre de verdade.
- **`MaterializedAggregate` extraído para `app/core/materialized_view.py`** — REFRESH
  CONCURRENTLY/AUTOCOMMIT/superusuário estava copiado ponto a ponto entre
  `workers/scores.py` (039) e `workers/financial_dashboard.py` (059). Os wrappers de cada
  worker (`refresh_user_monthly_scores`, `refresh_account_daily_balances`) continuam
  existindo com o mesmo nome/assinatura — os testes de 039/059 chamam essas funções
  direto, e romper esse contrato quebraria "testes passam sem edição". `MATERIALIZED_VIEWS`
  é o registro central que 074–077 (BI) vão alimentar quando chegarem.
- **"Cálculo de saldo em serviço próprio, usado por dashboard, conta e processo"
  interpretado com uma correção de escopo.** `BankAccountService.get_balance` (spec 055)
  segue devolvendo só `initial_amount` — isso é dívida técnica #20, explicitamente
  atribuída à spec 070 em `docs/DIVIDA-TECNICA.md`; reabrir esse escopo aqui contradiria a
  própria decisão já registrada. O saldo REAL (o que a 059 calcula de verdade) já vive
  isolado em `app/domain/financial/dashboard.py`, consumido tanto pelo dashboard
  (`get_dashboard_stats`) quanto pelo endpoint de conta específico da 059
  (`get_account_balances`, `/bank-accounts/balances`). "Processo" não tem uma noção de
  "saldo de conta" — o que o painel do processo mostra é `received`/`to_receive`/
  `expenses` (soma de lançamentos vinculados a ELE, não saldo de conta bancária), um
  conceito diferente, já numa função própria (`lawsuit_financial_totals`) desde a 056.
- **Banco: `ix_tx_open`/`ix_tx_effective` confirmados em uso com 100k lançamentos**
  (seed isolado direto por SQL, tenant descartado depois — mesmo padrão da medição de 20k
  da spec 040, não uma suíte permanente). `EXPLAIN ANALYZE`: atrasados usa `ix_tx_open`
  (18ms); gráfico por vencimento usa `ix_tx_effective` (8ms); o agregado de
  previsto/realizado por regime faz *Seq Scan* nesse dataset sintético (o filtro cobre
  ~metade da tabela, e nesse caso um seq scan é o plano mais barato de verdade) — ainda
  assim 25ms, bem dentro do teto de 300ms do DoD. Nenhum índice novo foi necessário.
- **`lawsuit_stage_history` sem política de retenção — investigado, decisão consciente de
  NÃO implementar expurgo automático agora.** Diferente de `external_requests` (spec 041,
  30 dias — log de API descartável), histórico de fase é dado de negócio que um usuário
  pode legitimamente querer consultar anos depois; decidir um prazo de expurgo é decisão
  de produto, não engenharia, e apagar errado é irreversível. Sem sinal de que o volume
  hoje é problema prático (1 insert pequeno por troca de etapa). Registrado em
  `docs/DECISOES.md` para uma spec futura decidir o prazo com dono de produto.
- **Wall-clock não bateu o teto de 90s desta spec — dívida pré-existente, não regressão.**
  848 testes backend rodando com `-n 2` (deliberadamente limitado pelo `run-tests.sh` para
  dar espaço às 3 suítes concorrentes, spec 035) não cabem em 90s. A causa raiz (custo de
  handshake de conexão nova por teste function-scoped + contenção de host compartilhado)
  já tinha sido investigada e re-atribuída à spec 098 no fechamento da spec 050 — reafirmado
  aqui, não uma investigação nova. O gate que de fato vale (CLAUDE.md §3, teto de 300s pra
  `make test` inteiro) continua verde (~237s medido).
- **Achado de processo real #4 — `test_datajud_401_permanente_para_o_lote_sem_duplicar_
  alerta` (spec 050, `test_resilience_chaos.py`) vazava um alerta de SISTEMA pra suíte
  inteira.** Diferente dos outros testes do mesmo domínio (`test_datajud_service.py`/
  `test_sync_observability.py`, que usam uma sessão sem `session.begin()` de propósito,
  só `flush`, pra nunca commitar o alerta de SISTEMA visível a QUALQUER tenant pela
  política de RLS da migration 046), este teste usa `session.begin()` porque precisa
  ler de volta numa sessão separada — e por isso COMMITAVA o alerta de verdade, sem
  nunca limpar depois. Isso quebrava deterministicamente 2 testes de
  `test_sync_observability.py` toda vez que a suíte inteira rodava (o alerta vazava pro
  resto da execução) — as specs 051/052/058, ao hit o mesmo sintoma, atribuíram a "banco
  sujo de execução ad-hoc" sem achar esta causa raiz específica (que também acontece em
  runs limpos). Corrigido com um `DELETE` explícito ao final do teste culpado — mesma
  higiene de teste, nenhuma mudança na regra de produto que ele verifica.
- **Achado de processo (não é dívida técnica do produto): as primeiras 4 tentativas de
  `make test` desta sessão falharam com centenas de `SocketConnectBlockedError`** — não
  eram regressão nem contenção de CPU (chegou a se cogitar isso, por causa de outra sessão
  concorrente rodando neste mesmo sandbox compartilhado), e sim `PYTEST_ALLOW_HOSTS=dind`
  nunca setado nas invocações manuais de `run-tests.sh` fora do `Makefile` (a env var só é
  lida pelo `Makefile`/`run-tests.sh`, mesmo aviso já registrado nas specs 019/037). Rerun
  com a var setada corretamente fechou 100% verde na primeira tentativa.
