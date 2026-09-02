# 116 — PLR0913: argumentos demais

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 106, 111, 112 · **Status:** ✅ concluída

---

## 1. Objetivo

Ligar `PLR0913` (too-many-arguments) e resolver as funções acima do teto. Assinatura longa é
o sintoma clássico de uma função que faz mais de uma coisa, ou de um conjunto de parâmetros
que já é um objeto e ninguém nomeou — que é exatamente o SRP do `CLAUDE.md` §5 aplicado à
assinatura.

> Refatoração: nenhuma mudança de comportamento. Muda a forma de chamar, não o que acontece.

## 2. Nota sobre esta spec

Na auditoria que originou esta leva, `PLR0913` foi a única regra que eu recomendei **não**
ligar: o `Depends()` do FastAPI infla a contagem por construção, e no teto default de 5
argumentos são 112 violações, das quais 36 em `router.py` são rotas legítimas. A decisão de
ligar assim mesmo foi tomada; a spec cumpre isso, e a forma de cumprir sem transformar o gate
em ruído é a calibragem da seção 3. Registrado aqui para quem ler daqui a seis meses saber que
o número não foi escolhido no chute.

## 3. Calibragem — medida, não arbitrada

Contagem em 28/08/2026, commit `44469bd`, sobre `ruff check .`:

| `max-args` | Total | Em `router.py` | Fora de `router.py` |
|---|---|---|---|
| 5 (default) | 112 | 36 | 76 |
| 6 | 48 | 16 | 32 |
| 7 | 30 | 9 | 21 |
| **8** | **14** | **5** | **9** |
| 10 | 5 | 3 | 2 |
| 12 | 3 | 2 | 1 |

**Escolha: `max-args = 8`.** É o joelho da curva. Abaixo dele o número explode por causa do
padrão de DI do FastAPI e dos repositórios com muitos filtros — que são casos reais, mas não
são o defeito que a regra existe para achar. Em 8, sobram 14 funções, e cada uma tem
assinatura longa de verdade, não por causa de framework.

```toml
[tool.ruff.lint.pylint]
max-args = 8
```

Sem `per-file-ignores` para `router.py`: cinco rotas ficam acima de 8 e elas merecem o mesmo
tratamento que o resto. Silenciar a camada inteira esconderia a rota que realmente tem 14
parâmetros.

## 4. Escopo — as 14

As nove fora de `router.py` são o núcleo do trabalho. Os campeões, e o que fazer:

| Arquivo:linha | Args | Correção |
|---|---|---|
| `domain/customers/repository.py:114` | 14 | filtros de listagem → um dataclass `CustomerFilters` |
| `integrations/http/client.py:45` | 11 | configuração de resiliência → um dataclass `RetryPolicy` |
| `domain/customers/repository.py:63` | 10 | mesmo `CustomerFilters` |
| `domain/financial/repository.py:255` | 10 | `TransactionFilters` |
| `domain/financial/service.py:339` | 10 | idem, repassando o filtro |
| `domain/ai/service.py:361` | 9 | separar contexto de execução dos parâmetros de chamada |
| `domain/posts/service.py:85` | 9 | `PostFilters` |
| `domain/ai/editor.py:365`, `domain/ai/service.py:109` | 8 | idem |
| `core/dates.py:199` | 8 | avaliar caso a caso |

O padrão dominante é evidente: **repositório de listagem recebendo cada filtro como parâmetro
solto**. Aparece em `customers`, `financial`, `posts` e `reports` — quatro vezes, muito além
da regra dos 3 usos do §6. A correção certa não é encurtar quatro assinaturas em quatro
lugares diferentes; é um objeto de filtro por contexto, e possivelmente um tipo base comum,
já que `BaseRepository` existe desde a 003.

As cinco em `router.py` ficam por último: mexer em assinatura de rota é o que tem maior chance
de mudar contrato, e o contrato é o que não pode mudar.

## 5. Fora de escopo

- Baixar `max-args` abaixo de 8. Se um dia fizer sentido, é spec própria, com nova medição.
- `max-positional-args`. Regra diferente, discussão diferente.
- Tocar nas 19 ocorrências em `tests/` que estão abaixo de 8 — no teto escolhido elas nem
  aparecem.

## 6. Modelo de dados / API / Front-end

Nada. **Nenhum contrato de API muda**: as cinco rotas afetadas continuam aceitando exatamente
os mesmos query params, com os mesmos nomes, tipos e defaults. O que muda é como o router
repassa isso para baixo. O `test_public_api_contract.py` e o snapshot de rotas são a prova.

