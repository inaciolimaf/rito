# 105 — Template database e ROLLBACK por teste

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** −80 s (alvo: wall-clock ≤ 200 s)
**Depende de:** 003, 009, 032 · **Status:** ⬜ pendente

---

## 1. Objetivo

Implementar a estratégia de isolamento que o `CLAUDE.md` §3 e a spec 009 declaram como oficial
do backend — «template database + `BEGIN`/`ROLLBACK` por teste» — e que **não existe no
código**. Depois desta spec, um teste não deixa linha no banco para o seguinte encontrar, o
`rito_test` não acumula estado entre execuções, e o custo por teste cai para o da transação,
não o da escrita.

> Refatoração: **nenhuma mudança de comportamento de produção**. Nenhum arquivo de `app/` é
> tocado. O que muda é a infraestrutura de teste — e os poucos testes que hoje dependem de
> estado vazado, que estão listados na regra 8.

## 2. O que existe hoje

Verificado no commit `44469bd`:

- `backend/tests/conftest.py` tem 74 linhas e **nenhuma** menção a transação, rollback ou
  template. As fixtures `admin_engine` e `app_session_factory` são de escopo de função e
  criam um engine novo por teste.
- `backend/tests/integration/conftest.py::make_user` **comita** tenant + usuário por teste,
  em duas transações separadas.
- `backend/tests/integration/test_sync_observability.py:9` diz, no próprio docstring:
  «sem transação global de rollback entre testes».
- `scripts/run-tests.sh` registra a consequência: «em agosto/2026 o `rito_test` tinha
  **9.317 tenants** e **1,16 milhão** de `task_types`», e faz um `TRUNCATE tenants CASCADE`
  uma vez por execução para conter o acúmulo — preservando à mão os catálogos globais, com
  uma consulta ao `information_schema` para descobrir quais são.

Ou seja: a limpeza existe, mas paga o custo errado. Cada um dos 1.496 testes escreve linhas
de verdade e as deixa lá até o fim da suíte. O custo médio por teste é de ~0,8 s de tempo de
worker — alto demais para «POST, GET, assert».

## 3. Escopo

**A. Template database.** Uma vez por sessão de teste: criar `rito_test_template`, aplicar
`alembic upgrade head`, semear os catálogos globais (`seed_global_catalogs`), e desconectar.
Cada worker do xdist cria o seu banco com `CREATE DATABASE rito_test_gwN TEMPLATE
rito_test_template`, que o Postgres resolve por cópia de arquivo — muito mais barato que
migrar 84 revisões por worker.

**B. Transação por teste.** Fixture `db_session` que abre uma conexão, inicia transação,
entrega uma `AsyncSession` ligada a essa conexão (`join_transaction_mode="create_savepoint"`)
e dá `ROLLBACK` no teardown. `session.commit()` dentro do teste vira `RELEASE SAVEPOINT`, não
commit de verdade.

**C. O `client` na mesma transação.** Sem isto, nada funciona: hoje o `client` sobe o
`lifespan` e o app abre sessão própria por requisição, que não enxergaria o dado escrito pela
fixture. O `client` passa a sobrescrever a dependency de sessão do FastAPI para devolver a
sessão da fixture.

**D. `make_user` deixa de commitar.** Passa a usar a sessão da fixture. Some a causa dos
9.317 tenants.

**E. Sair do `run-tests.sh`.** Com A–D no lugar, o bloco de `TRUNCATE`/preservação de
catálogos globais (≈60 linhas de Python embutido em shell) deixa de ter função e sai. O
`TRUNCATE integration_health` também.

## 4. Fora de escopo

- **Ordem de teste aleatória** (`pytest-randomly`). Vai revelar dependências entre testes que
  esta spec provavelmente já elimina, mas é gate próprio e entra depois — spec futura.
- Otimizar testes individuais lentos. Se algum aparecer no `--durations` depois desta spec,
  anote em `## 9. Descobertas`.
- O `client` continuar subindo o `lifespan` por teste. Medi: custa 10–40 ms, não é onde os
  segundos estão. Fica.
- Qualquer arquivo de `app/`.

## 5. Modelo de dados

Nenhuma tabela nova, nenhuma migration. O schema é o mesmo — muda quem o cria e quando.

## 6. Contratos de API / Front-end

Nada.

## 7. Regras de negócio

1. A template database é criada **uma vez por sessão** de pytest, não por worker e não por
   teste. Se ela já existe e está na head, é reaproveitada.
