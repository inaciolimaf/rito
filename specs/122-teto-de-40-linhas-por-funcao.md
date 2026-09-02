# 122 — Teto de 40 linhas por função (backend)

**Fase:** 12 · **Tipo:** refatoração · **Orçamento:** +0 s (o gate já existe)
**Depende de:** 121 · **Status:** ✅ concluída

---

## 1. Objetivo

Descer o teto de tamanho de função do backend de **50 para 40** linhas líquidas de corpo, e
trazer as 32 funções acima dele para dentro. Segundo dos três degraus que a Nota de execução
da 121 prescreve.

> Refatoração: nenhuma mudança de comportamento. Nenhum contrato de API muda, nenhum teste
> anterior é editado.

## 2. Por que em degraus, e por que este número

A 121 mediu 118 funções acima de 30 e entregou o teto em 50 — de 20 acima para zero, em 29
extrações. Fazer 30 de uma vez seria uma spec que não fecha, e spec que não fecha deixa o
teto onde estava por mais um ciclo. É o mesmo raciocínio que levou o `max-complexity` da 106
de 10 a 8 a 6, e funcionou lá.

Medido em `cdeb4cc`:

| Teto | Funções acima |
|---|---|
| 50 | **0** (o de hoje) |
| 45 | 16 |
| **40** | **32** ← esta spec |
| 35 | 73 |
| 30 | 117 (o alvo final, spec 123) |

Quarenta é o degrau certo porque 45 seria barato demais (16) e 35 já dobra o trabalho (73)
sem ser o alvo. O objetivo de cada degrau é ser grande o bastante para valer o ciclo e
pequeno o bastante para caber nele.

## 3. Escopo

**A.** `TETO_DE_LINHAS` de 50 para 40 em `tests/meta/test_tamanho_de_funcao.py`.

**B.** As 32 funções acima de 40, depois da recontagem obrigatória da §9.

**C.** `docs/GATES.md` com o valor novo — o `test_registro_de_gates.py` reprova se divergir.

## 4. Fora de escopo

- Descer abaixo de 40. É a spec 123.
- Frontend. Decidido ao fechar a 121: **não haverá** teto de tamanho de função lá, nem spec
  para isso. Ver dívida 38.
- Mudar a forma de contar. A contagem líquida (docstring, decorador e assinatura fora) foi
  decidida e validada na 121, e mexer nela agora invalidaria a comparação entre degraus.
- Aumentar o teto de exceções. Continua **5 no projeto**, e a 121 fechou com zero.

## 5. Modelo de dados / Contratos de API / Front-end

Nada. O contrato é o mesmo: 311 caminhos, 384 operações, e a prova é o diff de
`app.openapi()` antes e depois.

## 6. Regras de negócio

1. Nenhuma função de `app/` passa de 40 linhas líquidas de corpo.
2. Contagem líquida, como na 121: do primeiro statement executável ao último, com docstring,
   decoradores e assinatura de fora.
3. Toda função extraída é privada (`_nome`), **em inglês** (CLAUDE.md §9, decisão registrada
   na dívida 37), tipada, e `mypy --strict` continua verde sem exceção nova.
4. Docstring e comentário continuam em **português**.
5. Exceções versionadas: teto de **5 no projeto**, cada uma justificada. Se precisar da
   sexta, o teto de 40 está errado para este código e a spec não fecha — essa conclusão vale
   mais que forçar o número.
6. Nenhum teste anterior é editado. Atualizar baseline numérico de meta-teste (como o
   `test_workers_finos`) é manutenção prevista, não edição de asserção.

## 7. O que a 121 aprendeu e esta spec herda

Três lições caras, para não se repetirem:

- **A ordem de guardas É comportamento.** Ao extrair `_template_if_running` na 121, a ordem
  de duas checagens foi invertida e mudou o que acontece quando o modelo some e o limite foi
  atingido. Os 30 testes do módulo passaram — o caso não é coberto. Ao extrair guarda,
  **preservar a ordem e dizer no comentário por que ela é essa**.
- **Compactar não é extrair.** Três tentativas de baixar uma função reescrevendo chamadas em
  menos linhas foram desfeitas pelo `black`, uma delas deixando a função MAIOR (59 → 62). O
  que funciona é tirar um bloco com nome.
- **Quando a função é fluxo, o corte é um objeto para o que viaja junto.** `_Call`,
  `_Attempt` e `_Spent` resolveram o que nenhuma extração de bloco resolvia — e sem eles o
  laço de retry bateria no `max-args` da 116.

