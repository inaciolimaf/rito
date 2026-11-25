# 127 — SQL em string trocada pelo query builder

**Fase:** 12 · **Tipo:** refatoração · **Orçamento:** +1 s
**Depende de:** 115, 118, 120 · **Status:** ✅ concluída

---

## 1. Objetivo

Tirar do backend a SQL escrita como string. **54 statements** em 13 arquivos passam a ser
montados por `select`/`insert`/`update`/`delete` do SQLAlchemy, e um gate impede a volta.

Refatoração: **não muda comportamento**. Nenhum teste anterior foi editado.

## 2. Por que, já que nenhuma delas era vulnerável

Esta é a primeira pergunta honesta a fazer, e a resposta não é segurança. Os parâmetros já
iam ligados (a 115 fechou a última interpolação de valor), e os poucos identificadores
interpolados vinham de allowlist. O custo era de manutenção, e tinha três formas:

1. **Coluna renomeada não quebra uma string.** Ela quebra em produção, na primeira vez que
   aquele caminho roda. `_SINAIS_SQL` citava sete colunas de quatro tabelas e nenhuma delas
   participava de checagem nenhuma.
2. **O `mypy` não enxerga nada dentro de aspas.** O backend paga 659 arquivos de checagem
   de tipo e 54 statements ficavam de fora — justamente os mais difíceis de testar.
3. **O `S608` do Bandit vira ruído.** Toda f-string parecida com SQL era acusada, e a
   resposta virava `# noqa` com justificativa. Cada uma correta; o conjunto ensinando que
   `S608` se silencia. Depois desta spec sobrou **um** `# noqa: S608` no backend — nenhum.

E uma quarta, que só apareceu na conversão: `partnership_email_has_account` recebe `citext`.
Com `text()` o parâmetro ia sem tipo e o Postgres resolvia por contexto; com o builder ele
vai tipado, e o teste apontou o descasamento na hora. Tipo explícito é o que a versão em
string comprava por acidente.

## 3. Escopo

**A. Infraestrutura (5 arquivos).** `rls.py` (`set_config` — a consulta mais executada do
sistema, uma por request, agora com plano em cache), `health.py` e `cli.py` (`SELECT 1`,
`INSERT` de tenant e de gestor, busca por slug), `migrations.py` (advisory lock,
`migration_locks`, `alembic_version` — as duas últimas ganharam `Table` em Core, porque não
têm nem devem ter modelo ORM) e `provisioning.py` (os sete `INSERT … SELECT unnest(…) ON
CONFLICT DO NOTHING`).

**B. Domínio (6 arquivos).** `partnerships/sharing.py` (as 11 funções `SECURITY DEFINER` da
079), `api_tokens/service.py` e `schedule/service.py` (as funções da 095 e da 037),
`ai/analytics.py` (o painel de sinais e as quatro consultas de insight),
`lawsuits/listing.py` e `lawsuits/stagnation_service.py` (`interval` e `text("false")`).

**C. Workers (2 arquivos).** `aggregates.py` (log, registry e alerta de refresh lento) e
`external_requests.py` (`interval` da purga).

**D. `app/core/sql.py`** — `days_interval(n)`, o `interval 'N days'` que o builder não tem
literal para escrever. Cinco usos; era a construção que mais tentava a f-string.

**E. Dois gates novos.** `tests/meta/test_sql_em_string.py` (a regra) e
`tests/integration/test_funcoes_do_banco.py` (as colunas declaradas contra o `pg_proc`).

## 4. Modelo de dados

Nenhuma migration. A spec não toca em schema.

## 5. Contratos de API

Inalterados. É esse o critério de aceite de uma refatoração.

## 6. Front-end

Nada.

## 7. Regras

1. `text(...)` em `app/` só é permitido como valor de `server_default=`/`server_onupdate=`
   (ali não é query, é o DEFAULT da coluna) ou nas exceções nomeadas do gate.
2. `exec_driver_sql` e `execute("<string>")` são proibidos sem exceção.
3. As exceções são **cinco**, e cada uma tem a justificativa escrita ao lado. São de três
   naturezas: DDL (`REFRESH MATERIALIZED VIEW CONCURRENTLY`, 2), comando de sessão
   (`SET LOCAL`, `SAVEPOINT`, `ROLLBACK TO SAVEPOINT`, 3) e a SQL que o **modelo** escreve
   no text-to-SQL da 089 — que é o produto daquela feature, não uma consulta do Rito.
4. Chamada de função do banco declara as colunas do `RETURNS TABLE` numa tupla nomeada, e
   a tupla é conferida contra o `pg_proc`.
5. Parâmetro de chamada de função vai **tipado**: o Postgres resolve sobrecarga pelo tipo
   do argumento, e não há coluna de destino para o asyncpg inferi-lo.
