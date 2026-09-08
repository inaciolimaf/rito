# 125 — `last_assigned_at` calculado

**Fase:** 12 · **Tipo:** correção · **Orçamento:** +1,3 s
**Depende de:** 031, 032, 098 · **Status:** ✅ concluída

---

## 1. Objetivo

A coluna "Última atribuição" da tela de tarefas (`/settings/task-types`) passa a mostrar
quando cada tipo do catálogo foi atribuído a alguém pela última vez. Hoje ela mostra `—`
para os 152 tipos de todos os escritórios, sempre, porque o `router.py` devolve
`last_assigned_at=None` **literal** desde a spec 031 — com um comentário dizendo que
tarefas ainda não existiam. Elas existem desde a 032, há 93 specs. Esta é a dívida 25.

## 2. Por que isso é pior do que não ter o campo

O contrato mente, e mente de um jeito que o consumidor não consegue detectar. `null` no
front tem duas leituras possíveis — "nunca atribuído" e "não calculado" — e nada na
resposta as separa. O `TaskTypesListPage` renderiza `—` para as duas, então a tela não
está incompleta: está **errada com aparência de completa**, que é o estado do qual ninguém
reclama e ninguém corrige.

Uma coluna ausente seria uma pergunta aberta ("cadê a última atribuição?"). Uma coluna
constante é uma resposta fechada e falsa. O campo é o exemplo de manual de por que stub em
contrato de API é pior que buraco em contrato de API — e é por isso que a alternativa
**remover o campo** foi considerada e recusada: a spec 031 §6 lista a coluna no desenho da
tela, o front a renderiza e o dado existe. Não havia decisão de produto pendente; havia uma
conta que ninguém tinha feito.

## 3. Escopo

- `TaskTypeRepository` ganha a derivada: `list_with_last_assigned` (o catálogo com a data
  de cada linha, numa consulta só) e `last_assigned_at` (a mesma conta para um tipo só).
- `TaskTypeService` expõe as duas; `router.py` deixa de escrever a constante e passa a
  receber o valor pronto.
- As respostas de **listagem**, **POST** e **PUT** passam a concordar entre si.
- Teste de orçamento de queries da listagem, dentro do próprio arquivo do domínio.

## 4. Fora de escopo

- **Carimbo de tempo na atribuição.** `post_users` não guarda quando a linha nasceu, e é
  por isso que a derivada usa `posts.created_at` (§7, regra 2). Registrar o instante da
  atribuição é migration em `post_users` + retrofit do histórico; entra como dívida se
  alguém precisar distinguir "atribuído" de "criado" (§9).
- **Invalidar o cache do catálogo quando uma tarefa é criada.** O acoplamento seria de
  `posts` para a chave de `task_types`, na direção errada; o TTL de 5 minutos continua
  sendo o teto do atraso (§9).
- **Ordenar ou filtrar a listagem por `last_assigned_at`.** A coluna é exibição; ordenação
  por ela exigiria keyset sobre um valor derivado, que é outra spec.
- **A listagem de atividades** (dívida 26), que a 128 entregou.

> Fora de escopo é vinculante. Se durante a implementação surgir algo daqui,
> anote em `## 9. Descobertas` e siga — não implemente.

## 5. Modelo de dados

Nenhuma migration. A regra 9 da spec 031 diz "derivada, **nunca armazenada**", e a spec a
cumpre ao pé da letra: nenhuma coluna nova, nenhum contador desnormalizado a manter em
sincronia. O índice de que a consulta precisa já existe — `ix_posts_task_type_id`, criado
na 098 junto das outras 93 FKs sem índice.

## 6. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| GET | `/api/v1/task-types` | `step_id`, `status`, `q` | `200 {items: [{…, last_assigned_at}], total}` | autenticado |
| POST | `/api/v1/task-types` | corpo do tipo | `201 {…, last_assigned_at}` | GESTOR |
| PUT | `/api/v1/task-types/{id}` | corpo do tipo | `200 {…, last_assigned_at}` | GESTOR |

