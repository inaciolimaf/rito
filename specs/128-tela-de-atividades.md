# 128 — Tela de Atividades

**Fase:** 12 · **Tipo:** feature · **Orçamento:** +3 s no wall-clock
**Depende de:** 007, 030, 032, 033, 036, 098 · **Status:** ✅ concluída

---

## 1. Objetivo

O item **Atividades** do menu lateral passa a levar a uma tela de verdade: a lista global
de tarefas do escritório, com filtros na URL, paginação keyset, seleção em massa e
exportação Excel/PDF. Até aqui ele levava a `/home` por contorno da spec 102 — a rota
apontava para `/posts` desde a 008 e a **tela nunca existiu**. Esta spec consome a
**dívida nº 26** do `DIVIDA-TECNICA.md`, cujo alvo era a 125 — número já gasto por outra
spec — e passa a ser este.

## 2. Por que a dívida 26 é diferente da 24

A 24 era uma rota faltando: a tela de configurações existia e ninguém a tinha ligado. Aqui
existe `PostDetailPage` (`/posts/:id`) e mais nada — a listagem de atividades nunca foi
especificada por nenhuma das 100 primeiras specs. A caixa de entrada da 036 (`/home`) é
parecida o bastante para o contorno funcionar e diferente o bastante para não ser
substituta: ela é **a minha fila**, agrupada em seções fixas, sem export nem período. A
tela de Atividades é **a lista do escritório**, com eixo de data escolhível e filtros
combináveis — é a `/customers` e a `/lawsuits` das tarefas.

## 3. Escopo

- `GET /api/v1/posts` — listagem global de atividades no contrato do `CLAUDE.md` §6
  (`{items, next_cursor, total}`, keyset, filtros combináveis), em **2 statements**;
- `POST /api/v1/posts/export` — xlsx/pdf respeitando os filtros ativos, teto de 50.000 linhas;
- `PostListPage` em `/posts`, reusando `ListPageLayout`/`FilterBar`/`DataTable`/`EmptyState`
  e os hooks `useListPage`/`useFilters`;
- o `<Navigate to="/home">` da 102 sai do `App.tsx` e dá lugar à rota real;
- o endpoint novo entra na tabela do gate de orçamento de queries com o número **3**.

## 4. Fora de escopo

- **Filtros por taxonomia do processo** (`steps_id`, `groups_id[]`, `type_lawsuits_id[]` do
  levantamento) — são filtros de processo dentro de uma tela de tarefa; entram quando
  alguém pedir, com os três `JOIN` que eles custam. Registrado na §9.
- **Ordenar por Tarefa, Partes e Responsável** (o levantamento cita cinco ordenações; esta
  spec entrega as duas de data mais `created_at`). Motivo técnico na §9.
- **Sub-visão "Pauta de audiência"** (`page` do levantamento) — é outra tela, com outro
  recorte (`show_in_schedule`), não um filtro desta.
- **Conclusão em massa nova**: a tela reusa `POST /posts/bulk/complete`, que a spec 036 já
  entregou. Nenhuma linha de backend de conclusão foi escrita aqui.
- **Nova jornada de e2e**: o teto de 25 do `CLAUDE.md` §3 está cheio; os casos viraram
  teste de integração.

## 5. Modelo de dados

Nenhuma migration. A tela lê `posts`, `post_users`, `task_types`, `lawsuits` e `users`,
todas com `tenant_id` e RLS desde as specs 027/031/032. Não há tabela nova, e por isso
também não há índice novo: a ordenação padrão cai em `posts(scheduled_date)` e o filtro de
visibilidade em `post_users(post_id)`, ambos já existentes.

## 6. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| GET | `/api/v1/posts` | `view`, `column`, `date_from`, `date_to`, `task_type_id`, `lawsuit_id`, `assignee_id`, `sender`, `priority`, `include_future`, `sort`, `order`, `cursor`, `limit` | `200 {items, next_cursor, total}` | COLABORADOR |
| POST | `/api/v1/posts/export` | `{format, filters}` | `200` xlsx/pdf | COLABORADOR |

`403` com `application/problem+json` para perfil abaixo de COLABORADOR. Não há `404`: a
listagem de um filtro sem resultado é `200` com `items: []`.

**Decisões de produto, e onde estão ancoradas.** O levantamento
(`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md`, §2.3 "Filtros de Atividades" e §4.3) descreve a
tela; o modelo (`posts/models.py`) diz o que existe de fato. Onde os dois divergem, vale o
modelo — campo que não existe não vira filtro.

