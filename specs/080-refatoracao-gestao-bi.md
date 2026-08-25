# 080 — 🔧 REFATORAÇÃO — Gestão e BI

**Fase:** 7 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 071–079 · **Status:** ✅ concluída

---

## 1. Objetivo

Oitenta por cento. Duas prioridades: **auditar o isolamento entre tenants** agora que a spec 079
abriu a primeira exceção legítima à regra, e garantir que o BI não vire o gargalo de performance
do produto.

> Refatoração não muda comportamento. Testes de 071–079 passam **sem edição**.

## 2. Alvo 1 — auditoria completa de isolamento

> Premissa corrigida: a 079 **não** estendeu a política de RLS de `lawsuits`, `posts` e
> `lawsuit_parties` (ver Descobertas da 079). As 52 políticas de domínio continuam
> idênticas; a fronteira do parceiro vive em funções `SECURITY DEFINER`. A auditoria
> abaixo cobriu as duas coisas — as políticas e as funções.

- [x] Revisar **cada** política de RLS do banco, uma por uma, e documentar o porquê de cada exceção — `docs/SEGURANCA-RLS.md`, 56 políticas, 6 exceções
- [x] Teste matricial: para cada tabela com RLS, verificar que tenant B não lê, não escreve, não atualiza e não apaga dado de A
- [x] Teste específico de parceria: parceiro vê exatamente o processo compartilhado e nada mais
- [x] Verificar que a exceção de parceria **não** vazou para `transactions`, `customers`, `templates`, `reports` ou BI
- [x] Verificar que a exceção de modelo público (068) não colide com a de parceria — `public_templates` é catálogo global sem RLS, tabela diferente
- [x] Confirmar que nenhuma query usa `SET ROLE` ou conexão com `BYPASSRLS` — teste estático + `rolbypassrls = false` verificado em runtime

Esta auditoria é a mais importante do projeto. Reserve tempo.

## 3. Alvo 2 — performance do BI

Sete views materializadas foram criadas. Com volume real, refresh pode travar o banco.

- [x] Semear 100.000 processos, 500.000 tarefas e 200.000 lançamentos — `backend/scripts/bench_aggregates.py`
- [x] Medir o refresh de cada view e registrar em `docs/DECISOES.md`
- [x] Nenhum refresh acima de 60 s — o pior é 1,77 s (`bi_lawsuit_cycles`)
- [x] Confirmar que `CONCURRENTLY` não bloqueia leitura durante o refresh — `SELECT` concorrente em 0,05 s durante refresh de 1,08 s
- [x] Avaliar refresh incremental onde o completo for caro — não se justifica a 1,8 s a cada 8 h; reavaliar acima de 10 s
- [x] Confirmar que o refresh sequencial não estoura conexões do pool — uma conexão por vez, engine descartável por view

## 4. Alvo 3 — consolidar o padrão de relatório

- [x] 072 fez página genérica dirigida por metadados. As 4 abas de BI seguem o mesmo padrão? — seguiam só por convenção; agora pela casca
- [x] `BiTabPanel` reutilizável: indicadores + gráfico + tabela + defasagem — as 4 abas migradas
- [x] Divisão por zero tratada em **um** lugar, não em quatro — `app/core/ratios.py`
- [x] Formatação de indicador (moeda, percentual, dias) unificada — `formatBrl`/`formatDays` já eram compartilhados; nada a extrair
- [x] Aviso de amostra pequena com o mesmo componente nas abas 075, 076 e 077 — `SmallSampleWarning`

## 5. Checklist

### Cobertura
- [x] Toda regra numerada de 071–079 com teste
- [x] Os 5 testes de vazamento de 079 passando
- [x] Divisão por zero em todos os indicadores
- [x] Nulo distinguido de zero nos ciclos (076)
- [x] Toda view materializada no registry (078) — teste de consistência já existia

### SOLID
- [x] Cálculo de BI em services, nunca no router — nenhum `select(` em `bi/router.py` ou `reports/router.py`
- [x] Uma query de agregação por indicador, não uma por card
- [x] `MaterializedAggregate` de 060 usado por todas as sete views (oito, com `timesheet_daily`)

### Duplicação
- [x] Padrão de aba de BI extraído (alvo 3)
- [x] Cálculo de ciclo em um só lugar (076 e 077 usam os mesmos) — `bi_lawsuit_cycles` é a fonte das duas
- [x] Definição de "custo fixo" (grupos 2, 3, 5, 7) como constante única

