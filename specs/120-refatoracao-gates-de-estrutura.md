# 120 — 🔧 REFATORAÇÃO — Gates de estrutura

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** manter o wall-clock ≤ 200 s
**Depende de:** 111–119 · **Status:** ⬜ pendente

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

Preencher durante a implementação.

## 12. Definição de pronto

- [ ] As cinco auditorias percorridas, item a item
- [ ] Todo valor numérico de gate comparado, via `git log -p`, com o valor de entrada
- [ ] Revisão humana dos três gates de proxy feita e registrada em §11
- [ ] `docs/GATES.md` escrito, com meta-teste que o mantém completo
- [ ] Wall-clock ≤ 200 s
- [ ] Dívida resolvida ou registrada com spec-alvo
- [ ] Nenhum comportamento alterado; nenhum teste anterior editado
- [ ] `make test` verde
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 120 em ✅
- [ ] Commit `refactor(120): auditoria dos gates de estrutura`
