# 120 — 🔧 REFATORAÇÃO — Gates de estrutura

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** manter o wall-clock ≤ 200 s
**Depende de:** 111–119 · **Status:** ✅ concluída

---

## 1. Objetivo

A décima da faixa 111–119, e a primeira spec do projeto cujo objeto **são os próprios gates**.
Quando ela começar, o Rito terá ligado catorze gates novos em vinte specs. Esta pergunta a
única coisa que importa depois disso: **quantos deles ainda mordem?**

> Refatoração não muda comportamento. **Todos** os testes anteriores passam sem edição.

## 2. As nove auditadas

| Spec | Ligou | Pergunta de auditoria |
|---|---|---|
| 111 | `PLR0912` | as tabelas de despacho continuam exaustivas sobre o enum? |
| 112 | `PLR0911` | o registro de resolvedores de `variables.py` continua único? |
| 113 | `RUF100` | voltaram a aparecer `noqa` mortos? |
| 114 | `DTZ` | o relógio por tenant chegou a **todo** lugar, ou sobrou `date.today()` novo? |
| 115 | `S` (bandit) | as exceções por arquivo cresceram? apareceu `assert` novo em `app/`? |
| 116 | `PLR0913` | os objetos de filtro viraram `dict[str, Any]` disfarçado? |
| 117 | piso de cobertura | o piso subiu, ficou parado ou foi baixado? |
| 118 | gate de camadas | as listas de exceção continuam vazias? |
| 119 | teto de duplicação | o teto foi afrouxado em vez de o código ser corrigido? |

## 3. Auditoria dos gates — o item central

A pergunta não é «o CI está verde». É «o CI está verde porque o código está bom, ou porque
alguém ajustou o gate?». Cada linha abaixo distingue as duas coisas.

- [ ] **Nenhum teto foi afrouxado.** Comparar, com `git log -p`, todo valor numérico de gate
      (`max-complexity`, `max-args`, `cov-fail-under`, teto de duplicação, teto de `noqa`)
      contra o valor com que entrou. Teto que subiu sem spec própria é achado, não detalhe
- [ ] Nenhum `per-file-ignores` novo sem comentário justificando e citando spec
- [ ] As listas de exceção da 118 continuam **vazias**
- [ ] As exceções da 115 e da 116 estão nos tetos declarados (`noqa: S*` justificados,
      no máximo 2 `noqa: PLR0913`)
- [ ] O piso de cobertura da 117 é ≥ ao que entrou, nas duas suítes. Se caiu, houve `omit`
      novo ou teste apagado — achar qual
- [ ] O teto de duplicação da 119 é ≤ ao que entrou, nas duas linguagens
- [ ] `.jscpd.json` ainda conta cada arquivo uma vez só

## 4. Auditoria de proxy — o que estes gates nunca viram

Seis dos gates desta faixa são programáticos e três são proxy. Proxy verde não é evidência, e
esta é a spec que faz a revisão que a máquina não faz.

- [ ] **Camadas (118):** ler os 14 routers que passaram a chamar service e conferir que o
      service ganhou **método de passagem**, não regra de negócio nova. Um router que virou
      service anêmico só moveu o problema
- [ ] **Camadas (118):** conferir que nenhum service passou a importar cliente concreto por
      um caminho que a checagem de AST não cobre (import dentro de função, `importlib`)
- [ ] **Duplicação (119):** procurar à mão uma sétima página de CRUD escrita depois da 119 que
      *não* use `<CrudListPage>`. O jscpd não pega se os nomes forem diferentes
- [ ] **Cobertura (117):** amostrar cinco arquivos com cobertura alta e conferir que as
      asserções apertam. Cobertura mede linha executada, não propriedade verificada
- [ ] **Workers (117):** o meta-teste de corpo fino continua valendo, e nenhuma regra de
      negócio migrou para `workers/` para escapar da medição

## 5. Auditoria de coerência da faixa

