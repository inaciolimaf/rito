# 114 — DTZ: «hoje» é o hoje de quem, exatamente?

**Fase:** 11 · **Tipo:** correção · **Orçamento:** +2 s
**Depende de:** 011, 037 · **Status:** ⬜ pendente

---

## 1. Objetivo

Ligar a família `DTZ` do Ruff e trocar as 90 chamadas a `date.today()` por um relógio que
conhece o fuso do escritório. Esta é a única spec da leva que **muda comportamento de
propósito** — e muda porque o comportamento atual está errado: `date.today()` lê o relógio do
processo, não o do tenant, num sistema cujo produto é prazo processual.

> Não é refatoração. Testes que hoje afirmam o comportamento dependente do servidor são
> reescritos, e a lista deles vai em `## 8. Descobertas`.

## 2. Por que isto importa aqui mais que em outro projeto

A spec 011 guarda `timezone` por conta (`app/domain/account/models.py:45`, oito opções BR/PT,
default `America/Sao_Paulo`). O sistema já sabe que o fuso é um dado do escritório. Mas só
**dois** módulos usam esse dado hoje — `schedule/router.py:160` e
`reports/access_service.py:71` — e cada um resolve à sua maneira, com o fallback literal
`"America/Sao_Paulo"` escrito à mão no primeiro.

Nos outros 34 arquivos, «hoje» é o dia do servidor. As concentrações dizem tudo:

| Arquivo | Ocorrências | O que «hoje» decide ali |
|---|---|---|
| `domain/taskscore/router.py` | 6 | pontuação do período |
| `domain/financial/dashboard.py` | 3 | vencido vs. a vencer |
| `domain/dunning/router.py` | 3 | régua de cobrança |
| `domain/customers/repository.py` | 3 | filtros por período |
| `domain/bi/router.py` | 3 | safras e indicadores |
| `domain/workflows/router.py` | 2 | prazo de etapa |
| `domain/schedule/router.py` | 2 | agenda do dia |
| + 27 arquivos | 32 | — |

Um escritório em Rio Branco (UTC−5) vendo o dia de um servidor em UTC recebe o dia seguinte
por cinco horas, toda noite. Uma parcela que vence hoje aparece como vencida; uma tarefa de
amanhã entra na pontuação de hoje. Nada disso levanta exceção.

## 3. Escopo

**A. Um relógio, em `app/core/clock.py`.** A regra dos 3 usos já foi ultrapassada — o padrão
existe em dois lugares com duas formas. O helper resolve `today()` e `now()` a partir do
`timezone` da conta do tenant corrente, com `DEFAULT_TIMEZONE` como único fallback (nunca uma
string literal repetida).

**B. Injeção por `Depends`.** Rotas e services recebem o relógio pela dependency, não o
importam — `CLAUDE.md` §5, DIP. Isso também é o que torna o teste determinístico: injetar um
relógio fixo é mais honesto que congelar o tempo do processo.

**C. As 90 chamadas.** 54 em `app/`, 36 em `tests/`. As de teste na maioria viram relógio
injetado; as que só precisam de uma data qualquer viram literal.

**D. `DTZ` no `select` do Ruff**, sem exceção por arquivo.

## 4. Fora de escopo

- `datetime.now()` sem `tz` — o `DTZ` pega (`DTZ005`), mas hoje há **zero** ocorrências, então
  não há trabalho, só o gate.
- Feriados e contagem de prazo processual em dias úteis. Isso é a spec 037 e continua como
  está; esta spec só corrige de qual dia a contagem parte.
- Timezone por **usuário**. O dado é da conta. Se um dia for do usuário, é outra spec.
- Migração de dado histórico. Nada gravado muda.

## 5. Modelo de dados

Nenhuma tabela nova, nenhuma migration. `accounts.timezone` já existe desde a 011.

## 6. Contratos de API

Nenhuma rota muda de forma. Algumas mudam de **resposta** — é o objetivo. As afetadas são as
que hoje devolvem contagem, saldo ou lista dependente de «hoje»: taskscore, dashboard
financeiro, dunning, BI, workflows, agenda. Datas continuam ISO 8601 na API e `DD/MM/AAAA` na
UI (`CLAUDE.md` §9).

## 7. Front-end

Nada. O frontend já recebe datas resolvidas pelo backend.

## 8. Regras de negócio

1. `DTZ` no `select` do Ruff. Nenhum `per-file-ignores`, nenhum `# noqa: DTZ011`.
2. Nenhuma chamada a `date.today()` ou `datetime.now()` sem fuso sobrevive em `app/`.
3. «Hoje» é sempre o hoje **da conta do tenant da requisição**. Nunca do servidor.
4. O fallback é `DEFAULT_TIMEZONE`, importado de `app/domain/account/models.py`. A string
   `"America/Sao_Paulo"` não aparece literal em lugar nenhum além dessa constante — inclusive
   sai de `schedule/router.py:160`.
5. O relógio chega por `Depends`. Nenhum service importa `date` para saber que dia é hoje.
6. Um tenant em `America/Rio_Branco` e um em `America/Sao_Paulo`, consultando o mesmo endpoint
   no mesmo instante, podem receber dias diferentes — e é isso que o teste da regra 3 prova.
7. `reports/access_service.py` e `schedule/router.py` passam a usar o helper. Duas
   implementações do mesmo conceito não sobrevivem a esta spec.