### Banco
- [x] Refresh de todas as views medido com volume (alvo 2)
- [x] Índices das views sendo usados — `Bitmap Index Scan on ux_bi_cycles` pela view barreira
- [x] Política de retenção de `access_logs` e `aggregate_refresh_log` ativa — a segunda **não existia**; criada aqui

### Performance dos testes
- [ ] Wall-clock **< 90 s** — ver Descobertas: nesta máquina o backend sozinho leva ~165 s com `-n 2`; a meta é do host de referência da spec, não deste sandbox
- [x] E2E com no máximo 10 jornadas até aqui — 9 jornadas
- [x] Fixture de volume só nos testes de performance, marcada como lenta — o volume nem entra na suíte: vive em `scripts/bench_aggregates.py`

## 6. Entregáveis

1. [x] `docs/SEGURANCA-RLS.md` — cada política, cada exceção, com justificativa e o teste que a cobre
2. [x] Medição de refresh com volume real em `docs/DECISOES.md`
3. [x] `BiTabPanel` com as 4 abas migradas
4. [x] `test-timing.json` atualizado

## 7. Definição de pronto

- [x] Testes de 071–079 passam sem edição — nenhum teste anterior foi tocado
- [ ] Wall-clock < 90 s — não atingível neste host (ver Descobertas); backend estável em ~165 s com `-n 2`
- [x] Matriz de isolamento completa e verde
- [x] Nenhum refresh acima de 60 s com 100.000 processos — pior caso 1,77 s
- [x] Commit `refactor(080): auditoria de isolamento e performance do BI`

## 8. Descobertas

- **A premissa da spec estava errada, e isso é o achado mais importante da auditoria.**
  A 080 foi escrita assumindo que a 079 tinha estendido a política de RLS de
  `lawsuits`/`posts`/`lawsuit_parties`. Não estendeu: a 079 recusou esse caminho
  justamente porque o processo do parceiro passaria a entrar nas agregações dele. O
  banco tem 56 políticas, 50 são o isolamento padrão idêntico, e as 6 exceções não têm
  nada a ver com o processo compartilhado — são a linha bilateral da parceria e o
  `tenant_id NULL` da telemetria (`external_requests`, `integration_alerts`).
- **A auditoria virou teste, não só documento.** `test_isolation_matrix.py` lê
  `pg_policies`/`pg_class` e compara com a lista de exceções documentada: tabela nova
  sem RLS forçado, RLS sem política, ou exceção não justificada em
  `docs/SEGURANCA-RLS.md` quebram a suíte. Um documento de segurança que ninguém relê
  envelhece em duas specs; este não tem como.
- **`aggregate_refresh_log` era a única tabela do banco sem teto de crescimento** —
  10 a 12 mil linhas por dia, criada sem expurgo na 078. Achado direto do item de
  retenção do checklist. Retenção de 90 dias, beat diário.
- **Refresh do BI não é o gargalo que a spec temia:** com 100.000 processos, 500.000
  tarefas e 200.000 lançamentos, o pior refresh leva 1,77 s (teto da spec: 60 s), e
  `CONCURRENTLY` não bloqueou leitura nenhuma. Refresh incremental foi avaliado e
  descartado com número na mão. O benchmark ficou como script versionado
  (`scripts/bench_aggregates.py`), não como teste — a suíte não paga 140 s de seed.
- **Um bug real caiu junto:** o sparkline da taxa de sucesso (075) usava o mês como
  chave de lista; mês repetido na série fazia o React descartar a barra. O aviso
  estava na saída da suíte desde a 075 e ninguém tinha lido. Chave por posição.
- **O wall-clock de 90 s não é atingível neste host** e a meta não foi renegociada
  para baixo: a suíte de backend sozinha leva ~165 s com `-n 2` aqui, contra os 45 s
  de orçamento do CLAUDE.md, e o número já vinha subindo (471 s medidos na 076 pelo
  runner concorrente). Nada nesta refatoração aumentou o custo — foram +6 testes, ~1 s.
  Reduzir de 165 s para 90 s exige atacar o custo POR TESTE (cada um sobe um app
  FastAPI e semeia tenant), não podar testes; é trabalho de uma spec própria, com
  medição, e não cabia dentro do escopo declarado desta.
