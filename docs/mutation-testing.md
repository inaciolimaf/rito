# Teste de mutação

O teste de cobertura diz que uma linha **rodou**. O teste de mutação diz que um teste **falharia**
se a linha estivesse errada. O `mutmut` altera o código uma edição de cada vez (`>` vira `>=`,
`True` vira `False`, um argumento vira `None`), roda os testes que cobrem a função e conta como
**sobrevivente** cada alteração que nenhum teste notou.

Playbook: skill `mutation-testing` (project-standard). Ferramenta: `backend/tools/mutation.py`.
Configuração: `[tool.mutmut]` e `[tool.mutation]` em `backend/pyproject.toml`.

## Como rodar

Precisa do Postgres de pé (`make up`): o `tests/conftest.py` prepara o banco de teste em cada
execução do pytest, mesmo nos testes unitários.

```bash
make mutation       # só as funções alteradas desde origin/main (minutos, ou segundos sem alteração)
make mutation-all   # todos os módulos de [tool.mutation].paths (até 40 min; teto de 2400 s)
```

Direto na ferramenta, dentro de `backend/`:

```bash
uv run python -m tools.mutation --base HEAD~3            # funções alteradas desde outra ref
uv run python -m tools.mutation app/core/dates.py        # todas as funções de um arquivo
uv run python -m tools.mutation --all --survivors s.md   # + diff de cada sobrevivente
uv run python -m tools.mutation --check-speed            # só o orçamento de 5 s dos testes
```

A saída traz, por faixa, a porcentagem de mutantes mortos contra o mínimo, e a lista de
sobreviventes por função. Código de saída 1 quando alguma faixa está abaixo do mínimo ou quando
os testes da seleção passam de 5 s.

## Escopo

Só código puro entra em `[tool.mutation].paths`: sem sessão, sem HTTP, sem relógio. Hoje:

| Arquivo | Conteúdo |
|---|---|
| `app/core/dates.py` | dias úteis, ciclo de cartão, recorrências, datas de mês |
| `app/domain/publications/deadline.py` | cálculo do prazo de intimação |
| `app/domain/lawsuits/cnj.py` | número CNJ: parse, dígito verificador, inferência do tribunal |

A seleção de testes do mutmut (`pytest_add_cli_args_test_selection`) são só os arquivos unitários
que exercitam esses módulos. Não é `tests/unit/` inteiro: a pasta toda leva cerca de 12 s numa
só execução, e o orçamento é de 5 s.

## Faixas e mínimos

A primeira faixa cujo caminho casa com o arquivo vence.

| Faixa | Mínimo | Arquivos | Por quê |
|---|---|---|---|
| heurísticas | 65% | `app/domain/lawsuits/cnj.py` | inferência do tribunal é um palpite a partir dos dígitos |
| regras de domínio | 80% | `app/*` (o restante) | prazo e dias úteis: erro aqui é prazo perdido |

Nunca 100%: parte dos mutantes é equivalente (a alteração não muda nada observável).

## Medições

Mesma base (`chore/project-standard`), mesmo Postgres local, 4 processos. Os números são da
base reaplicada (o `chore/project-standard` andou depois da primeira medição: 86% → 85%).

| Medição | Seleção de testes | Geral | Domínio (80%) | Heurísticas (65%) | Testes da seleção |
|---|---|---|---|---|---|
| Antes: 4 arquivos de teste | `business_days`, `publication_deadline`, `recurrence_dates`, `cnj` | 73% (330/449) | **71%** de 338, abaixo | 81% de 111 | 0,16 s |
| Depois: 7 arquivos de teste | + `test_dates`, `test_card_cycle`, `test_ai_analysis_parser` | **85%** (384/449) | **87%** de 338 | 79% de 111 | 1,19 s |

O ganho veio da seleção, não de teste novo: os mutantes de `app/core/dates.py` (ciclo de cartão,
mês seguinte, recorrências) não tinham nenhum teste selecionado que os executasse, e contavam como
sobreviventes do tipo `(no tests)`. Com a seleção ampliada, as duas faixas passaram do mínimo, e
**nenhum teste novo foi escrito**.

### Sobreviventes que ainda restam (depois)

Ainda são 65 sobreviventes, 52 deles `(no tests)`: nenhum teste da seleção executa a função. Os
maiores grupos:

- `app.core.dates.next_month_start` (17), `iter_occurrences` (11), `previous_month_start` (7),
  `last_weekday` e `preview_occurrences` (2 cada)
- `app.domain.lawsuits.cnj._militar_estadual` (12), `_eleitoral` (5): ramos da inferência de tribunal
  que nenhum teste pede

A faixa de domínio tem folga de 7 pontos; a de heurísticas, de 14. O próximo passo, se a seleção
crescer, é escrever os testes que faltam para esses ramos (`references/rewriting-tests.md` do
playbook: um teste por sobrevivente, com `(no tests)` primeiro).

## Regras de ferramenta

- Os testes da seleção rodam **duas vezes no mesmo processo** sem falhar (mutmut chama o pytest
  mais de uma vez): nenhum teste deixa estado global. Verificado antes da primeira medição.
- Logs e mensagens de erro não são mutados (`do_not_mutate_patterns`): `logger.` e
  `raise <X>Error(`.
- `alembic.ini` e `alembic/` são copiados para `mutants/` (`also_copy`): o `conftest.py` migra o
  banco-modelo a partir deles.
- `mutants/` e `mutants-survivors.md` estão no `.gitignore`.

## CI (pendente de merge)

Não está no CI ainda. O job abaixo é o que se quer adicionar em `.github/workflows/ci.yml` depois
que o outro agente reestruturar o arquivo. Precisa de um serviço Postgres, porque o `conftest.py`
prepara o banco em cada execução. Fica fora do gate de 180 s do `test-speed`.

```yaml
  mutation:
    name: mutation (changed functions)
    runs-on: ubuntu-latest
    timeout-minutes: 5
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: rito
          POSTGRES_PASSWORD: rito
          POSTGRES_DB: rito
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U rito" --health-interval 5s --health-retries 10
    env:
      TEST_DATABASE_URL: postgresql+asyncpg://rito_app:rito_app@localhost:5432/rito_test_mut
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0 # a base precisa estar no clone
      - uses: astral-sh/setup-uv@v5
        with:
          prune-cache: false
      - run: uv sync --frozen
      - name: mutmut nas funções alteradas (make mutation)
        env:
          # pull request: desde a branch base; push na main: desde o tip anterior.
          BASE: ${{ github.event_name == 'pull_request' && format('origin/{0}', github.base_ref) || github.event.before }}
        run: |
          rc=0; timeout 270 uv run python -m tools.mutation --base "$BASE" || rc=$?
          if [ "$rc" -eq 124 ]; then echo "::warning::mutation testing hit 270 s; run make mutation locally"; exit 0; fi
          exit "$rc"
```

Pendências ao integrar: o `rito_app`/`rito_test_mut` precisa existir no serviço (o template de
banco é criado pelo `conftest.py` a partir de `MIGRATIONS_DATABASE_URL`; confirmar as credenciais
do job com o `ci.yml` da reestruturação); e o `make mutation` do CI deve usar o mesmo `BASE`.
