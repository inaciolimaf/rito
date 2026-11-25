# Velocidade dos testes

Medições do playbook `test-speed` (`project-standard`). Cada número diz a máquina e a carga:
o host de desenvolvimento tem 12 núcleos e outros processos pesados rodando, então o
wall-clock oscila 2x entre execuções. Por isso as comparações são feitas **intercaladas** e
com o tempo de CPU (`user`) ao lado.

## Backend

Suíte: `backend/`, 1.970 testes, `pytest -q`. Ordem do playbook, com o que foi medido.

| Onde o tempo vai | Estado antes | Decisão | Medição |
|---|---|---|---|
| Hash de senha em produção | Testes já usam `ARGON2_TIME_COST=1`, `ARGON2_MEMORY_COST=8192` (`tests/conftest.py`), e `test_hashing.py` já prova o default de produção | nada a fazer | um hash no custo de teste leva ~3 ms; no custo de produção (t=3, 64 MiB) ~72 ms. 740 chamadas de `make_user` somam ~2 s num total de ~250 s de CPU: menos de 1 % |
| Um banco por worker do xdist | Já existe (spec 105): template migrado uma vez, `CREATE DATABASE ... TEMPLATE` por worker, `ROLLBACK` por teste; Redis também por worker (spec 110) | nada a fazer | — |
| Número de workers (`scripts/run-tests.sh`, `_cap`) | Teto 3, comentário diz que foi medido em 4 e 12 núcleos | teto subiu para 6, ver abaixo | ver tabela de workers |
| Cobertura com o rastreador padrão | `coverage` com `sys.settrace` | `COVERAGE_CORE=sysmon` no `make coverage` e no passo de cobertura do CI | ver tabela de cobertura |
| Testes lentos individuais | maior teste: 4,2 s (`test_djen_sync.py::test_paginacao_percorre_todas_as_paginas`); os 30 mais lentos somam pouco contra 250 s de CPU | nada a fazer agora; `--durations=15` entrou no `addopts` | — |
| Postgres em tmpfs | Não há compose de teste separado: os testes usam o Postgres do `docker-compose.yml` de desenvolvimento, que guarda dados de dev | **não aplicado** | não medido; um `tmpfs` no compose de dev mudaria dados de dev, então fica para um compose de teste ou para o serviço do CI, com medição própria |

### Workers (`pytest -n`)

Medido com `pytest -q -p no:cacheprovider`, mesma árvore, mesmo banco de teste por execução.

| Execução | Workers | Wall-clock | CPU user | Carga no início |
|---|---|---|---|---|
| 1 | 3 | 200 s no total (pytest 181,7 s) | — | 17 |
| 2 | 6 | 130,4 s | — | 16 |
| 3 | 12 (auto) | 137,4 s | — | 24 |
| 4 | 3 | 258,3 s | — | 38 |
| 5 (intercalada) | 3 | 105,2 s | 209 s | 19,5 |
| 6 (intercalada) | 6 | 62,7 s | 251 s | 7,9 |
| 7 (intercalada) | 3 | 101,5 s | 202 s | 8,0 |
| 8 (intercalada) | 6 | 62,9 s | 245 s | 5,3 |

Leitura: com a máquina menos carregada (execuções 5 a 8, medidas em par), 6 workers levaram o
backend de ~103 s para ~63 s, com ~20 % a mais de CPU. Com carga alta (execuções 1 a 4) os
números não são comparáveis entre si. Não medimos a suíte inteira com `make test`: o e2e usa
portas compartilhadas e não roda em paralelo com outros agentes. Por isso o ganho medido é do
backend isolado. Como o `_cap` já é `min(teto, núcleos - 1)`, o teto novo só muda o resultado em
máquinas com 7 núcleos ou mais: 2 núcleos continua com 1 worker, 4 com 3. O teto de 6 é
conservador para o `make test`, porque as outras suítes (vitest, playwright, vite) disputam os
mesmos núcleos durante a execução. O efeito no `make test` completo não foi medido: é o
primeiro número a conferir se o wall-clock do gate de 300 s voltar a oscilar.

### Cobertura (`--cov`, 6 workers)

| Rastreador | Wall-clock | CPU user | Execuções |
|---|---|---|---|
| `sys.settrace` (padrão) | 97,7 s; 103,6 s | 418 s; 432 s | 2 |
| `COVERAGE_CORE=sysmon` | 69,0 s; 68,5 s | 245 s; 256 s | 2 |

O piso de cobertura não muda: é a mesma medição, só com outro rastreador. Não comparamos
os percentuais dos dois rastreadores neste passo; a suíte de cobertura do CI continua
validando o piso.

### Não medido

- Frontend e e2e: fora do escopo desta fatia (o playbook de frontend e e2e é outro).
- Postgres em tmpfs: ver a tabela acima.
- `make test` completo com as três suítes concorrentes: exige o e2e, que não rodou aqui.