6. Fora de escopo, e vinculante: as migrations do Alembic e `rls.py::enable_rls_statements`
   continuam em string. São DDL, o builder não monta DDL, e migration commitada não se
   edita (§9 do `CLAUDE.md`).

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | `text()` fora de `server_default` reprova (provado mordendo) | `tests/meta/test_sql_em_string.py` | ~0,3 s |
| meta | exceção órfã reprova (provado mordendo) | `tests/meta/test_sql_em_string.py` | ~0,3 s |
| meta | exceção sem justificativa reprova | `tests/meta/test_sql_em_string.py` | ~0,1 s |
| integração | as 9 tuplas de coluna batem com o `pg_proc` | `tests/integration/test_funcoes_do_banco.py` | ~0,2 s |
| integração | as 9 chamadas montadas pelo builder são aceitas pelo banco | `tests/integration/test_funcoes_do_banco.py` | ~0,2 s |

Os **1.625 testes anteriores passam sem edição** — é o que prova que o comportamento não
mudou. Os dois gates do §11 do `CLAUDE.md` (wall-clock e orçamento de queries) continuam
verdes: o painel de sinais continua em 1 statement, com as quatro subqueries correlacionadas.

**Total estimado:** +1 s
**Fixtures externas:** nenhuma. Nada aqui toca a rede.

## 9. Descobertas

- **`make_interval` só aceita notação posicional pelo `func`.** `days => N` é sintaxe do
  Postgres, não do builder; `days_interval` esconde os três zeros de anos/meses/semanas.
- **`table_valued()` não emite a lista de colunas do alias.** Sem `render_derived()` o
  `.c.<nome>` existe do lado Python e o Postgres não conhece a coluna — o `unnest` do
  `provisioning.py` reprovou com `column anon_2.group_name does not exist`. Para as funções
  do banco é o contrário: **sem** `render_derived` o Postgres resolve pelos nomes do
  `RETURNS TABLE`, que é mais seguro do que uma lista posicional.
- **`insert().from_select()` sobre modelo ORM inclui os defaults Python** (`is_active`,
  `is_system`) na lista de colunas. Aqui todos coincidem com o `server_default`, então o
  resultado é o mesmo — mas o statement não é idêntico ao anterior, e vale saber.
- **`100.0` importava.** No insight de carteira, `100 * count(*) / total` seria divisão
  inteira e toda concentração abaixo de 100% viraria 0. O `cast(..., Numeric)` é o que
  preserva o que a string comprava de graça.
- **`proargmodes` é `"char"[]`** e o asyncpg devolve `[b'i', b't']`; comparar `bytes` com
  `str` não dá erro, dá lista vazia. O `::text[]` no `pg_proc` é obrigatório.
- **`_record_failure`/`_record_success` tipavam `log_id` como `int`** e o valor é `UUID`
  desde a 078 (a `Base` do Rito dá `id` UUID). A string escondia; o builder não deixou.
- **O número 127, e não 125.** O `DIVIDA-TECNICA.md` reserva a 125 (dívidas 25 e 26) e a
  126 (dívida 18). A "Nota de método: número de spec é recurso reservado" manda rodar
  `grep -n "Spec-alvo:.*\bNNN\b" docs/DIVIDA-TECNICA.md` ao ABRIR a spec; esta foi aberta
  como 125 e renumerada antes do commit. A terceira vez que o número escapa — e a primeira
  em que a nota da 124 evitou o retrabalho de fechar no número errado.
- **Dois vermelhos que já estavam lá.** Medidos no HEAD limpo, ANTES de qualquer
  alteração, e medidos de novo depois — os mesmos, nem um a mais:
  - `test_cartao_mostra_fatura_nao_saldo`, teste com data fixa (`2026-08-20`) que saiu da
    janela do ciclo do cartão. Vira a **dívida 41**;
  - **9 das 10 jornadas de e2e**, que não chegam a renderizar a tela de login neste host.
    Idênticas com e sem as mudanças (conferido com `git stash`). Não é desta spec, e
    diagnosticá-la é trabalho de outra: nada aqui toca o front nem o caminho de login.

  O `make test` fica, portanto, **vermelho por herança** — e a afirmação que esta spec faz
  não é "a suíte está verde", é "os 1.625 testes que passavam continuam passando, mais os
  13 que a spec trouxe". É o que dá para provar, e é o que importa numa refatoração.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras com teste
- [x] Nenhuma tabela nova (nada de RLS a testar)
- [x] `make test` sem NENHUMA regressão (os 2 vermelhos são anteriores, §9) e dentro do orçamento — 43 s de backend, 145 s de wall-clock contra o teto de 300 s
- [x] `make lint` verde
- [x] Sem `Any`, `# type: ignore` ou `# noqa` sem justificativa
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `refactor(127): SQL em string trocada pelo query builder`
