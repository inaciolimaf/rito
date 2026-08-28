# 121 — Teto de 30 linhas por função

**Fase:** 12 · **Tipo:** refatoração · **Orçamento:** +0,3 s
**Depende de:** 106, 109, 111, 112, 119, 120 · **Status:** ⬜ pendente

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

Preencher durante a implementação. **Obrigatório:** a recontagem feita depois de 106, 109, 111,
112 e 119 — quantas das 134 e das 225 já estavam resolvidas.

## 13. Definição de pronto

- [ ] Recontagem registrada em §12 **antes** de qualquer edição
- [ ] `tests/meta/test_tamanho_de_funcao.py` com contagem líquida por AST
- [ ] `max-lines-per-function` em 30 no `eslint.config.js`, com `skipBlankLines`/`skipComments`
- [ ] Backend e frontend abaixo do teto
- [ ] No máximo 5 exceções, versionadas e justificadas
- [ ] Subcomponentes novos em `features/`, não em `components/domain/`
- [ ] Nenhum teste anterior editado
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 121 em ✅
- [ ] Commit `refactor(121): teto de 30 linhas por função`

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
