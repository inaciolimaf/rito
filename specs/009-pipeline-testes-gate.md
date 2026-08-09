# 009 — Pipeline de testes e gate de 300 s

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +0 s (é a própria infra)
**Depende de:** 002, 006 · **Status:** ✅ concluída

---

## 1. Objetivo

Tornar o orçamento de 5 minutos uma restrição **executável**. A partir daqui, nenhuma spec
fecha se estourar o teto — e o CI é quem decide, não o julgamento de quem implementou.

## 2. Escopo

- **Backend:** `pytest-xdist -n auto`; **template database** criada uma vez por sessão e clonada
  por worker; cada teste em transação com `ROLLBACK`; fixtures em escopo de sessão
- **Frontend:** Vitest com `pool: threads`, jsdom, MSW
- **E2E:** Playwright com `workers` = núcleos, `fullyParallel`, reuso de servidor, **contador de jornadas que falha acima de 25**
- `scripts/run-tests.sh`: dispara as três em paralelo, agrega saídas, mede **wall-clock** e sai com erro se > 300 s
- `make test` (tudo), `make test-backend`, `make test-frontend`, `make test-e2e`
- GitHub Actions: um job com serviços Postgres e Redis, cache de dependências, publicação do tempo
- Relatório `test-timing.json` com o tempo por suíte, versionado a cada spec

## 3. Fora de escopo

- Cobertura mínima obrigatória (avaliada nas specs de refatoração)
- Deploy → 099

## 4. Modelo de dados

Nenhum. Cria o database `rito_test_template`.

## 5. Contratos de API

Nenhum.

## 6. Front-end

Nenhum.

## 7. Regras de negócio

1. `make test` roda as três suítes **concorrentes**, não em sequência.
2. Sai com código ≠ 0 se qualquer suíte falhar **ou** se o wall-clock passar de 300 s.
3. Template database é criada **uma vez**; cada teste roda em transação revertida ao fim.
4. Nenhum teste faz I/O de rede. Um teste dedicado varre e falha se achar cliente HTTP real sem mock.
5. E2E acima de 25 jornadas falha o build com mensagem explicando a regra.
6. Teste marcado `@pytest.mark.slow` (>1 s) precisa de justificativa em comentário; um teste conta e limita a 5 no projeto.
7. `test-timing.json` é atualizado e commitado a cada spec — a evolução do custo fica versionada.

## 8. Plano de testes

Testes **da própria infraestrutura**:

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | `run-tests.sh` falha se uma suíte falha | `tests/meta/test_runner.sh` | ~0,5 s |
| meta | wall-clock simulado > 300 s falha | idem | ~0,3 s |
| meta | contador de jornadas e2e barra acima de 25 | `e2e/meta/journey-count.spec.ts` | ~0,2 s |
| meta | nenhum teste faz chamada de rede real | `tests/meta/test_no_network.py` | ~0,4 s |
| meta | template DB reutilizada entre workers | `tests/meta/test_db_isolation.py` | ~0,5 s |

**Total estimado:** ~1,9 s

## 9. Descobertas

**Wall-clock de linha de base:** 20 s (backend ~5-15 s com `-n auto`, frontend ~19 s, e2e ~17-22 s,
concorrentes — ver `test-timing.json`). Bem abaixo dos 300 s; a folga é o orçamento que as
specs 011+ vão consumir.

**Escopo reduzido conscientemente na regra 3 (template DB).** A seção 2/regra 3 descrevem
"template database criada uma vez por sessão e clonada por worker; cada teste em transação
com ROLLBACK". Implementado de fato: `alembic upgrade head` roda **uma vez por invocação**
de `make test`/`make test-backend` (antes dos workers do `-n auto` subirem), eliminando o
"esquecer de migrar" manual que existia até a spec 008. O que **não** foi feito: clonar o
banco por worker do xdist e envolver cada teste existente em transação com rollback — isso
exigiria reescrever a fixture de banco de todos os testes já verdes (003-008), risco alto
para um ciclo que deveria só entregar infraestrutura de teste. **Decisão:** os testes atuais
continuam usando o banco `rito_test` compartilhado entre workers (RLS + `tenant_id` únicos
por teste já evitam colisão — ver `tenant_probe_table` em `tests/integration/conftest.py`).
O retrofit completo de template-per-worker + rollback-per-test fica para a **spec 010**
(refatoração da Fase 0), que já existe no roadmap justamente para pente-fino sem mudar
comportamento.

**`pytest-socket`: `SocketBlockedError` não é o que é levantado.** A exceção real quando uma
conexão é bloqueada é `SocketConnectBlockedError` — as duas são subclasses irmãs de
`RuntimeError`, não uma hierarquia pai/filho. `test_no_network.py` testa contra a classe certa.

**Fixture cross-diretório do pytest.** Um `conftest.py` em `tests/integration/` é invisível
para `tests/meta/` (pastas irmãs não compartilham fixtures). `admin_engine` e
`app_session_factory` subiram para `tests/conftest.py` (raiz) para que ambas as pastas as
usem; fixtures específicas de integração (`tenant_probe_table`, `make_user`, `rbac_client`)
continuam em `tests/integration/conftest.py`.