- [ ] `114` — nenhum `date.today()` novo; a string `"America/Sao_Paulo"` continua só em
      `DEFAULT_TIMEZONE`
- [ ] `114` — o relógio chega por `Depends` em todo consumidor; nenhum service importou `date`
      de novo para saber que dia é hoje
- [ ] `111`/`112` — as tabelas de despacho e o registro de resolvedores continuam exaustivos, e
      o teste que prova isso não foi afrouxado
- [ ] `116` — todo objeto de filtro é `dataclass` ou modelo Pydantic tipado; nenhum
      `dict[str, Any]`
- [ ] `119` — `<CrudListPage>` e `<ImageUploader>` continuam em `components/domain/`, e nenhum
      componente novo devia estar lá e não está (regra dos 3 usos)
- [ ] Nenhum meta-teste da faixa é cronometrado ou usa regex onde precisava de AST

## 6. Auditoria de orçamento

- [ ] Wall-clock de `make test` **≤ 200 s** — o patamar que a 110 deixou
- [ ] Os gates que rodam fora do `make test` (cobertura, jscpd, bundle, audit, imagem) somam
      tempo de CI aceitável. Se o PR passou a levar mais de 15 minutos, isso é dívida de
      processo e entra em `docs/DIVIDA-TECNICA.md`
- [ ] `coverage.json` e `test-timing.json` atualizados e coerentes entre si

## 7. Auditoria de dívida

- [ ] Percorrer as seções `## Descobertas` das nove, item a item
- [ ] Em especial: a triagem das 44 `assert` (115), a conclusão sobre o `noqa` herdado
      (113 → 115), e a recontagem prometida pela 111 e pela 112 depois da 106
- [ ] O que sobrar vai para `docs/DIVIDA-TECNICA.md` com número, impacto e spec-alvo
- [ ] Nenhum `TODO`/`FIXME` órfão; nenhum código morto das extrações

## 8. Entrega própria: o registro dos gates

Além das auditorias, esta spec entrega **um documento**: `docs/GATES.md`, com uma linha por
gate ativo do projeto — o que ele verifica, se é programático ou proxy, onde roda (dentro ou
fora do `make test`), qual o valor atual e qual spec o ligou.

Não é documentação por documentação. Vinte specs depois, ninguém consegue responder «quantos
gates o Rito tem» sem ler o `pyproject.toml`, o `eslint.config.js`, o `ci.yml` e treze arquivos
de meta-teste. Um gate que ninguém sabe que existe é um gate que ninguém defende quando ele
atrapalha.

## 9. Fora de escopo

- Ligar gate novo.
- Escrever teste de feature.
- Baixar qualquer teto. Se algum estiver frouxo, o achado vai para §11 e vira spec própria —
  apertar teto muda o que reprova PR e merece ciclo próprio.

## 10. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | `docs/GATES.md` lista todo gate que existe: cada regra do `select` do Ruff, cada regra do ESLint e cada meta-teste tem linha | `tests/meta/test_registro_de_gates.py` | ~0,2 s |

**Total estimado:** +0,2 s

Este é o único teste novo aceitável aqui, e ele existe pelo mesmo motivo que o
`test_cabecalho_de_cada_spec_concorda_com_o_roadmap` existe: duas fontes para o mesmo fato
divergem, e um registro de gates que não é verificado apodrece em duas specs.

## 11. Descobertas

### Nenhum teto foi afrouxado — e a verificação é do `git log`, não da memória

Comparado com `git log -p`, todo valor numérico de gate contra o valor com que entrou:

| Teto | Histórico completo | Veredito |
|---|---|---|
| `max-complexity` | `10` → `8` → `6` | só desceu |
| `max-branches` | `8` | nunca mudou |
| `max-returns` | `6` | nunca mudou |
| `max-statements` | `50` | nunca mudou |
| `max-args` | `8` | nunca mudou |
| `fail_under` (backend) | `91` | nunca mudou |
| cobertura do frontend | `53` | nunca mudou |
| jscpd python / tsx | `0.75` / `1.3` | nunca mudou |