## 7. Regras de negócio

1. `PLR0913` no `select`, `max-args = 8`.
2. Nenhuma mudança de comportamento; nenhum contrato de API alterado.
3. Objeto de filtro é `dataclass` ou modelo Pydantic tipado — nunca `dict[str, Any]`. Trocar
   argumentos demais por um `Any` seria piorar o código para agradar o lint.
4. Onde o mesmo padrão de filtro aparecer pela terceira vez, ele sobe para um tipo comum
   junto ao `BaseRepository` (§6, regra dos 3 usos).
5. Nenhum `per-file-ignores`. No máximo **2** `# noqa: PLR0913`, com justificativa, travados
   por meta-teste.
6. As cinco rotas são as últimas a serem tocadas.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | no máximo 2 `# noqa: PLR0913`, justificados | `tests/meta/test_final_audit.py` (estende) | ~0,1 s |
| meta | as rotas de `/api/v1` aceitam os mesmos query params de antes (snapshot) | `tests/meta/test_public_api_contract.py` (estende) | ~0,3 s |
| — | testes de listagem das specs 018, 022, 052 e 084 passam sem edição | — | — |

**Total estimado:** +0,4 s

## 9. Descobertas

### A calibragem se confirmou

Recontagem sobre `5fdb537`: 126 / 50 / 31 / **15** / 6 / 3 nos tetos 5 / 6 / 7 / 8 / 10 / 12 —
praticamente igual à medição de 28/08 (que dava 112 / 48 / 30 / 14 / 5 / 3; a diferença são
rotas novas). O joelho em 8 continua sendo o joelho. Foi a primeira spec desta leva em que o
gate **não** chegou verde: 15 funções de verdade para resolver.

### O objeto de filtro comum apareceu — e o que subiu foi a PAGINAÇÃO, não o filtro

A §4 previa «possivelmente um tipo base comum, já que `BaseRepository` existe desde a 003».
Apareceu, mas não onde a spec apontava. Os *filtros* não sobem: contatos filtram por
aniversário, lançamentos por vencimento, tarefas por prazo — não há denominador comum
honesto, e forçar um daria um objeto com quinze campos opcionais dos quais cada listagem usa
cinco.

O que sobe é o outro lado: `sort`, `descending`, `cursor` e `limit` são **os mesmos quatro em
toda listagem**, porque são o contrato do §6 do `CLAUDE.md`. Viraram `Page`, em
`app/core/listing.py`, ao lado do `paginate_keyset` que já os consumia. Cinco repetições do
mesmo quarteto, muito além da regra dos 3 usos.

Ficou uma separação que a assinatura antiga não tinha: **o que filtrar** e **como paginar**
são duas perguntas, e agora são dois parâmetros.

### Um objeto de filtro por contexto, e a razão de não reusar o schema

Nasceram `CustomerQuery`, `TransactionQuery` e `TaskQuery` — no repositório, não no
`schemas.py`. A tentação era passar o `CustomerFilters` (que já existia) direto para baixo, e
ela **quebraria**: o schema declara `birthdays: Literal["day", "month"]`, e a rota pública de
aniversariantes manda `"month:<n>"`. Construir o schema com esse valor levantaria erro de
validação onde hoje há resposta errada — mudança de comportamento, proibida aqui.

Isso não foi um obstáculo, foi um achado: o tipo separado tornou VISÍVEL um descasamento que
o `str | None` solto escondia. Ver a **dívida 34** — a rota pública de aniversariantes não
filtra nada e devolve os primeiros mil contatos do escritório. É anterior a toda esta leva
(conferido em `da213af`); não foi corrigida aqui porque 116 é refatoração.

### O ganho maior foi no financeiro, e é de correção, não de forma

`TransactionQuery` unificou o mesmo octeto de filtros que aparecia em **cinco** assinaturas.
A regra 9 da spec 059 exige que o rodapé de somatórios use *exatamente* o mesmo filtro da
página. Com oito parâmetros soltos, «o mesmo filtro» era uma convenção que dependia de alguém
repetir oito nomes certos em dois lugares — e o router os repetia, literalmente, em duas
chamadas seguidas. Agora é o mesmo objeto passado duas vezes. A classe de bug «o rodapé soma
um recorte diferente do que a tabela mostra» deixou de ser possível.

### A armadilha do alias, que quase entrou em produção

Para as rotas, o padrão é `filtros: Modelo = Depends()`: o FastAPI expande os campos em query
params. Funcionou em cinco rotas e **falhou numa**, silenciosamente.

