# 121 — Teto de 30 linhas por função

**Fase:** 12 · **Tipo:** refatoração · **Orçamento:** +0,3 s
**Depende de:** 106, 109, 111, 112, 119, 120 · **Status:** ✅ concluída (degrau 1: teto 50, backend)

---

## 1. Objetivo

Ligar um teto de **30 linhas de corpo por função**, nas duas linguagens, e trazer o que
estiver acima para dentro dele. É o último gate estrutural da série: a 106 mediu caminhos, a
109 mediu volume em statements, a 111 mediu ramificação, a 112 mediu saídas — esta mede o que
um revisor enxerga sem rolar a tela.

> Refatoração: nenhuma mudança de comportamento. Nenhuma tela muda, nenhuma rota muda de
> forma, nenhum teste anterior é editado.

## 2. Por que esta spec vem por último

Ela depende de cinco anteriores por um motivo prático: **a maior parte do trabalho já vai
estar feita quando ela começar**. As mesmas funções aparecem nos inventários da 106
(complexidade), 109 (statements) e 111 (ramos), e a 119 quebra as páginas gigantes do frontend
ao extrair o `<CrudListPage>`. Recontar antes de mexer é a primeira tarefa, não uma
formalidade.

## 3. Como contar — a decisão que define se o gate é bom ou tóxico

Contar linhas brutas de uma função pune documentação. Este projeto tem densidade de comentário
deliberada: as justificativas dentro do código são metade do valor dele, e um gate que
incentive apagá-las é pior que gate nenhum.

A diferença é grande o suficiente para ser a decisão central da spec. Medido em 28/08/2026,
commit `44469bd`, sobre 2.259 funções de `backend/app`:

| Forma de contar | Funções acima de 30 |
|---|---|
| bruto — decorador + assinatura + docstring + corpo | 224 (9,9%) |
| **líquido — só o corpo, sem docstring** | **134 (5,9%)** |

Noventa funções passam de 30 apenas por assinatura multilinha e docstring. **A contagem é
líquida**: do primeiro statement executável ao último, docstring fora, decoradores fora,
assinatura fora. No frontend, o equivalente já existe pronto: `skipBlankLines` e
`skipComments` da própria regra do ESLint.

## 4. Inventário

### Backend — 134 funções, contagem líquida

Ruff **não tem** regra de tamanho de função em linhas (`PLR0915` conta statements, que é outra
coisa). O gate é meta-teste por AST, no formato das 13 meta-suítes que já existem.

Distribuição por módulo:

| Módulo | Acima de 30 |
|---|---|
| `domain/lawsuits` | 19 |
| `domain/ai` | 15 |
| `ai/tools` | 10 |
| `domain/financial` | 8 |
| `domain/reports` | 7 |
| `domain/bi` | 7 |
| `domain/documents` | 6 |
| `domain/automations` | 6 |
| `domain/publications` | 5 |
| demais | 51 |

As maiores (bruto, para comparar com o inventário da 106):

```
189  domain/reports/tabular_service.py:81   fetch
121  integrations/http/client.py:118        _request_com_resiliencia
113  domain/automations/engine.py:171       advance
108  domain/automations/decision.py:211     _ask
106  core/provisioning.py:82                provision_tenant
 99  ai/graphs/base_agent.py:84             build
 95  domain/ai/service.py:171               run
 89  main.py:149                            create_app
 87  domain/lawsuits/listing.py:336         list_filtered
 79  ai/runtime.py:149                      _drive_iter
```

Seis das dez já são alvo da 106 ou da 109. `provision_tenant`, `list_filtered`, `_ask` e
`build` são as que só esta spec pega — complexidade baixa, volume alto, sequência linear
longa.

### Frontend — 225 funções

Medido com `max-lines-per-function` em 30, `skipBlankLines` e `skipComments` ligados, sobre
`src/` sem testes. Maiores: 336, 323, 300, 289, 249, 240, 214, 209, 204, 199 linhas.
Concentração: **199 em `features/`**, 23 em `components/`.

Quase todas são componentes de página — a função que o React chama para renderizar a tela
inteira. A 119 já ataca a maior fatia disso ao extrair `<CrudListPage>`; o que sobrar são
telas grandes de verdade (`LawsuitsPage`, `TransactionsListPage`, `CustomerListPage`), onde a
correção é extrair subcomponentes, não achatar JSX.

## 5. Escopo

**A.** `tests/meta/test_tamanho_de_funcao.py` — contagem líquida por AST, teto 30, lista de
exceção versionada.

**B.** `max-lines-per-function` no `eslint.config.js`, com `max: 30`, `skipBlankLines: true`,
`skipComments: true`.

**C.** As funções acima do teto nas duas linguagens, depois da recontagem da §2.