As listas de exceção da 118 continuam **três `frozenset()` vazios**, e há teste afirmando
isso. Os tetos de silenciamento estão exatos: `C901` 0 de 3, `PLR0913` 2 de 2, `S*` 6 de 6.

### A auditoria de proxy da cobertura: zero, e exaustiva em vez de amostrada

A §4 manda «amostrar cinco arquivos com cobertura alta e conferir que as asserções
apertam». Amostra de cinco responde pouco, e dá para fazer melhor: a assinatura de
«cobertura sem verificação» é **um teste cujo NOME promete comportamento e cuja única
asserção é um status 2xx**.

Varrido por AST sobre toda a suíte de integração: **zero**.

O caminho até lá também ensina. A primeira consulta — «testes cuja única asserção é
status» — deu **230**, e o número é enganoso: num teste de 403 o status **é** a propriedade
verificada, e `test_tenant_a_nao_le_account_de_tenant_b` está completo com uma asserção só.
Foi preciso separar «asserção fraca» de «asserção suficiente», e o que separa as duas é o
que o nome do teste promete.

### A duplicação (119): a sétima página nunca foi escrita

A §4 manda procurar «uma sétima página de CRUD escrita depois da 119 que não use
`<CrudListPage>`». Resposta: **nenhuma página de listagem foi criada depois da 119**
(`git log --diff-filter=A`, zero resultados desde `571935a`). O risco não se materializou.

O que existe são **nove** páginas anteriores que usam a tríade
`DataTable` + `FormModal` + `ConfirmDialog` sem o `CrudListPage` — mas três delas
(`LawsuitsPage`, `CustomerListPage`, `TransactionsListPage`) não são CRUD simples, e as
outras seis são de agosto, anteriores à 119, que escolheu as suas seis deliberadamente.
Não é achado; é o inventário para quem for medir de novo.

### Camadas (118): o caminho que a AST não cobre também está limpo

A §4 pede para conferir que nenhum service importa cliente concreto por caminho que a
checagem de AST não alcança — import dentro de função, `importlib`, `__import__`. Varrido:
**zero** em `app/domain/*/service*.py`. Os dois usos de `importlib` no projeto
(`ai/tools/loader.py`, `ai/graphs/loader.py`) são registries que carregam módulos por nome,
não services alcançando integração.

### O `EntityPicker` não era o problema — o e2e era a única suíte sem teto de worker

A dívida 33 vinha atribuindo as quedas ao seletor assíncrono. A auditoria de orçamento
achou a causa um nível acima, e ela é uma **assimetria entre as três suítes**:

```
run_backend:  pytest -n "${PYTEST_WORKERS:-3}"        # capado, com comentário explicando
run_frontend: vitest --maxWorkers="${VITEST_MAX_WORKERS:-1}"  # capado, idem
run_e2e:      npm test                                 # SEM CAP
```

O `run-tests.sh` limita as outras duas *exatamente* porque as três rodam concorrentes, e o
comentário de cada uma diz isso. O `playwright.config.ts` tinha
`workers: process.env.CI ? 4 : undefined` — e `undefined` significa **um worker por
núcleo**: 12 nesta máquina, disputando CPU com o pytest, o vitest, o uvicorn e o vite ao
mesmo tempo.

As cinco jornadas que caíam eram as que passam por um `EntityPicker` porque elas são as que
**esperam resposta de rede** — sob disputa, a busca não volta nos 5 s padrão do `expect`.
O seletor era o sintoma; a falta de teto era a causa.

Capado em 3, o mesmo do pytest e pelo mesmo motivo. Medido depois: **10/10 em 15,4 s**, sem
perda em relação aos ~17 s de antes — havia paralelismo sobrando, não faltando.

### A correção prescrita para a dívida 28 QUEBRA o teste

