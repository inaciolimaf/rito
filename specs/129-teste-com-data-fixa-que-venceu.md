# 129 — Teste com data fixa que venceu

**Fase:** 12 · **Tipo:** correção · **Orçamento:** +0,1 s
**Depende de:** 055, 059, 101, 114 · **Status:** ✅ concluída

---

## 1. Objetivo

Fechar a **dívida 41**: `test_cartao_mostra_fatura_nao_saldo` volta a ser verde e passa a
ser verde em qualquer dia do calendário. A data do lançamento deixa de ser um literal e
passa a sair do relógio do escritório, pela mesma função de janela que a aplicação usa.

O comportamento de produção **não muda** — o cálculo de fatura estava certo desde a 055.
O que muda é o teste, que afirmava a coisa certa por um motivo que só valia em agosto.

## 2. O defeito, e por que ele é pior que um teste quebrado

O teste criava um cartão de ciclo dia 5 e lançava uma despesa com
`due_date="2026-08-20"`, esperando `balance == 220`. `card_invoice`
(`app/domain/financial/dashboard.py`) soma as despesas cuja `due_date` cai na janela de
`card_cycle_range(cycle_day, today)` — e `today` vem do `Clock` do tenant (spec 114), não
de uma constante. Enquanto "hoje" esteve entre 05/08 e 04/09/2026 a despesa caía dentro da
janela e o teste passava. Em 05/09/2026 a janela virou, a despesa saiu, `balance` virou
`0.0` e o teste ficou **permanentemente** vermelho.

Três coisas fazem disso pior do que um vermelho comum:

1. **Ele não denuncia regressão nenhuma.** Nada em `app/` mudou. Quem abrir a falha vai
   investigar `card_cycle_range` — que tem seis casos de borda cobertos em
   `tests/unit/test_card_cycle.py` e está correto. O teste manda a pessoa para o lugar
   errado, e o custo é o tempo dela, não o do CI.
2. **Ele passou por sorte antes de falhar por calendário.** Durante um mês inteiro o
   verde não significava nada: se alguém tivesse removido o filtro de janela do
   `card_invoice`, o teste continuaria verde. Um teste que só é vermelho fora de época é
   um teste que também é verde de graça dentro dela.
3. **É a terceira da mesma família.** A dívida 30 (suíte vermelha depois das 21h de
   Brasília), a 31 (`func.now()` constante dentro da transação) e a 32 (timestamp UTC
   comparado com data de escritório) são todas a mesma pergunta: **o teste depende de
   quando roda?**. A 114 respondeu isso para o fuso; esta responde para o calendário.

A 127 mediu o vermelho no HEAD limpo e registrou a dívida em vez de consertar de passagem:
mudar a asserção de uma fatura **muda o que o teste afirma**, e refatoração não faz isso.
É por isso que a correção vem numa spec própria, e não numa de refatoração.

## 3. Escopo

**A. `_vencimento_na_fatura(cycle_day, today)`** em `tests/integration/test_financial_dashboard.py`
— devolve um vencimento que cai na fatura corrente, calculado com a **mesma**
`card_cycle_range` da aplicação, alimentada pelo **mesmo** "hoje" (`tests.clock.hoje()`,
spec 114). Devolve o meio da janela, não uma ponta: quem afirma que as bordas do ciclo
entram é o `tests/unit/test_card_cycle.py`, e misturar as duas afirmações no mesmo teste
faria uma mudança de inclusividade quebrar dois lugares dizendo coisas diferentes.

**B. `_vencimento_fora_da_fatura(cycle_day, today)`** — o primeiro dia depois da janela.
É o contra-exemplo que faltava: com só um lançamento dentro, uma `card_invoice` que
somasse *tudo* do cartão ignorando o ciclo passaria igual. O teste agora lança 220 dentro
e 900 fora, e continua exigindo 220.

**C. Dois testes de posicionamento** que provam a não-recorrência sem congelar relógio
nenhum (§8).

## 4. Modelo de dados

Nenhuma migration. A spec não toca em schema, nem em `app/`.

