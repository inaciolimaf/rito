# 113 — RUF100: noqa que não silencia nada

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 107, 108, 109, 111, 112 · **Status:** ✅ concluída

---

## 1. Objetivo

Ligar `RUF100` e apagar as 31 diretivas `# noqa` que não silenciam mais nada. Supressão morta
é pior que ruído: ela documenta um problema que não existe, e treina quem lê o código a
ignorar `noqa` — inclusive os que estão segurando algo de verdade.

> Refatoração: nenhuma mudança de comportamento. Só comentários saem.

## 2. Escopo

`pyproject.toml`: `select` ganha `RUF100`.

Medido em 28/08/2026, commit `44469bd`, sobre `ruff check .`: **31 violações**, todas com
correção automática (`ruff check --fix`).

| Onde | Qtd. | Códigos silenciados que não estão ligados |
|---|---|---|
| `app/core/observability/*` | 6 | `ANN401`, `ANN001`, `E501`, `BLE001` |
| `app/core/cache.py` | 4 | `ANN401`, `BLE001` |
| `app/domain/automations/*` | 4 | `BLE001` |
| `app/core/migrations.py` | 2 | `BLE001` |
| `app/domain/{financial,templates}/router.py` | 2 | `A002` |
| `app/workers/celery_app.py` | 1 | `F401` |
| `tests/integration/*` | 9 | `F401`, `ANN001`, `S608` |
| `tests/meta/test_ai_guardrails.py` | 2 | `SLF001` |
| `tests/perf.py` | 1 | `ANN001`, `E501` |

## 3. A armadilha desta spec — leia antes de rodar `--fix`

`RUF100` diz «este `noqa` é inútil **dadas as regras ligadas hoje**». Três dos códigos
suprimidos estão programados para serem ligados por specs desta mesma leva:

- **`S608`** em `tests/integration/test_post_comments.py:452` — a spec 115 liga a família `S`.
  Apagar aqui e reintroduzir lá é trabalho ao quadrado, e pior: se a 115 não olhar essa linha,
  ela vai aparecer como violação nova sem contexto.

A ordem escolhida para a leva resolve isso de propósito: esta spec vem **antes** da 115, e a
115 tem no escopo reavaliar essa linha específica. A regra 3 abaixo torna isso obrigatório em
vez de esperar que alguém lembre.

`ANN*`, `BLE001`, `A002` e `SLF001` **não** estão programados para nenhuma spec desta leva —
esses saem sem ressalva.

## 4. Fora de escopo

- Ligar `ANN`, `BLE`, `A` ou `SLF`. Se alguma dessas famílias merecer gate, é spec própria —
  e a decisão fica mais fácil depois desta, porque o inventário acima mostra onde elas
  doeriam.
- `eslint-disable` órfão no frontend. Spec futura.

## 5. Modelo de dados / API / Front-end

Nada.

## 6. Regras de negócio

1. `RUF100` no `select`.
2. As 31 diretivas saem. `ruff check --fix` resolve todas; conferir o diff antes de commitar,
   porque `--fix` também mexeria em outras regras se rodado sem `--select`.
3. **A linha `tests/integration/test_post_comments.py:452` é registrada em `## 8. Descobertas`
   com o texto original do `noqa`**, e a spec 115 cita esta spec ao reavaliá-la. Nenhuma das
   duas fica dependendo da memória de quem implementa.
4. Nenhum `noqa` novo é criado por esta spec.
5. Depois desta spec, todo `# noqa` que sobrar no projeto está segurando algo de verdade — e o
   `test_final_audit.py`, estendido pela 106, exige justificativa em todos eles.

## 7. Plano de testes

Nenhum teste novo. O gate é o `make lint`.

```bash
cd backend && uv run ruff check . --select RUF100
```

**Total estimado:** +0 s

## 8. Descobertas

### O comando da §7 desta spec está errado, e rodá-lo com `--fix` teria apagado dois `noqa` legítimos

A §7 manda medir com:

```bash
uv run ruff check . --select RUF100
```

`--select` **substitui** o `select` do `pyproject.toml` em vez de somar a ele. Com só o
`RUF100` ligado, nenhuma outra regra existe — e aí **todo** `# noqa` do projeto parece
inútil, porque nenhum deles está silenciando uma regra ativa. Medido assim, o resultado é 35
violações; medido certo, 29.

As seis de diferença são as diretivas que estão segurando algo de verdade, entre elas os
**dois `# noqa: PLR0913`** que a spec 116 acabou de criar e travar com meta-teste. Um
`ruff check . --select RUF100 --fix` teria apagado os dois, e o `PLR0913` voltaria a
reprovar no `make lint` sem que o diff explicasse por quê.

Formas corretas: `--extend-select RUF100`, ou pôr a regra no `select` e rodar `ruff check .`
— que é o que o CI faz de qualquer jeito. A advertência ficou escrita no `pyproject.toml`, ao
lado da regra, porque é lá que a próxima pessoa vai procurar.

Vale como regra geral desta leva: **`--select` num comando de medição mente sobre qualquer
regra cujo resultado dependa das outras estarem ligadas.** `RUF100` é o caso extremo, mas o
mesmo vale para qualquer coisa que raciocine sobre supressões.