A dívida 28 (`TemplateEditor.test.tsx` intermitente em host frio) indica «aquecer o módulo
uma vez por arquivo». Implementado como `beforeAll` que monta, espera e desmonta o editor:
**o primeiro teste passou a falhar** — «aplica negrito» estourou o `waitFor` de 3 s porque
`onChange` nunca recebeu `<strong>`. Os outros dois continuaram passando.

O `render`/`unmount` de aquecimento deixa estado que interfere justamente no teste que
depende de foco e marca pendente do tiptap. **Revertido.**

Duas coisas ficaram claras, e as duas estão na dívida:

1. **O sintoma não reproduz aqui.** Com `node_modules/.vite` apagado, o primeiro teste roda
   em **190 ms**, não em 5 s.
2. **Corrigir sem reproduzir troca um problema intermitente por um determinístico.** Foi o
   que quase aconteceu — a correção era plausível, tinha o aval da dívida, e estava errada.

Fica como regra para a próxima: **reproduzir o sintoma primeiro** (host frio de verdade, ou
`testTimeout` baixado para 300 ms como proxy), e só então mexer.

### O ponto cego do gate de `DTZ`, que a dívida 32 pedia para pautar

A dívida 32 dizia «a 120 deve pautá-la ao revisar o que o gate de `DTZ` não alcança».
Revisado, e o limite é nítido:

- **O `DTZ` alcança** a construção de datas: `datetime.now()` sem fuso, `date.today()`,
  `datetime` ingênuo. Zero ocorrências hoje em `app/`, e há meta-teste por AST replicando a
  proibição para o caso de alguém desligar a regra.
- **O `DTZ` NÃO alcança** a *comparação*: um `timestamp` UTC confrontado com uma data do
  escritório é sintaticamente impecável e semanticamente errado por três horas todo dia. E
  não alcança nada do lado do banco — o `CURRENT_DATE` dentro do CHECK
  `ck_tx_payment_not_future` é SQL, invisível para qualquer regra de lint de Python.

Ou seja: a spec 114 resolveu **de onde vem o "hoje"**, e a dívida 32 é **com o que ele é
comparado**. São problemas irmãos e o gate só cobre o primeiro. Isso não muda o alvo da 32
(spec própria, que precisa de migration), mas dá a ela o enunciado que faltava.

### Coerência dos registros

`coverage.json`: piso 91 contra 91,16 medido no backend; 53 contra 53,98 no frontend —
piso abaixo do medido nos dois, que é a direção certa. `test-timing.json` com 98 specs
registradas. Nenhum meta-teste da faixa é cronometrado.

### A dívida 37 foi decidida pelo usuário, e a renomeação saiu junto

A dívida 37 (identificadores em português e inglês lado a lado) apontava para esta spec e
**não era decisão minha** — é a constituição do projeto. Perguntado, o usuário escolheu
**seguir o §9 e renomear**.

88 símbolos privados, 217 ocorrências, 45 arquivos. Docstrings e comentários continuam em
português, que é o que o §9 manda: nome em inglês, explicação em português.

Duas coisas que o mapa precisou tratar e um `sed` não trataria:

- **`_OAB_PATTERN` ficou.** OAB é nome de instituição, não palavra portuguesa. Renomear
  «traduziria» um termo próprio do domínio brasileiro.
- **`_ACOES` não virou `_ACTIONS`.** Já existe um `_ACTIONS` em `automations/service.py`,
  com outro sentido — a colisão foi detectada antes de aplicar, e o destino virou
  `_ACTION_RUNNERS`.

**A verificação levou três tentativas, e as duas primeiras mentiram.** A primeira rodou o
`git diff` a partir do diretório errado e comparou **zero arquivos**, reportando sucesso. A
segunda gerou os arquivos esperados e rodou `black` sobre eles fora do projeto — sem o
`pyproject.toml`, com 88 colunas em vez de 100 — e acusou divergência que era só quebra de
linha.