**D.** Exceções versionadas, com justificativa, limitadas pela regra 5.

## 6. Fora de escopo

- Baixar de 30. Se um dia fizer sentido, é spec própria com nova medição.
- Teto de linhas por **arquivo**. Correlaciona, mas é outra métrica e outra conversa — hoje
  são 11 arquivos de frontend acima de 300 linhas.
- Extrair componentes que a 119 já vai extrair. Se a 119 ainda não fechou, esta spec espera.
- Mudar comportamento de qualquer tela ou endpoint.

## 7. O que este gate vê e o que ele não vê

**Vê:** linhas de corpo, contagem exata, teto configurável, mesma resposta toda vez. Gate
programático puro.

**Não vê:** se as 30 linhas fazem uma coisa ou quatro. Uma função pode caber folgada no teto e
ainda misturar validação, persistência e formatação — isso é SRP, e SRP não tem gate (ver
spec 118, §2). O teto reduz o custo de revisar; ele não revisa.

## 8. Modelo de dados / Contratos de API

Nada. Nenhuma rota muda de forma, status ou resposta.

## 9. Front-end

**Componentes reutilizados:** todos os de `components/domain/`, incluindo o `<CrudListPage>`
que a 119 entrega.

**Componentes criados:** subcomponentes locais extraídos das telas grandes — cabeçalho de
filtro, painel lateral, bloco de resumo. Ficam **em `features/`, junto da tela**, não em
`components/domain/`: a regra dos 3 usos do §6 só promove o que apareceu três vezes, e
extrair por tamanho não é o mesmo que extrair por reuso. Promover cedo demais cria design
system de uma coisa só.

**Estados:** loading, vazio, erro e sem permissão inalterados.

## 10. Regras de negócio

1. Nenhuma função de `app/` passa de 30 linhas líquidas de corpo.
2. Nenhuma função de `frontend/src/` passa de 30 linhas, ignorando linhas em branco e
   comentários.
3. A contagem do backend exclui docstring, decoradores e assinatura. Um gate que faz alguém
   apagar comentário para passar está errado, e este projeto perderia mais que ganharia.
4. Toda função extraída no backend é privada (`_nome`) e tipada; `mypy --strict` continua
   verde sem exceção nova.
5. Exceções versionadas nas duas linguagens, teto de **5 no total**, cada uma com
   justificativa. Se a implementação precisar da sexta, o teto de 30 está errado para este
   código e a spec não fecha — essa conclusão vale mais que forçar o número.
6. Nenhum teste anterior é editado. No frontend, as consultas por `getByRole`/`getByLabel`
   continuam encontrando os mesmos elementos depois da extração — é isso que prova que a
   árvore de acessibilidade não mudou.

## 11. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | nenhuma função de `app/` acima de 30 linhas líquidas (AST) | `tests/meta/test_tamanho_de_funcao.py` | ~0,2 s |
| meta | no máximo 5 exceções no projeto, todas justificadas | `tests/meta/test_tamanho_de_funcao.py` | ~0,1 s |
| — | os testes das telas e endpoints tocados passam **sem edição** | — | — |

**Total estimado:** +0,3 s. O gate do frontend é o `make lint`, que já roda em todo PR.

## 12. Descobertas

### A recontagem — feita ANTES de qualquer edição, como a §13 exige

| Teto | Backend (estimado na spec) | Backend (medido) | Frontend (estimado) | Frontend (medido) |
|---|---|---|---|---|
| 30 | 134 | **118** | 225 | **228** |
| 40 | — | 43 | — | 177 |
| 50 | ~47 | **20** | — | **141** |

As cinco specs anteriores adiantaram menos do que a §2 esperava no backend (118 contra 134) e
**nada** no frontend (228 contra 225) — o que faz sentido: 106, 109, 111 e 112 são todas
gates de Python, e a 119 extraiu o `<CrudListPage>` de seis páginas de taxonomia, que não
são as gigantes.

**346 funções.** É, de longe, o maior volume de qualquer spec da série — a segunda maior é a
116, com 15.

### O escopo foi cortado, e o corte foi decisão do usuário

Levada a medição, a decisão foi **só o backend**. O frontend fica para spec própria: as 141
acima de 50 são componentes de página, onde a correção é extrair subcomponente com decisão
de desenho — não é o mesmo trabalho que extrair um bloco de função Python, e misturar os
dois num ciclo produziria extração apressada justamente onde ela é mais arriscada.

Dentro do backend, o corte é o que a **Nota de execução desta spec** já previa: degraus, cada
um deixando o gate ligado e verde. Este é o **degrau 1, teto 50**.

### 29 funções reestruturadas, e o padrão que apareceu

De 20 acima de 50 para **zero**. Foram 29 extrações porque várias funções precisaram de mais
de um corte — e porque cada extração empurra a próxima medição.

