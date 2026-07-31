# 009 — Pipeline de testes e gate de 120 s

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +0 s (é a própria infra)
**Depende de:** 002, 006 · **Status:** ⬜ pendente

---

## 1. Objetivo

Tornar o orçamento de 2 minutos uma restrição **executável**. A partir daqui, nenhuma spec
fecha se estourar o teto — e o CI é quem decide, não o julgamento de quem implementou.

## 2. Escopo

- **Backend:** `pytest-xdist -n auto`; **template database** criada uma vez por sessão e clonada
  por worker; cada teste em transação com `ROLLBACK`; fixtures em escopo de sessão
- **Frontend:** Vitest com `pool: threads`, jsdom, MSW
- **E2E:** Playwright com `workers` = núcleos, `fullyParallel`, reuso de servidor, **contador de jornadas que falha acima de 25**
- `scripts/run-tests.sh`: dispara as três em paralelo, agrega saídas, mede **wall-clock** e sai com erro se > 120 s
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
2. Sai com código ≠ 0 se qualquer suíte falhar **ou** se o wall-clock passar de 120 s.
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
| meta | wall-clock simulado > 120 s falha | idem | ~0,3 s |
| meta | contador de jornadas e2e barra acima de 25 | `e2e/meta/journey-count.spec.ts` | ~0,2 s |
| meta | nenhum teste faz chamada de rede real | `tests/meta/test_no_network.py` | ~0,4 s |
| meta | template DB reutilizada entre workers | `tests/meta/test_db_isolation.py` | ~0,5 s |

**Total estimado:** ~1,9 s

## 9. Descobertas

Registrar aqui o wall-clock inicial. É a linha de base contra a qual as refatorações medem.

## 10. Definição de pronto

- [ ] `make test` roda as três em paralelo e reporta o wall-clock
- [ ] Gate de 120 s falhando de verdade quando estourado
- [ ] Contador de jornadas e2e ativo
- [ ] Guarda contra rede real ativa
- [ ] CI verde publicando o tempo
- [ ] `test-timing.json` commitado
- [ ] Commit `feat(009): pipeline de testes e gate de 120s`