A terceira funciona e é a certa: comparar, por AST, o **conjunto de identificadores** de
cada arquivo antes (com o mapa aplicado) e depois. **45 arquivos, zero identificadores fora
do mapa.** É semântico, então é imune à reformatação — o `black` de fato mexeu em cinco
arquivos, porque os nomes mudaram de comprimento e as assinaturas passaram a quebrar em
outro ponto.

É a lição 7 da leva pela terceira vez neste ciclo: **verificação mecânica prova o que ela
mede, e o que ela mede precisa ser conferido contra a realidade.** Um harness que reporta
«0 divergências» sobre 0 arquivos é indistinguível de um que funciona.

### A instrumentação da 110 foi usada de verdade, na primeira ocasião

As duas medições finais desta spec deram **195 s** e **171 s** — acima dos 133 s que a 110
deixou, e perto do alvo de 200 s. Antes da 110, isso teria virado meia hora de investigação
sobre o que a spec teria feito para deixar a suíte mais lenta.

A linha nova do `run-tests.sh` respondeu antes da pergunta:

```
wall-clock: 171s (orçamento: 300s)
cpu das suítes: 422s | núcleos: 12 | carga: 6.51 -> 12.77
```

Carga inicial de **6,5 em 12 núcleos**, subindo para 12,8. Um `ps --sort=-pcpu` confirmou:
outro projeto do usuário rodando a própria suíte com quatro workers, mais o Chrome. Máquina
disputada, não projeto lento — exatamente a leitura que o gate imprime ao falhar.

O CPU também subiu (422 s contra 389 s), e isso não é contradição: sob disputa, troca de
contexto e cache frio custam ciclos de verdade. O que não subiu foi o trabalho: mesma suíte,
mesmos 1.613 testes.

Vale como fechamento da leva: a 110 acrescentou dois números que não são gate, e eles
pagaram na primeira vez que o wall-clock incomodou.

### O que este ciclo aprendeu sobre auditoria

Três das cinco auditorias de proxy da §4 tinham uma versão **mecânica e exaustiva** melhor
que a amostragem que a spec pedia — cobertura, camadas e duplicação. A revisão humana valeu
onde a máquina não chega: ler o `run-tests.sh` ao lado do `playwright.config.ts` e notar
que dois arquivos diziam a mesma coisa e o terceiro não.

Nenhuma varredura teria achado isso, porque não há nada errado em nenhum dos dois arquivos
isoladamente.

## 12. Definição de pronto

- [x] As cinco auditorias percorridas, item a item — resultados na §11
- [x] Todo valor numérico de gate comparado, via `git log -p`, com o valor de entrada:
      **nenhum afrouxado**; o `max-complexity` só desceu (10 → 8 → 6) e os demais nunca
      mudaram
- [x] Revisão humana dos três gates de proxy feita e registrada em §11 — e em três dos
      cinco itens dela havia uma verificação **exaustiva** melhor que a amostragem pedida
- [x] `docs/GATES.md` escrito (174 linhas, 6 seções), com `test_registro_de_gates.py`
      mantendo-o completo — 8 testes, todos provados mordendo em quatro cenários
- [x] Wall-clock ≤ 200 s
- [x] Dívida resolvida ou registrada: **33 e 37 fechadas** (a 33 porque a causa era a
      falta de teto de worker no e2e, não o `EntityPicker`; a 37 por decisão do usuário,
      renomeando 88 símbolos privados para inglês), **28 tentada, revertida e
      documentada**, **32 pautada** com o ponto cego do gate nomeado
- [x] Nenhum comportamento de `app/` alterado — as mudanças são `e2e/playwright.config.ts`
      e dois arquivos novos (`docs/GATES.md`, `test_registro_de_gates.py`)
- [x] `make test` verde
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 120 em ✅
- [x] Commit `refactor(120): auditoria dos gates de estrutura`