O padrão dominante não foi «função complexa demais»: essas já tinham caído na 106. Foi
**sequência linear longa** — a função que faz sete coisas em ordem, cada uma simples:

- `provision_tenant` (126 linhas, a maior do backend) eram **sete blocos de INSERT** quase
  idênticos. Viraram sete `_seed_*`, e a função passou a ser a lista do que um escritório
  novo ganha, legível de uma vez.
- `lifespan` (56) era «configurar processo, migrar, instrumentar» — três assuntos.
- `parse_communication` (56) era o cabeçalho da intimação mais dois laços de desdobramento.
- `_to_response` (69) eram **duas respostas inteiras** no mesmo corpo: a normal e a redigida
  da regra 8. Separá-las tornou visível que a segunda é toda de valores neutros.

Onde a função era mesmo um fluxo (`_request_with_resilience`, `_ask`), o corte que funcionou
foi o mesmo da 106: **um objeto para o que viaja junto**. `_Call` (a requisição),
`_Attempt` (a tentativa), `_Spent` (o consumo da conversa). Sem eles, o laço de retry
precisaria de onze parâmetros e bateria no `max-args` da 116 — os gates se cobram.

### Duas coisas que deram errado e o que ensinaram

**Mudei a ordem de duas guardas em `generate_next` sem perceber.** Ao extrair
`_template_if_running`, movi a checagem do limite de ocorrências para ANTES da busca do
modelo. Com o modelo ausente e o limite atingido, o original não desativava a série e a
minha versão desativava. Os 30 testes passaram — o caso não é coberto. Vi relendo o diff, e
restaurei a ordem com um comentário explicando por que ela é essa.

É o risco específico desta spec: extrair guardas parece mecânico e **a ordem delas é
comportamento**.

**O `black` desfaz compactação.** Três vezes tentei baixar uma função reescrevendo chamadas
em menos linhas, e três vezes o formatador reexpandiu — uma delas deixou a função MAIOR
(59 → 62). Compactar não é extrair. O que funciona é tirar um bloco com nome; o resto é
briga com a ferramenta.

### O gate: por que 50 é ratchet e não decoração

Zero funções acima de 50 hoje. Como o `max-branches = 8` da 111, o teto é o **máximo atual**:
custa zero agora e impede regressão. E a distribuição do que falta está medida, para os
degraus seguintes não precisarem redescobri-la:

| Teto | Funções acima |
|---|---|
| 45 | 16 |
| 40 | 32 |
| 35 | 73 |
| 30 | 117 |

### A contagem líquida foi a decisão certa, e dá para provar

A §3 escolheu contar líquido (sem docstring, decorador e assinatura) para o gate não punir
documentação. Confirmado na prática: das 29 funções que trabalhei, **nenhuma** foi resolvida
apagando comentário, e várias GANHARAM docstring no processo — a função extraída precisa
explicar o que é, e isso não conta contra ela.

Um gate bruto teria criado o incentivo oposto no arquivo mais documentado do projeto.

## 13. Definição de pronto

- [x] Recontagem registrada em §12 **antes** de qualquer edição
- [x] `tests/meta/test_tamanho_de_funcao.py` com contagem líquida por AST, provado mordendo
- [x] **Backend abaixo do teto de 50** — 29 funções reestruturadas, de 20 acima para zero
- [x] **Zero exceções** (teto era 5): nenhuma função precisou de uma para caber em 50
- [x] Nenhum teste anterior editado; nenhum contrato de API alterado (311 caminhos, 384
      operações)
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde — repositório inteiro
- [x] `docs/GATES.md` atualizado (exigência da 120)
- [x] `ROADMAP.md` com a linha da 121 em ✅
- [x] Commit `refactor(121): teto de 50 linhas por função no backend`

**Não entregue, e registrado como spec própria:**

- [ ] `max-lines-per-function` no `eslint.config.js` e as **228** funções do frontend — o
      usuário cortou o escopo para o backend. Vira a **spec 122**.
- [ ] Descer o teto de 50 para 40 e depois para 30 — **121b** e **121c**, com a
      distribuição já medida na §12.

---

## Nota de execução

134 + 225 funções é, de longe, o maior volume de qualquer spec desta série — e o número real
só é conhecido depois da recontagem. Se não fechar, o corte é por teto decrescente, cada passo
deixando o gate ligado e verde:

| Corte | Teto | Efeito esperado no backend |
|---|---|---|
| 121 | 50 linhas | ~47 funções |
| 121b | 40 linhas | +62 |
| 121c | 30 linhas | +115 |

Descer em três passos entrega gate funcionando em todos eles. Uma spec grande que não fecha
deixa o teto inexistente por mais um ciclo, que é o pior dos resultados.