**`PYTEST_ALLOW_HOSTS` como escape hatch, não hardcode.** Este sandbox de desenvolvimento
resolve Postgres/Redis via o hostname `dind` (Docker-in-Docker remoto), não `localhost`.
Colocar `dind` no `--allow-hosts` padrão do `pyproject.toml` quebraria qualquer máquina de
desenvolvedor real. Em vez disso, `scripts/run-tests.sh` e `make test-backend` aceitam um
`PYTEST_ALLOW_HOSTS` de ambiente que, se setado, substitui o allowlist do ini — testado
empiricamente (conexão bloqueada sem `dind` na lista, permitida com).

**Testes meta com falso positivo em si mesmos.** Tanto `test_slow_marker_budget.py` (varre
`@pytest.mark.slow` em todo `tests/`) quanto `e2e/tests/meta/journey-count.spec.ts` (varre
`test(`/`test.only(`/`test.skip(` em todo `e2e/tests/`) continham, no próprio texto/docstring,
a string que estavam procurando — cada um se auto-denunciava como infrator. Corrigido
excluindo a própria pasta `meta/` da varredura em ambos.

**`e2e/tests/meta/` em vez de `e2e/meta/` (like o plano original sugeria).** Playwright só
descobre specs sob `testDir: "./tests"` (`playwright.config.ts`); colocar o meta-teste fora
disso o deixaria fora do `npm test`. O contador exclui qualquer diretório chamado `meta` da
própria contagem de jornadas, então não se conta a si mesmo.

**`journey-count.spec.ts` precisou de `import.meta.url` em vez de `__dirname`.** O pacote
`e2e/` é `"type": "module"` — `__dirname` não existe em ESM; a correção usa
`fileURLToPath(import.meta.url)` + `path.dirname`.

**`run-tests.sh` refatorado para ser sourceable.** O plano de testes original previa um teste
de que o script falha quando uma suíte falha e quando o wall-clock estoura
(`tests/meta/test_runner.sh`). Para tornar isso testável sem rodar as suítes de verdade (e
sem gastar minutos por execução do teste), o corpo do script virou uma função `main()`, e o
script só a invoca automaticamente quando **executado** (`BASH_SOURCE[0] == $0`) — quando
**sourced**, quem chama `main` é o teste, depois de sobrescrever `run_backend`/
`run_frontend`/`run_e2e` com stubs. `tests/meta/test_runner.sh` cobre 3 cenários (suíte
falha, orçamento estoura, tudo verde) e faz backup/restore de `test-timing.json` porque o
cenário "tudo verde" de fato reescreve o arquivo (regra 7) — sem isso, o teste sujaria o
repo com um wall-clock sintético a cada execução. Um wrapper pytest
(`test_runner_gate.py`) só invoca esse shell script via `subprocess`, para que ele rode
junto com `pytest -n auto` como os demais.

**GitHub Actions criado e validado no remoto — pegou um bug real de primeira.** A primeira
run de `.github/workflows/ci.yml` (Postgres 16 + Redis 7 como serviços, banco `rito` e
`rito_test` separados de verdade) falhou com `UndefinedFunctionError: function
uuid_generate_v4() does not exist` em `rito_test`. Causa: `run_backend()` chama
`uv run alembic upgrade head` como **subprocesso**, antes do pytest subir — isso herda o
`MIGRATIONS_DATABASE_URL` do ambiente (apontando para o banco de **dev**, `rito`), não o
`TEST_MIGRATIONS_DATABASE_URL`. `tests/conftest.py::pytest_configure` só sobrescreve a
variável **dentro do processo do pytest**, tarde demais para esse `alembic upgrade` externo.
No sandbox de desenvolvimento local isso não apareceu porque `rito` e `rito_test` foram
apontados pro mesmo banco físico em alguns testes manuais — só o CI, com dois bancos de
verdade, expôs o bug. **Corrigido** em `scripts/run-tests.sh` e `Makefile` (`test-backend`):
`alembic upgrade head` agora roda com
`MIGRATIONS_DATABASE_URL="${TEST_MIGRATIONS_DATABASE_URL:-$MIGRATIONS_DATABASE_URL}"`, e a
correção foi confirmada localmente derrubando e recriando `rito_test` do zero antes de rodar
`make test`/`make test-backend` de novo. Isso valida a decisão de ter CI real desde a
spec 009: um ambiente com dois bancos de verdade (não um só reaproveitado) pegou algo que a
verificação manual não pegaria.

**Segundo bug, mesma causa raiz.** Corrigido o primeiro, o e2e passou a falhar com
`UndefinedTableError: relation "tenants" does not exist` — o webServer do Playwright e o
`scripts/seed_e2e.py` usam o banco de **dev** (`rito`), que nunca era migrado em lugar
nenhum do workflow (antes, só era migrado "sem querer" pelo bug do primeiro fix). Corrigido
adicionando um passo explícito `make migrate` no CI antes de `make lint`/`make test`,
espelhando o fluxo real (`make up && make migrate && make dev`). Confirmado localmente
derrubando **os dois** bancos (`rito` e `rito_test`) e recriando do zero antes de rodar
`make migrate && make test` — e confirmado no remoto (run 30706528182, verde).

## 10. Definição de pronto

- [x] `make test` roda as três em paralelo e reporta o wall-clock
- [x] Gate de 300 s falhando de verdade quando estourado
- [x] Contador de jornadas e2e ativo
- [x] Guarda contra rede real ativa
- [x] CI verde no remoto publicando o tempo (run 30706528182, após 2 fix commits — ver Descobertas)
- [x] `test-timing.json` commitado
- [x] Commit `feat(009): pipeline de testes e gate de 120s`