## 8. Plano de testes

Nenhum teste novo. O gate é o `test_tamanho_de_funcao.py` que a 121 entregou, com o teto
baixado — e ele já foi provado mordendo.

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| — | os 1.616 testes existentes passam **sem edição** | — | 0 s |

**Total estimado:** +0 s.

## 9. Descobertas

### A recontagem, antes de qualquer edição

Medida em `4b9b223`, com o mesmo contador do gate (linhas líquidas, docstring fora):

| Acima de | Funções | Total do `app/` |
|---|---|---|
| 45 | 16 | 2.460 |
| **40** | **32** | 2.460 |
| 35 | 73 | 2.460 |
| 30 | 117 | 2.460 |

Os 32 bateram exatamente com a projeção da §12 da 121 — o contador é o mesmo, e nada entrou
acima de 40 entre uma spec e outra.

### Trinta cortes, e nenhum precisou de dois

Trinta funções foram reestruturadas; **nenhuma exigiu mais de um corte** para descer de
acima de 40 para abaixo. Isso não é sorte, é consequência da forma da distribuição: as 32
estavam entre 41 e 46 linhas, ou seja, no máximo 6 linhas acima do teto, e todo bloco com
nome próprio que dá para tirar de uma função desse tamanho tem pelo menos 6 linhas.

Foram 24 arquivos, 44 auxiliares novos — mais do que 30 porque três funções renderam dois
blocos nomeáveis cada, e extrair só um deixaria o segundo pela metade.

### As duas exceções, e por que não são preguiça

Duas funções acima de 40 não têm bloco a extrair:

| Função | Linhas | O que é |
|---|---|---|
| `customers/router.py::_customer_to_response` | 42 | `return CustomerResponse(...)` com 40 campos `campo=customer.campo` |
| `posts/router.py::_to_response` | 41 | guarda de tarefa privada (já extraída) + `return PostResponse(...)` com 24 campos |

A classificação foi feita por AST, não a olho: o corpo do primeiro é **um único `Return`**,
sem `if`, `for` ou atribuição. Não existe nome para "a primeira metade dos campos de um
schema" — `_parte_um`/`_parte_dois` seria indireção que esconde a única coisa que o leitor
quer ver, que é a lista de campos. O tamanho deles é o do schema, e desce quando o schema
descer.

Usa 2 das 5 exceções previstas pela regra 5 da 121. As duas com a mesma justificativa —
o que sugere que, se um dia forem 5, o que estará faltando não é uma exceção a mais e sim
um gerador de mapeadores.

### O efeito colateral no degrau seguinte

Extrair para caber em 40 arrastou o resto da distribuição junto — os auxiliares novos nascem
pequenos, e a função de origem encolhe:

| Acima de | Antes | Depois |
|---|---|---|
| 40 | 32 | 0 (2 em exceção) |
| 35 | 73 | **52** |
| 30 | 117 | **103** |

A 123 herda 103, não 117. O degrau de 30 ficou 12% mais barato sem ninguém trabalhar nele —
que é o argumento a favor de descer por degraus em vez de tentar 50→30 de uma vez.

### O acidente do número reservado (dívida 18)

A dívida 18 (cálculo de prazo fatal das intimações) apontava para a **spec 122** desde a
101 — e a 122 virou o teto de linhas por função. Aberta a spec, a dívida passou a apontar
para uma spec concluída que não a resolve, exatamente o acidente do handoff 038→086 que a
própria entrada da dívida 18 descreve. Foi re-atribuída para a 124.

A lição vale de regra: o CLAUDE.md §8 manda rodar `grep -n "Spec-alvo" docs/DIVIDA-TECNICA.md`
ao **fechar** uma spec; falta mandar rodar ao **abrir**. Um número de spec pode já estar
reservado por uma dívida, e só o `grep` mostra isso. O meta-teste pegaria — mas só na hora
de fechar, com o trabalho já feito no número errado.

## 10. Definição de pronto

- [x] Recontagem registrada em §9 **antes** de qualquer edição
- [x] `TETO_DE_LINHAS = 40`, gate verde
- [x] Nenhuma função de `app/` acima de 40 linhas líquidas
- [x] No máximo 5 exceções, versionadas e justificadas
- [x] Auxiliares novos em inglês; docstrings em português
- [x] Nenhum teste anterior editado; contrato inalterado (311 caminhos, 384 operações)
- [x] `docs/GATES.md` com o valor novo
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 122 em ✅
- [x] Commit `refactor(122): teto de 40 linhas por função no backend`
