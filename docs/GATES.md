# Registro de gates do Rito

> Entregue pela **spec 120**. Um gate que ninguém sabe que existe é um gate que ninguém
> defende quando ele atrapalha.

Depois de vinte specs de qualidade, responder «quantos gates o Rito tem» exigia ler o
`pyproject.toml`, o `vite.config.ts`, o `eslint.config.js`, o `.jscpd.json`, o `ci.yml` e
dezoito arquivos de meta-teste. Este arquivo é a lista, e o
`tests/meta/test_registro_de_gates.py` impede que ela envelheça em silêncio.

## Como ler

**Programático** = a máquina decide sozinha se passa. **Proxy** = a máquina mede algo
*correlacionado* com o que se quer, e verde não é evidência — cobertura mede linha
executada, não propriedade verificada.

**Onde roda:** `make lint` e `make test` rodam na máquina de quem desenvolve e no CI; os
demais só no CI, porque custam minutos que não cabem nos 300 s do §3.

**Todo teto só desce.** Subir qualquer número desta página exige spec própria — é o que
separa «o código melhorou» de «alguém ajustou a régua».

---

## 1. Ruff — 20 famílias de regra (`make lint`, programático)

Configuração: `backend/pyproject.toml`, `[tool.ruff.lint] select`.

| Regra | O que reprova | Spec |
|---|---|---|
| `E` | erros de estilo do pycodestyle (inclui linha acima de 100 colunas) | 001 |
| `F` | erros do pyflakes: nome indefinido, import não usado | 001 |
| `I` | ordem dos imports (isort) | 001 |
| `UP` | sintaxe velha que a versão mínima de Python já não exige | 001 |
| `B` | armadilhas do bugbear (`B008` liberado: é o idioma do `Depends()`) | 001 |
| `SIM` | condicional que dá para escrever mais simples | 001 |
| `RET` | `return` redundante, `else` depois de `return` | 107 |
| `PTH` | `os.path` onde `pathlib` serve | 107 |
| `ERA` | código comentado (exceção: migrations commitadas) | 107 |
| `TID` | import relativo que atravessa pacote | 107 |
| `ICN` | apelido de import fora da convenção | 107 |
| `ASYNC` | I/O bloqueante dentro de corrotina | 108 |
| `DTZ` | `datetime` sem fuso — inclui `date.today()` | 114 |
| `C90` | complexidade ciclomática (ver tetos) | 106 |
| `PLR0911` | pontos de saída demais | 112 |
| `PLR0912` | ramos demais | 111 |
| `PLR0913` | argumentos demais | 116 |
| `PLR0915` | statements demais | 109 |
| `RUF100` | `# noqa` que não silencia nada | 113 |
| `S` | bandit: SQL por string, segredo literal, `assert` em produção, subprocess | 115 |

### Tetos numéricos

| Teto | Valor | Entrou como | Spec |
|---|---|---|---|
| `max-complexity` (C901) | **6** | 10 → 8 → 6, em três degraus | 106 |
| `max-branches` (PLR0912) | **8** | 8 (padrão da regra é 12; apertado por medição) | 111 |
| `max-returns` (PLR0911) | **6** | 6 (padrão da regra) | 112 |
| `max-statements` (PLR0915) | **50** | 50 (padrão da regra) | 109 |
| `max-args` (PLR0913) | **8** | 8 (padrão é 5; 8 é o joelho da curva medida) | 116 |

O teto de **linhas por função** não está aqui porque o Ruff não tem essa regra — `PLR0915` conta statements, que é outra métrica. Ele é meta-teste; ver a seção 5.

### Tetos de silenciamento

| Marcador | Teto | Hoje | Travado por |
|---|---|---|---|
| `# noqa: C901` | 3 | **0** | `test_final_audit.py` |
| `# noqa: PLR0913` | 2 | **2** | `test_final_audit.py` |
| `# noqa: S*` | 6 | **6** | `test_final_audit.py` |

Todo `# noqa` do projeto exige justificativa em prosa na linha acima — também travado pelo
`test_final_audit.py`.

### Exceções por arquivo (`per-file-ignores`)

| Arquivo | Regras | Por quê |
|---|---|---|
| `alembic/versions/*.py` | `ERA001`, `S608` | CLAUDE.md §9: migration commitada não se edita |
| `tests/**/*.py` | `S101`, `S105`, `S106`, `S107`, `S603`, `S607`, `S608` | `assert` é a interface do pytest; senha de teste é literal por desenho |
| `scripts/*.py` | `S101`, `S105`, `S608` | idem |

---

## 2. Tipos e formato (`make lint`, programático)

| Gate | O que reprova | Onde |
|---|---|---|
| `mypy --strict` | tipo frouxo em `app/`, `tests/` e `scripts/` | `backend/pyproject.toml` |
| `black --check` | formatação divergente no Python | `backend/pyproject.toml` |
| `tsc --noEmit` | erro de tipo no TypeScript (`strict`) | `frontend/tsconfig.json` |
| `prettier --check` | formatação divergente no front | `frontend/` |
| ESLint `react-hooks` | dependência faltando em hook, hook condicional | `frontend/eslint.config.js` |
| ESLint `react-refresh` | export que quebra o fast refresh (aviso) | `frontend/eslint.config.js` |
| ESLint `rito/no-literal-tailwind-color` | cor literal do Tailwind fora do token de tema | `frontend/eslint-rules/` |

---

## 3. Orçamento de tempo (`make test`, programático)