**O formato não muda** — `last_assigned_at` continua `datetime | null` em ISO 8601, e
nenhum campo entra ou sai. O que muda é que o valor passa a ser verdade. Nenhum cliente
precisa de alteração para continuar funcionando; o front precisa de zero linhas para
começar a mostrar o dado certo, porque a célula já sabia formatar a data que nunca chegava.

## 7. Front-end

**Componentes reutilizados:** `DataTable`, `FilterBar`, `FormModal` — nada muda.
**Componentes criados:** nenhum.
**Rotas:** `/settings/task-types` (inalterada).
**Estados:** a célula já tratava os dois casos (`data` ou `—`); com o cálculo, o `—` passa
a significar só "nunca atribuído".

Sobra um comentário desatualizado em `TaskTypesListPage.tsx:161` («Regra 9: derivada —
tarefas só existem na spec 032»), que descreve o motivo de um `null` que não existe mais.
É uma linha de comentário, sem efeito em runtime, e o arquivo está fora dos arquivos desta
entrega (§9).

## 8. Regras de negócio

1. **`last_assigned_at` é derivado, nunca armazenado** (regra 9 da 031, cumprida ao pé da
   letra): nenhuma coluna, nenhum gatilho, nenhum contador. A conta é
   `MAX(posts.created_at)` entre as tarefas do tipo que têm ao menos um responsável.
2. **A data é a da criação da tarefa.** `post_users` — que é a linha de atribuição — não
   guarda instante nenhum, só conclusão e pontos. O único carimbo existente é o do post, e
   ele responde a pergunta porque toda tarefa nasce com ao menos um responsável
   (`resolve_assignees`, regra 1 da 032): criar e atribuir são o mesmo instante.
3. **`null` significa "nunca atribuído", e só isso.** É a regra que a dívida 25 pedia: o
   consumidor passa a poder confiar na ausência de valor.
4. **Listagem, POST e PUT respondem pelo mesmo caminho.** Uma função de repositório, dois
   chamadores. Foi a existência de duas respostas (uma calculada, outra constante) que
   produziu a dívida.
5. **A conta mora no repositório.** Router não faz query (CLAUDE.md §5), e o gate
   `tests/meta/test_camadas.py` reprova quem tentar.
6. **A listagem continua em 3 statements.** A derivada entra como subquery correlacionada
   na consulta que já existia — não como uma consulta por linha (CLAUDE.md §11).
7. **Ninguém filtra tenant no `WHERE`.** O `MAX` percorre `posts`, que tem RLS por
   `tenant_id`; quem escopa é a política (CLAUDE.md §4).

## 9. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | tipo nunca atribuído devolve `null`; atribuir muda só ele | `tests/integration/test_task_types.py` | ~0,33 s |
| integração | é um `MAX` (a mais recente vence) e o PUT concorda com a listagem; POST de tipo novo devolve `null` | `tests/integration/test_task_types.py` | ~0,21 s |
| orçamento | a listagem cabe em 3 queries com 3 tipos e 3 tarefas | `tests/integration/test_task_types.py` | ~0,24 s |
| RLS | a data do escritório vizinho, criada DEPOIS, não aparece aqui | `tests/integration/test_task_types.py` | ~0,46 s |

**Total estimado:** +1,3 s (arquivo inteiro: 3,3 s, 10 testes)
**Fixtures externas:** nenhuma. Nada aqui toca a rede.

Os testes anteriores do arquivo passam **sem edição** — o contrato não mudou de forma, só
de valor. `tests/integration/test_query_budget.py` roda junto e continua verde.

## 10. Descobertas

- **O gate mediria o Redis, não a consulta.** A chamada SEM filtro é cacheada (spec 098,
  regra 9), então um orçamento medido por ali daria **1** query — só a autenticação — e um
  N+1 introduzido amanhã passaria batido. O teste de orçamento e os dois de valor usam o
  caminho **filtrado** (`?status=active`), que não passa pelo cache, de propósito e com o
  motivo escrito ao lado. É o mesmo risco de gate que só parece funcionar da dívida 29.