2. Cada worker do xdist tem banco próprio, derivado do template. Dois testes concorrentes
   nunca compartilham linha.
3. Todo teste roda dentro de uma transação que sofre `ROLLBACK` no teardown. Ao fim da suíte,
   os bancos de worker têm exatamente o conteúdo do template.
4. `make_user` não comita. Nenhuma fixture comita.
5. A sessão que o `client` usa nas requisições HTTP é **a mesma** da fixture do teste.
6. RLS continua valendo dentro da transação: a conexão usa a role `rito_app` (sem
   `BYPASSRLS`) e `set_tenant_context` segue sendo chamado. O `test_isolation_matrix.py`
   passa sem edição — é o teste que prova que esta spec não afrouxou o isolamento.
7. `admin_engine` continua existindo para DDL e sondagem (`tenant_probe_table`), fora da
   transação do teste, porque DDL não volta com rollback em toda situação. Uso restrito ao
   que já existe hoje.
8. **Os testes que precisam de commit real ganham marcador explícito**, não gambiarra. São os
   que exercitam justamente o comportamento transacional:
   - `tests/integration/test_resilience_chaos.py` — a sessão continua utilizável após rollback
   - `tests/integration/test_public_api.py:347` — «sessão própria, e não a da requisição que
     acabou de dar rollback»
   - `tests/integration/test_sync_observability.py` e `test_datajud_service.py` — o docstring
     do primeiro já declara a dependência
   Marcador `@pytest.mark.commits`, fixture alternativa com banco próprio, e um meta-teste que
   limita a lista a esses quatro arquivos — no mesmo espírito do teto de `slow` da 009.
9. Nenhum outro teste é editado. Se um terceiro arquivo quebrar, ele estava dependendo de
   estado vazado: registre em `## 9. Descobertas` **antes** de decidir se conserta o teste ou
   se ele vira `@pytest.mark.commits`.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | a template database está na head antes do primeiro teste | `tests/meta/test_db_isolation.py` (estende) | ~0,2 s |
| meta | um teste que insere não deixa a linha visível para o seguinte | `tests/meta/test_isolamento_transacional.py` | ~0,3 s |
| meta | `@pytest.mark.commits` aparece em no máximo 4 arquivos, todos justificados | `tests/meta/test_isolamento_transacional.py` | ~0,1 s |
| meta | nenhuma fixture de `tests/` chama `commit()` fora do marcador | `tests/meta/test_isolamento_transacional.py` | ~0,2 s |
| — | os 1.496 testes existentes passam **sem edição** | — | — |

**Total estimado:** +0,8 s de teste novo, contra o alvo de −80 s no total.
**Fixtures externas:** nenhuma.

### Medição de aceite

- Wall-clock de `make test` **≤ 200 s** (hoje 288 s). Se ficar entre 200 s e 288 s, a spec
  ainda fecha — mas o número medido vai para `test-timing.json` e para §9 com a explicação.
- Rodar `make test` **duas vezes seguidas** e conferir que `SELECT count(*) FROM tenants` no
  banco de teste devolve o mesmo número. Hoje ele cresce.

## 9. Descobertas

Preencher durante a implementação.

## 10. Definição de pronto

- [ ] Template database criada uma vez por sessão; um banco por worker
- [ ] Fixture transacional com `ROLLBACK` no teardown
- [ ] `client` na mesma sessão da fixture
- [ ] `make_user` sem commit
- [ ] Bloco de `TRUNCATE` removido do `scripts/run-tests.sh`
- [ ] `@pytest.mark.commits` em no máximo 4 arquivos, com meta-teste que trava o número
- [ ] `test_isolation_matrix.py` passa sem edição
- [ ] Nenhum arquivo de `app/` tocado
- [ ] `make test` verde; wall-clock medido e registrado em `test-timing.json` e em §9
- [ ] Duas execuções seguidas não acumulam tenants
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 105 em ✅
- [ ] Commit `refactor(105): template database e rollback por teste`

---

## Nota de execução

Esta é a spec mais arriscada da leva 104–116: mexe indiretamente em 1.496 testes. Se o ciclo
não fechar, o corte é por bloco, e a ordem já está desenhada — **B+C+D primeiro** (a transação
é o que devolve tempo e mata o acúmulo), **A depois** (o template acelera o boot, mas o banco
por worker já funciona com `alembic upgrade head`), **E por último** (remover o `TRUNCATE` só
é seguro quando A–D estiverem verdes por uma execução inteira).