## 9. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | `today()` devolve o dia da conta, não o do processo | `tests/unit/test_clock.py` | ~0,1 s |
| unit | conta sem timezone cai em `DEFAULT_TIMEZONE` | `tests/unit/test_clock.py` | ~0,1 s |
| integração | às 02:00 UTC, tenant em `America/Rio_Branco` e tenant em `America/Sao_Paulo` recebem dias diferentes no mesmo endpoint | `tests/integration/test_clock_tenant.py` | ~0,6 s |
| integração | parcela que vence hoje no fuso da conta **não** aparece como vencida | `tests/integration/test_financial_dashboard.py` (estende) | ~0,5 s |
| meta | nenhuma chamada a `date.today()` em `app/` (AST, não regex) | `tests/meta/test_final_audit.py` (estende) | ~0,2 s |
| RLS | o relógio não vaza conta de outro tenant | `tests/integration/test_clock_tenant.py` | ~0,3 s |

**Total estimado:** +1,8 s
**Fixtures externas:** nenhuma. Nenhum teste chama relógio real do sistema para afirmar
resultado — o relógio é injetado.

## 10. Descobertas

**Recontagem (01/09/2026, HEAD `946ad91`):** 96 chamadas, não 90 — **56 em `app/`** (a spec
dizia 54) e **40 em `tests/`** (dizia 36). Todas `DTZ011`; `DTZ005` continua em zero.

**Existem DOIS `DEFAULT_TIMEZONE`.** A regra 4 assume um. Além de
`app/domain/account/models.py:13`, há uma cópia em `app/domain/schedule/service.py:20`, com
comentário próprio explicando o mesmo fallback. A regra 7 já mandava unificar as duas
implementações de fuso; o que ela não sabia é que a duplicação começa na constante. A cópia
do `schedule` sai e passa a importar de `account/models.py`.
O literal em `account/schemas.py:13` **fica**: é um dos 8 valores de `ALLOWED_TIMEZONES`,
o conjunto de opções válidas, não um fallback duplicado. Passa a ser escrito referenciando
`DEFAULT_TIMEZONE` para que a regra 4 valha ao pé da letra.

### O relógio não pode custar uma query — medido

A spec manda injetar o relógio por `Depends` (bloco B) e não diz de onde ele tira o fuso. O
caminho óbvio — repositório da conta, como `schedule/service.py:86` e
`reports/access_service.py:89` já fazem — **quebra o gate de orçamento de queries do
`CLAUDE.md` §11**. Contagem real de hoje, medida zerando os tetos de
`tests/integration/test_query_budget.py`:

| Endpoint | Queries | Teto | Folga |
|---|---|---|---|
| `/api/v1/customers/stats` | **5** | 5 | **zero** |
| `/api/v1/customers` | **3** | 3 | **zero** |
| `/api/v1/lawsuits` | 3 | 3 | zero |
| `/api/v1/transactions/stats` | 4 | 5 | 1 |
| `/api/v1/lawsuits/stats` | 4 | 5 | 1 |

`customers/repository.py` tem 3 `date.today()` e é justamente quem atende os dois endpoints
sem folga. Uma query a mais para descobrir o fuso reprova o gate.

**Descartados, e por quê:**

- *Cache em processo ou no Redis (`core/cache.py`).* Funciona em regime, mas o gate passaria
  porque a fixture do teste aquece o cache, não porque o custo sumiu — a primeira requisição
  depois de todo deploy pagaria 6 queries em `/customers/stats` e o gate nunca veria. Gate que
  só mede o caminho quente é gate que mente.
- *Resolver no preâmbulo de RLS*, que o orçamento explicitamente não conta. Seria esconder a
  query do gate em vez de não fazê-la. O preâmbulo é plumbing de sessão; `accounts` é tabela
  de domínio.
- *Subir o teto de `/customers/stats` para 6.* Afrouxa um gate do §11, e teto que sobe pede
  spec própria.

**Escolhido: o fuso vem junto do principal autenticado.** Toda requisição já carrega o
usuário do token — é a primeira das 3 queries de uma listagem. `accounts` tem uma linha por
tenant, então buscar o fuso ali é um `JOIN` na query que já existe, não uma query nova. A
contagem não muda em endpoint nenhum, não há cache, não há valor velho, e «hoje» passa a ser
uma propriedade do contexto autenticado — resolvida onde o contexto é construído.

Worker e task do Celery não têm requisição nem usuário; esses resolvem a conta explicitamente
e ficam fora do gate, que só mede rota HTTP.

**Obrigatório, ainda a preencher:** a lista dos testes existentes que precisaram ser
reescritos por dependerem do fuso do servidor.

## 11. Definição de pronto

- [ ] `app/core/clock.py` com `today()`/`now()` por tenant, injetado via `Depends`
- [ ] As 54 chamadas de `app/` e as 36 de `tests/` resolvidas
- [ ] `"America/Sao_Paulo"` literal só em `DEFAULT_TIMEZONE`
- [ ] `DTZ` no `select`, sem `per-file-ignores` e sem `noqa`
- [ ] Teste de dois tenants em fusos diferentes recebendo dias diferentes
- [ ] Meta-teste por AST impedindo a reincidência
- [ ] Testes reescritos listados em §10
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 114 em ✅
- [ ] Commit `fix(114): «hoje» passa a ser o hoje do escritório`