## 5. Contratos de API

Inalterados. `GET /api/v1/bank-accounts/balances` responde exatamente o mesmo — é o
critério de aceite: só o teste mudou.

## 6. Front-end

Nada.

## 7. Regras

1. Data de teste que participa de comparação com "hoje" **é derivada do relógio**, nunca
   escrita à mão. O relógio é o `tests.clock.hoje()` — o do escritório, não o do processo.
2. A janela usada pelo teste é a **mesma função** que a aplicação usa
   (`app.core.dates.card_cycle_range`). Recalcular a janela à mão no teste seria escrever
   uma segunda implementação da regra 5 da 055 e testar uma contra a outra.
3. Literal de data continua **certo** para o caso oposto: âncora de subtração, valor de
   campo que ninguém compara com o presente, mês explícito na query
   (`?month=2026-08`). O `tests/clock.py` já diz isso no seu próprio docstring, e esta
   spec não o alarga: `hoje()` é para quando o teste afirma algo **sobre o presente**.
4. O teste declara o ciclo uma vez (`CICLO_DO_CARTAO = 5`) e as duas datas saem dele — se
   o ciclo do cartão da fixture mudar, as datas acompanham.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | vencimento calculado cai na fatura em 5 datas de borda × 2 `cycle_day` | `tests/integration/test_financial_dashboard.py` | ~0,01 s |
| unit | o mesmo invariante varrido em 366 dias × 31 fechamentos | `tests/integration/test_financial_dashboard.py` | ~0,07 s |
| integração | cartão mostra fatura do ciclo, e o lançamento da PRÓXIMA fatura não entra | `tests/integration/test_financial_dashboard.py` | ~0,4 s |

**O projeto não tem `freezegun`, e não passa a ter por causa disto.** A coisa que precisa
ser determinística é a **função de posicionamento**, não o processo inteiro — então o
relógio entra por parâmetro. As cinco bordas são dia 1 (antes do fechamento, a fatura
corrente abriu no mês anterior), véspera do fechamento, o próprio dia do fechamento, fim
de fevereiro (onde o clamp do dia 31 age) e 31 de dezembro (a janela atravessa o ano); os
dois `cycle_day` são 5 e 31. A varredura dia a dia existe porque cinco bordas escolhidas a
dedo provam que quem escreveu pensou nelas, e só a varredura prova que não sobrou nenhuma.

Fora da suíte, e como conferência do conjunto, o teste de integração inteiro foi rodado com
app e teste congelados no **mesmo** dia falso (um plugin descartável que troca
`Clock.today`/`Clock.now` e `tests.clock.hoje` juntos — congelar um lado só seria desonesto)
em 2026-09-01, 2026-09-05, 2026-01-31, 2027-02-28 e 2026-12-31: passou nas cinco. O plugin
não entra no repositório; ele responde uma pergunta de uma vez, e quem responde
continuamente é a varredura de 366 dias, que não precisa de plugin nenhum.

**Total estimado:** +0,1 s (medido: 4,53 s no arquivo, contra 4,87 s antes — o custo novo
some no ruído porque as duas despesas do teste substituíram uma só).
**Fixtures externas:** nenhuma. Nada aqui toca a rede.

## 9. Descobertas

### A varredura: 37 arquivos com literal de data, nenhuma segunda bomba

A dívida 41 pedia explicitamente para varrer o resto da suíte pela mesma assinatura —
literal de data no corpo de um teste que acaba comparado com "hoje". O método foi partir
de `app/`, não de `tests/`: primeiro levantar **quais caminhos de produção leem o
relógio** (`clock.today()`, `func.now()`, `CURRENT_DATE`) e só depois perguntar quais
testes passam por eles. São eles a fatura de cartão e os atrasados (`financial/`),
aniversariantes e estatísticas de contato (`customers/`), taskscore, BI de vintage e
agilidade, agenda, publicações, dunning, workflows/automações, estagnação de processo e a
expiração de token/convite.