### 29, não 31 — e a diferença entre «não ligada» e «inútil»

O Ruff distingue dois motivos, e a distinção importa:

- **`non-enabled: X`** (21 casos) — a regra não está no `select`. O `noqa` seria válido se
  alguém ligasse `ANN`, `BLE`, `A` ou `SLF`. É supressão *preventiva*, escrita contra uma
  regra que o projeto nunca adotou.
- **`unused: X`** (8 casos) — a regra **está** ligada e o código não a viola. É supressão
  *morta*: já foi verdadeira e deixou de ser, ou nunca foi.

Os oito mortos são os mais interessantes, porque documentavam um problema que não existe:
quatro `F401` em `import setup as setup` (a forma de reexportação explícita, que o `F401`
nunca marcou) e quatro `E501` em linhas que hoje cabem em 100 colunas — encolheram em alguma
refatoração e o `noqa` ficou.

### Os dois `noqa` da família `S` que a spec 115 vai reencontrar

A §3 previa **um**. São **dois** — e o segundo é o mais delicado dos dois.

**1. `tests/integration/test_post_comments.py:454`** (a §3 diz 452; o arquivo cresceu)

```python
rows = await session.execute(
    text(
        f"SELECT count(*) FROM {table} WHERE id = CAST(:id AS uuid)"
    ),  # noqa: S608
    {"id": row_id},
)
```

Sem justificativa escrita. O `S608` (SQL injection por interpolação) dispara pelo `{table}`
no f-string. Aqui o valor vem de uma lista literal de nomes de tabela definida no próprio
teste, e o `id` — que é o dado — viaja como parâmetro ligado. **A 115 deve repor o `noqa`
com a justificativa que faltava**, não apenas repor o marcador.

**2. `tests/conftest.py:105`**

```python
subprocess.run(  # noqa: S603 — argumentos fixos, nada vem de fora
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    ...
)
```

Este já vinha com justificativa, e ela é boa: a lista de argumentos é literal. **A 115 deve
repor o marcador E o texto**, que se perdeu junto.

Os dois estão registrados aqui exatamente para que a 115 não precise redescobri-los — e para
que ela note que o primeiro chega sem defesa escrita.

### O `--fix` apaga prosa, e meu diff mecânico foi cego para isso

Três linhas tinham DOIS marcadores e uma justificativa só:

```python
def _count(conn, cursor, ...) -> None:  # type: ignore[no-untyped-def]  # noqa: ANN001, E501 — assinatura fixada pelo evento do SQLAlchemy, sem stubs
```

O `ruff --fix` remove o `# noqa` **e tudo que vem depois dele na linha** — inclusive o texto
que justificava o `# type: ignore`, que fica. As três linhas saíram sintaticamente corretas,
sem `noqa` morto, e **sem a explicação de por que o `type: ignore` existe**.

Meu diff mecânico não viu: ele comparava a linha antiga com o `# noqa...$` removido contra a
nova, e as duas batiam exatamente. A verificação estava certa sobre o que se propunha a
provar — que nenhum **código** mudou — e cega para o que também estava naquele span:
**documentação**.

Quem viu foi o `test_final_audit.py::test_todo_type_ignore_tem_justificativa`, escrito na
spec 100, que exige prosa na linha do marcador ou nas quatro acima. As três justificativas
voltaram como comentário na linha de cima, que é onde a auditoria procura e onde elas
sobrevivem ao próximo `--fix`.

A lição vale além desta spec: **quando dois marcadores dividem uma linha, a justificativa
pertence à linha de cima, não ao rabo do comentário** — ali ela é propriedade de quem vier
primeiro a ser removido.

### O que a regra protege que nada protegia

`RUF100` é o único gate do projeto que olha para as **supressões** em vez do código. Os
outros perguntam «este código está bom?»; este pergunta «este pedido de exceção ainda faz
sentido?».

Sem ele, um `# noqa` sobrevive a qualquer refatoração — inclusive à que apagou o motivo dele.
E supressão morta corrói mais que ruído: quem lê aprende que `noqa` no projeto não quer dizer
nada, e passa a ignorar também os seis que seguram algo. Depois desta spec, os seis
sobreviventes são todos verdadeiros: quatro `F401` de import por efeito colateral e os dois
`PLR0913` da 116.

Combinado com o `test_final_audit.py` (que a 106 estendeu para exigir justificativa em cada
`noqa`), o projeto passa a ter as duas metades: **todo `noqa` precisa segurar algo, e precisa
dizer o quê.**

## 9. Definição de pronto

- [x] `RUF100` no `select`, com a advertência sobre `--select` escrita ao lado
- [x] As **29** diretivas removidas (não 31 — a medição original usou o comando errado)
- [x] Diff conferido **mecanicamente**: 29 linhas removidas, 29 acrescentadas, e cada par
      difere APENAS pela remoção do `# noqa`. Nenhuma linha de código mudou.
- [x] Os **dois** `noqa` da família `S` registrados em §8 para a 115 — a spec previa um
- [x] Os dois `# noqa: PLR0913` da 116 sobreviveram, como devia
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 113 em ✅
- [x] Commit `refactor(113): remove noqa que não silencia nada`