| Gate | Valor | Onde |
|---|---|---|
| Wall-clock das três suítes | **300 s** | `scripts/run-tests.sh` (CLAUDE.md §3) |
| Jornadas e2e no projeto | **25** | `e2e/tests/meta/journey-count.spec.ts` |
| Testes marcados `slow` | teto próprio | `tests/meta/test_slow_marker_budget.py` |
| Arquivos com `@pytest.mark.commits` | **19** arquivos / **69** testes | `tests/meta/test_isolamento_transacional.py` |

Desde a spec 110 a execução também registra **tempo de CPU e carga**, que não são gate: são
o que distingue «o projeto ficou lento» de «a máquina estava disputada» quando o wall-clock
estoura.

---

## 4. Desempenho (`make test`, programático)

| Gate | Valor | Onde |
|---|---|---|
| Queries por endpoint | listagem 3, detalhe 5, timeline 3, busca global 4 | `tests/integration/test_query_budget.py` |
| Invariantes de índice e plano | sem Seq Scan onde há índice esperado | `tests/meta/test_performance_invariants.py` |
| Import de `app.main` | abaixo de 9 s | `tests/meta/test_imports_pesados.py` |

---

## 5. Arquitetura (`make test`, programático)

| Gate | O que reprova | Onde | Spec |
|---|---|---|---|
| Camadas | `select()` em router, router importando repositório, service importando integração concreta | `test_camadas.py` | 118 |
| Registro do app | ordem dos middlewares, ordem de rotas ambíguas, router importado e não registrado, rota fora de `/api/v1` sem exceção | `test_app_registry.py` | 109 |
| Corpo de worker fino | função de `app/workers/` acima do baseline por arquivo | `test_workers_finos.py` | 117 |
| Imports pesados | biblioteca pesada no topo de módulo | `test_imports_pesados.py` | 104 |
| Isolamento transacional | teste que comita sem marcador; engine próprio fora do conftest | `test_isolamento_transacional.py` | 105 |
| Isolamento de Redis | workers do xdist compartilhando banco | `test_isolamento_transacional.py` | 110 |
| Sem RAG | vector store, embedding, pgvector | `test_no_rag.py` | 081 |
| Sem rede | teste tocando a rede (`--disable-socket`) | `test_no_network.py` | 009 |
| Contrato da API pública | as 22 rotas da v1, escopos e autenticação | `test_public_api_contract.py` | 095 |
| Guardrails de IA | prompt sem as regras obrigatórias | `test_ai_guardrails.py` | 084 |
| Espelho de enum | enum do Python divergindo do tipo do Postgres | `test_enum_mirror.py` | 054 |
| Registry de agregados | view materializada sem entrada no registry | `test_aggregate_registry.py` | 097 |
| Chave do DataJud | chave real vazando para o repositório | `test_datajud_key.py` | 040 |
| Isolamento de banco | teste apontando para banco que não é o de teste | `test_db_isolation.py` | 006 |
| Imagem de produção | não-root, multi-stage, sem toolchain, healthcheck | `test_deploy_image.py` | 099 |
| Gate do runner | `run-tests.sh` falha quando uma suíte falha ou o orçamento estoura | `test_runner_gate.py` | 009 |
| Auditoria final | `type: ignore` e `# noqa` sem justificativa, TODO órfão, `as any`, PII em fixture, spec × ROADMAP, dívida com alvo no futuro | `test_final_audit.py` | 100 |
| Tamanho de função | função de `app/` acima de **30** linhas LÍQUIDAS de corpo (docstring, decorador e assinatura fora); teto de 5 exceções versionadas, 2 em uso | `test_tamanho_de_funcao.py` | 121, apertado pela 122 e pela 123 |
| Idioma dos identificadores | função ou classe de `app/` com nome em português (§9) | `test_nomes_em_ingles.py` | 124 |
| Registro de gates | este arquivo listando todo gate que existe | `test_registro_de_gates.py` | 120 |

---

## 6. Fora do `make test` — só no CI

| Gate | Valor | Tipo |
|---|---|---|
| Cobertura do backend | piso **91%** de statements em `app/` sem `app/workers/` | **proxy** |
| Cobertura do frontend | piso **53%** de statements e linhas | **proxy** |
| Duplicação (jscpd) | Python ≤ **0,75%**, TSX ≤ **1,3%** | **proxy** |
| Tamanho do bundle | inicial abaixo de **300 KB** gzip, com chunks obrigatórios separados | programático |
| Auditoria de dependências | `pip-audit` e `npm audit` | programático |
| Imagem de produção | constrói e sobe | programático |

Os três **proxy** medem correlação, não a propriedade: cobertura alta com asserção frouxa
passa, e duplicação baixa com nomes diferentes passa. A revisão humana deles é item de toda
spec de refatoração da faixa (`§4` da 120).

---

## 7. Onde cada número vive

Fonte única de verdade de cada teto, para não haver dois lugares dizendo coisas diferentes:

- tetos do Ruff, `mypy`, `black`, cobertura do backend → `backend/pyproject.toml`
- cobertura do frontend → `frontend/vite.config.ts`
- duplicação → `.jscpd.json` (raiz)
- bundle → `frontend/scripts/check-bundle.mjs`
- wall-clock → `scripts/run-tests.sh`
- tetos de silenciamento e de marcadores → os próprios meta-testes
- **registro histórico** (não é gate): `coverage.json` e `test-timing.json`