Num modelo usado como dependência, o FastAPI monta a assinatura da rota dinamicamente e usa o
alias como NOME DE PARÂMETRO — o que ele não consegue fazer quando o alias é palavra
reservada do Python. Aí ele cai, sem avisar, no nome do campo:

```
alias="status" -> query param `status`   (funciona)
alias="from"   -> query param `from_`    (vira o nome do campo)
alias="class"  -> query param `a_`       (idem)
```

`GET /reports/tabular/{report_key}?from=...` existe desde a spec 070. O param teria virado
`from_`, a rota continuaria respondendo 200, e o filtro de data simplesmente deixaria de
existir. Nenhum teste de rota que confere status pegaria.

Quem pegou foi o **diff de query params contra o baseline**, que é a razão de tirá-lo antes
de encostar no código. A correção é declarar os `Query(...)` numa dependência de **função**
(`report_scope`), não como campo de modelo. E virou teste permanente: nenhum query param do
projeto pode terminar em `_`, porque ninguém batiza um assim de propósito.

### O `Depends()` também revelou uma rota que aceitava o que não usava

`GET /publications/counts` construía um `PublicationFilters` completo mas só preenchia sete
dos dez campos — os três toggles são o que ela CONTA, não o que ela filtra (§8 da 048). Com
`Depends()` no tipo completo, ela passaria a publicar `linked`/`cancelled`/`read` como query
params que não fazem nada.

Daí a divisão em `PublicationScope` (o recorte) e `PublicationFilters(PublicationScope)` (o
recorte mais os toggles). O tipo passou a dizer o que cada rota aceita, em vez de a rota
ignorar campos em silêncio.

### Duas exceções, e por que elas são as certas

O teto de 2 `# noqa: PLR0913` foi usado inteiro, e nos dois casos em que o cheiro que a regra
procura não está presente:

1. **`ResilientHttpClient.__init__`** (11) — são dependências injetadas, e injetar é a única
   coisa que o construtor faz. Cinco existem para o teste substituir tempo e acaso; agrupá-las
   obrigaria a editar 15 chamadas de teste para tornar `sleep=_no_sleep` mais verboso.
2. **`make_publication`** (10) — construtor de dado de teste. Os opcionais são o que cada caso
   varia um de cada vez («como as outras, mas cancelada»). O objeto que os agrupasse não teria
   nome que descrevesse nada: ele seria «os argumentos».

Havia um terceiro candidato, `_add_expense` em `test_bi_costs.py`, e ele tinha correção
estrutural de verdade: `cost_center_id` e `account_id` eram **literalmente sempre os mesmos**
nas catorze chamadas, e só a categoria variava. Viraram `_Contas`, e as catorze chamadas
ficaram três linhas mais curtas cada. Foi o que manteve o teto em 2 — e a diferença entre as
três decisões é a mesma pergunta: agrupar dá um nome a alguma coisa, ou só encurta a lista?

### O gate de camadas pegou uma violação minha

O `make test` reprovou em `test_camadas.py::test_nenhum_router_importa_repositorio`: eu tinha
feito o router do financeiro construir um `TransactionQuery`, que é tipo de repositório.

O gate estava certo, e a correção mostrou onde a tradução deve morar: **no service**, que é
quem faz a ponte entre HTTP e domínio (§5). Foi exatamente o desenho que `customers/service.py`
já usava com o `_consulta` — eu tinha acertado por lá e escorregado aqui, e um meta-teste
escrito há dezenas de specs me devolveu à consistência sem discussão. É o argumento a favor
desse tipo de teste em uma frase.

## 10. Definição de pronto

- [x] `PLR0913` no `select` com `max-args = 8`, provado reprovando uma função de 9
- [x] As 15 (não 14) resolvidas; exatamente 2 `noqa`, justificados e travados por meta-teste
- [x] Nenhum `per-file-ignores`
- [x] Objetos de filtro tipados (`dataclass` frozen e modelos Pydantic), sem `dict[str, Any]`
- [x] **Nenhum query param de rota mudou de nome, tipo, default ou obrigatoriedade** — 276
      operações comparadas com o baseline, zero divergência; 311 caminhos, 384 operações, e a
      ordem de registro idêntica
- [x] Nenhum teste anterior editado — nenhuma asserção tocada; `_add_expense` teve a própria
      assinatura melhorada, e é helper, não caso de teste
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 116 em ✅
- [x] Commit `refactor(116): argumentos demais`