- **Colunas:** Tarefa (nome do tipo) · Processo (número ou pasta) · Responsáveis · Data do
  compromisso · Prazo fatal · Status · prioridade (! importante/urgente). São as colunas da
  caixa de entrada do levantamento menos as que não cabem numa lista global (favorito e
  lida são **por usuário**, não da tarefa — regra 11 da 033).
- **Ordenação padrão:** `scheduled_date` **crescente**. O levantamento não declara a
  ordenação inicial; o `column` default dele é "Data do compromisso", e uma fila de
  pendências se lê pelo que vence primeiro. Tarefas sem data vão para o fim (§7, regra 6).
- **Filtros:** os do levantamento que existem no modelo — eixo de data (`column`) + período,
  tipo de tarefa, processo, responsável, remetente (`sender`), prioridade e futuras. A visão
  rápida (`view`) absorve o `completed` do levantamento (Pendentes/Concluídas) e acrescenta
  **Atrasadas**, que é o terceiro status colorido da agenda (§4.2 do levantamento).
- **`q` de busca livre não existe** na tela do levantamento e não foi inventado aqui.

## 7. Front-end

**Componentes reutilizados:** `ListPageLayout`, `FilterBar`, `DataTable` (seleção, ações em
massa, export e paginação), `EmptyState`, `ConfirmDialog`, e os hooks `useFilters` e
`useListPage`.
**Componentes criados:** **nenhum**. É o ponto da spec: a 40ª tela custa pouco. O único
arquivo de UI novo é a página, e ela é declaração de colunas + declaração de filtros.
`PriorityBadge` e `TaskFlags`, que a `PostDetailPage` já usava, entram como célula.
**Rotas:** `/posts` (`PostListPage`), preservando `/posts/:id` (`PostDetailPage`).
**Estados:** carregando (`DataTable isLoading`), vazio sem filtro (`EmptyState` com atalho
para a caixa de entrada), vazio com filtro (`emptyMessage` da tabela), erro (`DataTable
error`) e **sem permissão** (a ação em massa "Concluir selecionadas" não é renderizada para
COLABORADOR — regra 9 da 033 reserva ao ADMINISTRADOR fechar a linha de outro, e numa lista
global a seleção quase sempre pega linha de outro).

## 8. Regras de negócio

1. **Contrato de listagem.** `{items, next_cursor, total}`, keyset por `(valor, id)` em
   base64, nunca offset. `total` é o do filtro inteiro, não o da página.
2. **Privacidade é filtro de `WHERE`, não de pós-processamento.** Tarefa `is_private` de
   terceiro **não aparece** — nem para o GESTOR (regra 8 da 033). Diferente da lista de
   tarefas de um processo, aqui ela não aparece nem redigida: naquela tela a presença faz a
   contagem fechar; aqui, "existe uma tarefa privada em algum lugar do escritório" é
   informação sem uso e vazamento sem contrapartida. Mesmo recorte do `search` da 083.
3. **Futuras ocultas até a data** (regra 7 da 033), a menos que `include_future=true`.
4. **O período incide sobre o eixo escolhido.** `column` ∈ compromisso · prazo fatal ·
   criação · conclusão; `date_from`/`date_to` são um intervalo aberto dos dois lados.
   Conclusão é data de linha (`post_users.completed_at`), então filtra por `EXISTS`.
5. **Visões rápidas:** `pending` (padrão), `completed`, `overdue`, `all`. "Concluída" é
   **todas** as linhas concluídas (regra 3 da 033); "atrasada" é pendente com
   `coalesce(prazo fatal, compromisso)` no passado.
6. **Data nula ordena no fim**, nas duas direções.
7. **Export respeita o filtro ativo**, não a página visível; teto de 50.000 linhas.
8. **RLS garante o tenant.** Nenhum `WHERE tenant_id` na aplicação (§4 do `CLAUDE.md`).
9. **A listagem cabe em 3 queries** — autenticação + página (com o `total` por janela) +
   rótulos das linhas escolhidas. É gate de CI (§11 do `CLAUDE.md`).
10. **Status derivado, nunca persistido:** CONCLUIDA · ATRASADA · PENDENTE, calculados a
    partir das linhas de conclusão e do dia do escritório (`Clock`).