**Resultado: nenhuma outra bomba ativa.** Os 37 arquivos de teste com literal de data
caem em dois padrões seguros, e vale escrever a diferença porque ela é o critério, não a
lista:

- **Literal que não é comparado com o presente.** Mês explícito na query
  (`?month=2026-08`, `from`/`to`), valor de campo que nenhuma asserção confronta com hoje
  (`due_date` nos testes de permissão de `test_ai_actions.py`), "agora" passado como
  **parâmetro** para uma função pura (`test_djen_client.py`,
  `test_datajud_movement_sync.py`, `test_resilience_chaos.py`) e a suíte unitária inteira
  (`test_card_cycle.py`, `test_business_days.py`, `test_recurrence_dates.py`,
  `test_publication_deadline.py`, …), que por construção recebe o dia por argumento.
- **Literal no passado sob condição monotônica.** É o caso de
  `test_atrasados_excluem_interno`, neste mesmo arquivo: `due_date="2026-08-01"` com
  `overdue == 150`. `overdue_total` (`financial/dashboard.py`) é `due_date < today AND
  payment_date IS NULL`, **independente do mês e do regime da consulta** — uma vez
  atrasado, atrasado para sempre. É o oposto exato da fatura do cartão, que é **janela
  móvel**: entra e sai.

**A distinção que a dívida 41 ensina não é "literal é ruim".** É *janela móvel × condição
monotônica*. Um literal comparado com uma condição que só liga (atrasado, vencido,
encerrado) é estável depois que a data passa; um literal comparado com uma janela que
anda (fatura do ciclo, "últimos 30 dias", aniversariantes do mês) é uma bomba com data
marcada. O `tests/clock.py` já dizia metade disso — «`hoje()` é para quando o teste afirma
algo sobre o presente» —; a outra metade é que *janela móvel é sempre uma afirmação sobre
o presente*, mesmo quando o teste parece só estar escolhendo uma data.

### Um detalhe que quase passou: a bomba que o tempo desarmou

`test_atrasados_excluem_interno` **teria falhado** se rodado antes de 01/08/2026 — o
`overdue` daria 0, porque a data ainda não tinha vencido. Ele é seguro hoje por sorte
cronológica, não por construção. Não foi mexido porque está fora do escopo desta spec
(o defeito é sobre a fatura) e porque o conserto seria trocar uma âncora estável por outra
sem ganho de garantia. Mas o registro fica: a mesma família tem uma segunda direção, a do
literal **no futuro**, e a varredura achou quatro deles — `2030-01-01`/`2030-12-31`
(`test_bi_time_fees.py`, recorte vazio por construção: os dados semeados são de 2024),
`2026-09-10` (duas vezes em `test_ai_actions.py`, só valor de payload) e `2026-09-14`
(`test_post_recurrence.py`, preview ancorado num `_ANCHOR` literal). Nenhum é comparado
com hoje. Se algum dia forem, o defeito aparece em 2030 e ninguém vai lembrar disto.

### O que ficou de fora, e por quê

- **Gate automatizado contra a assinatura.** Um meta-teste que reprovasse literal de data
  em teste que também chama um endpoint dependente de relógio seria o fecho natural — é o
  que a 124 fez com os nomes em português e a 127 com a SQL em string. Não entra aqui por
  duas razões: `tests/meta/` tem gate próprio (`test_registro_de_gates.py`) que exige
  linha em `docs/GATES.md`, e a regra é **difícil de escrever sem falso positivo** — o
  mesmo literal é certo ou errado dependendo de a condição do outro lado ser janela ou
  monotônica, e isso o AST não vê. Fica proposto, não prometido.
- **`freezegun`/`time-machine` como dependência.** Rejeitado no §8: o determinismo
  necessário é o da função de posicionamento, e ele se compra com um parâmetro.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] `test_cartao_mostra_fatura_nao_saldo` verde
- [x] Não-recorrência provada em datas de borda e por varredura anual
- [x] Nenhuma linha de `app/` alterada — contrato inalterado
- [x] `black`, `ruff` e `mypy` verdes no arquivo tocado
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `fix(129): teste com data fixa que venceu`