- **A derivada envelhece no cache, e o TTL é o teto disso.** O payload cacheado agora
  carrega um valor que muda com a criação de **tarefa**, e a invalidação por evento só
  dispara em escrita de **catálogo** — criar uma tarefa não derruba a chave. Considerado e
  recusado: chamar `invalidate_catalog` do serviço de posts acopla `posts` à chave de cache
  de `task_types` na direção errada. O contrato escrito em `core/cache.py` já cobre o caso
  ("o TTL é o limite superior do erro"): a coluna é informativa, nenhuma decisão do sistema
  depende dela, e cinco minutos de atraso numa data que muda algumas vezes por dia não é
  um erro visível. Registrado em comentário no ponto exato do cache.

- **`resolve_assignees` é o que torna `posts.created_at` uma resposta honesta.** Os quatro
  caminhos que criam post no backend (`creation.py`, `recurrence_service.py`,
  `publications/routing.py`, `workflows/service.py`) passam todos por
  `create_with_assignees` com ao menos um id — verificado, não suposto. Sem essa
  invariante, "criado" e "atribuído" seriam coisas diferentes e a conta estaria errada.

- **O `JOIN` com `post_users` não muda o resultado hoje — e fica.** Justamente porque toda
  tarefa nasce atribuída, a consulta daria o mesmo número sem ele. O que ele muda é o que a
  consulta **afirma**: "atribuído a alguém" passa a estar escrito na consulta em vez de
  depender de uma invariante que vive em outro arquivo. No dia em que uma tarefa puder
  existir sem dono, a resposta continua certa sem ninguém precisar se lembrar daqui.

- **A troca de responsável não conta como nova atribuição.** `replace_assignees` (PUT de
  tarefa) apaga e recria as linhas de `post_users` sem mexer em `posts.created_at`, então
  reatribuir uma tarefa de três meses atrás para outra pessoa não move a data. É a leitura
  menos surpreendente das duas — a coluna responde "quando este tipo de trabalho foi
  distribuído pela última vez", não "quando alguém mexeu na tarefa" —, mas é uma escolha, e
  fica declarada. Corrigi-la exige `created_at` em `post_users`: migration + retrofit de
  histórico, fora do escopo (§4).

- **O POST paga uma query para não recriar a dívida.** Um tipo recém-criado provavelmente
  não tem tarefa nenhuma, e escrever `None` ali seria correto — e seria também exatamente a
  linha que esta spec veio apagar, de volta, com um argumento melhor. A resposta pergunta em
  vez de afirmar: uma fonte de verdade só, e um `POST` não disputa orçamento com listagem
  nenhuma (o orçamento do §11 do CLAUDE.md é sobre leitura).

- **`list_filtered` continuou existindo.** `publications/analysis.py::_suggest_task_type`
  lê o catálogo para casar o ato do DJEN com um tipo e não usa a derivada. Em vez de mudar o
  retorno de todo mundo, os filtros saíram para `_filtered_stmt` e há dois métodos sobre
  ele: quem quer a data pede a data, quem não quer não paga a subquery.

- **O gate morde.** Baixado o orçamento para 2, o teste falha listando as três queries
  (usuário do token, catálogo com a subquery, catálogo de fases) — conferido antes de fixar
  em 3. Um teste de orçamento que nunca se viu falhar não é um gate, é decoração.

## 11. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] Nenhuma tabela nova; o teste de isolamento por tenant cobre a derivada (regra 7)
- [x] Testes do domínio verdes (10/10) e `test_query_budget.py` verde (13/13)
- [x] `ruff`, `black` e `mypy` verdes nos arquivos da spec
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Nenhum componente novo — a regra dos 3 usos não foi acionada
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `fix(125): last_assigned_at calculado`