## 9. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | contrato `{items,next_cursor,total}` + colunas da linha | `tests/integration/test_posts.py` | ~0,4 s |
| integração | keyset: 2 páginas sem repetir nem pular, e sem data no fim | `tests/integration/test_posts.py` | ~0,5 s |
| integração | visões `pending`/`completed`/`overdue` | `tests/integration/test_posts.py` | ~0,5 s |
| integração | eixo de data + período (compromisso, prazo, conclusão) | `tests/integration/test_posts.py` | ~0,4 s |
| integração | `sender`, `assignee_id`, `priority`, `task_type_id` | `tests/integration/test_posts.py` | ~0,4 s |
| integração | futura oculta; `include_future` mostra | `tests/integration/test_posts.py` | ~0,3 s |
| integração | **privada de terceiro não aparece, nem para o GESTOR** | `tests/integration/test_posts.py` | ~0,4 s |
| integração | export xlsx/pdf respeita o filtro | `tests/integration/test_posts.py` | ~0,5 s |
| RLS | tenant A não enxerga atividade de tenant B | `tests/integration/test_posts.py` | ~0,3 s |
| gate | `GET /api/v1/posts` em 3 queries | `tests/integration/test_query_budget.py` | ~0,2 s |
| frontend | renderiza colunas e status | `src/features/posts/PostListPage.test.tsx` | ~0,3 s |
| frontend | filtro vai para a URL e volta dela | `src/features/posts/PostListPage.test.tsx` | ~0,3 s |
| frontend | paginação avança e volta pelo cursor | `src/features/posts/PostListPage.test.tsx` | ~0,3 s |
| frontend | vazio sem filtro mostra `EmptyState`; COLABORADOR não vê a ação em massa | `src/features/posts/PostListPage.test.tsx` | ~0,3 s |

**Total estimado:** +3 s
**Fixtures externas:** nenhuma. A tela não toca rede externa.

## 10. Descobertas

- **Keyset sobre coluna anulável não é keyset.** `scheduled_date` e `deadline_date` são
  `NULL` com frequência, e o predicado do cursor compara `(valor, id)` como TUPLA: com
  `NULL` do lado esquerdo a comparação inteira é `NULL`, e a linha **some da segunda página
  em diante**. O `coalesce` com o extremo do calendário (`date.max` no crescente,
  `date.min` no decrescente) resolve ordenação e cursor de uma vez — é o que permite
  entregar a ordenação por prazo fatal sem tocar em `core/listing.py`.
- **Ordenar por Tarefa, Partes ou Responsável fica fora, e não por preguiça.** As três
  ordenam por um valor que não está em `posts`: nome do tipo (outra tabela), partes
  (agregado de duas) e responsáveis (N:M — uma tarefa com três responsáveis não tem *um*
  valor de ordenação). Keyset sobre valor agregado exige materializar o valor antes de
  paginar; feito errado, vira offset disfarçado. Dívida nomeada: **ordenação por rótulo na
  listagem de atividades**.
- **Os filtros por taxonomia do processo** (`steps_id`, `groups_id[]`,
  `type_lawsuits_id[]`) custam três `JOIN` na query da página, que hoje só lê `posts`. É a
  metade cara do levantamento e a menos usada numa tela de tarefa — a pergunta "quais
  tarefas da fase Recursal" se responde melhor pelo CRM. Dívida nomeada: **filtros de
  taxonomia na listagem de atividades**.
- **A conclusão em massa já existia** (`POST /posts/bulk/complete`, spec 036) e é do
  domínio `inbox`. A tela nova consome o endpoint tal como está: uma feature que precisa da
  ação de outra não copia o caso de uso, chama.
- **`count(*) OVER ()` e `DISTINCT` não convivem.** Todo filtro que atravessa `post_users`
  (responsável, remetente, conclusão, visão) foi escrito como `EXISTS` correlacionado e
  não como `JOIN`: com `JOIN` seria preciso `DISTINCT`, e o total por janela passaria a
  contar linha de junção em vez de tarefa. É o mesmo motivo do `EXISTS` das partes na
  listagem de processos (027) — mas ali o argumento era duplicata visível, aqui é um
  `total` silenciosamente errado.
- **O número 128, e não 125.** O `DIVIDA-TECNICA.md` reservava a 125 para as dívidas 25 e
  26. A 127 já registrou que número de spec é recurso disputado; a 128 é o número livre no
  momento em que esta abriu, e o `DIVIDA-TECNICA.md` precisa da re-atribuição
  (`~~125~~ → 128`) para a dívida 26.

## 11. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] Nenhuma tabela nova; isolamento por tenant testado mesmo assim
- [x] Testes da spec verdes (backend `test_posts.py` + `test_query_budget.py`, frontend `src/features/posts`)
- [x] `GET /api/v1/posts` dentro do orçamento de 3 queries
- [x] Sem `Any`, `as any` ou `# type: ignore` sem justificativa em comentário
- [x] Nenhum componente novo — os sete da 007 deram conta (regra dos 3 usos)
- [ ] `ROADMAP.md` atualizado para ✅ *(texto no relatório: arquivo compartilhado, editado fora do ciclo)*
- [ ] Commit `feat(128): tela de atividades`
