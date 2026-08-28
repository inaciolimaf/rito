# 051 — CRM: board Kanban

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +7 s
**Depende de:** 027, 007 · **Status:** ✅ concluída

---

## 1. Objetivo

Visão de funil: processos como cards, colunas por fase, arrastar para avançar. É a tela do
sócio que quer ver onde o dinheiro está parado.

## 2. Escopo

- `KanbanBoard` genérico e reutilizável
- Colunas pelas 9 fases
- Drag & drop com persistência otimista
- Card com partes, tipo, valor, responsável, tempo na etapa
- Virtualização para volume
- Ação em massa "alterar fase"

## 3. Fora de escopo

- Estagnação e métricas → 052 · Workflow ao mover → 053

## 4. Modelo de dados

```sql
CREATE TABLE lawsuit_stage_history (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  from_stage_id UUID REFERENCES stages(id),
  to_stage_id UUID NOT NULL REFERENCES stages(id),
  changed_by UUID NOT NULL REFERENCES users(id),
  changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_stage_history ON lawsuit_stage_history (lawsuit_id, changed_at DESC);

ALTER TABLE lawsuits ADD COLUMN stage_entered_at TIMESTAMPTZ NOT NULL DEFAULT now();
```
Migration `051_stage_history.py`. `stage_entered_at` é atualizada por trigger — é a base do
tempo na etapa (052) e do BI de tempo (076).

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/crm/board?<mesmos filtros de /lawsuits>&limit_per_column=50` |
| POST | `/api/v1/lawsuits/{id}/move-stage` → `{stage_id}` |
| POST | `/api/v1/lawsuits/bulk/move-stage` → `{lawsuit_ids[], stage_id}` |
| GET | `/api/v1/crm/board/column/{step_id}?cursor=` — paginação da coluna |

## 6. Front-end

**Reutiliza:** `FilterBar`, `EmptyState`, `ConfirmDialog`
**Cria:** `KanbanBoard<T>` (genérico), `KanbanColumn`, `KanbanCard`, `LawsuitCard`, `CrmPage`
**Rota:** `/crm`

`KanbanBoard` é genérico de propósito — recebe colunas, itens, `onMove` e um render de card.
Não conhece processo.

## 7. Regras de negócio

1. Colunas são as **9 fases**, sempre todas visíveis, mesmo vazias.
2. Card exibe: partes (2 + contador), tipo de ação, valor da causa, responsável, tempo na etapa.
3. Arrastar entre colunas move para a **primeira etapa** da fase destino, por `position`.
4. Movimento é otimista: a UI atualiza na hora e reverte se a API falhar.
5. Toda mudança de etapa grava em `lawsuit_stage_history` — inclusive as feitas fora do Kanban.
6. `stage_entered_at` é atualizado por trigger a cada mudança.
7. Coluna carrega 50 cards e pagina por scroll; o contador mostra o total real.
8. Filtros do CRM são os mesmos de `/lawsuits` — mesmo `ListQueryBuilder`.
9. Ação em massa é transacional.
10. Colaborador move só processos onde é responsável; ADMINISTRADOR move qualquer um.
11. Board com mais de 2.000 cards no total sugere refinar o filtro, em vez de renderizar tudo.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | board retorna 9 colunas, inclusive vazias | ~0,4 s |
| integração | mover grava histórico | ~0,4 s |
| integração | mover vai para a primeira etapa da fase | ~0,3 s |
| integração | trigger atualiza `stage_entered_at` | ~0,3 s |
| integração | mudança fora do Kanban também grava histórico | ~0,3 s |
| integração | Colaborador não move processo alheio → 403 | ~0,3 s |
| integração | ação em massa é transacional | ~0,4 s |
| integração | paginação por coluna | ~0,4 s |
| integração | **budget: board ≤ 3 statements** | ~0,4 s |
| frontend | `KanbanBoard` genérico com dados falsos | ~0,5 s |
| frontend | drag & drop chama `onMove` | ~0,5 s |
| frontend | falha da API reverte a UI | ~0,4 s |
| e2e | **jornada 8/25:** arrastar card e ver a fase mudar | ~4 s |

**Total:** ~8,6 s

## 9. Descobertas

- **"Primeira etapa da fase" (regra 3) é resolvida no FRONTEND, não no backend.** O
  contrato `POST /lawsuits/{id}/move-stage → {stage_id}` já pedia um `stage_id` exato, não
  um `step_id` — o backend não tem (nem precisa ter) lógica de "qual é a primeira etapa de
  uma fase"; a UI busca `GET /stages` (já ordenado por `position`, spec 015) e resolve a
  etapa de destino antes de chamar a API. O teste de integração
  `test_mover_para_primeira_etapa_da_fase` prova as duas metades: a ordenação por
  `position` existe, e mover para o id resolvido funciona ponta a ponta.
- **`stage_entered_at` por trigger, `lawsuit_stage_history` pela aplicação.** Uma trigger de
  banco não sabe QUEM fez a mudança (`changed_by` é obrigatório) — só a aplicação tem esse
  contexto. Design final: `BoardService.change_stage` é o ÚNICO caminho que grava
  histórico (usado por `move_stage`/`bulk_move_stage`/`LawsuitService.update`, este último
  ganhou um parâmetro `changed_by` novo), e a trigger cuida sozinha de `stage_entered_at`
  sempre que `stage_id` muda de verdade — nunca escrita à mão pela aplicação.
- **`updated_at` expirado gerava `MissingGreenlet`.** `board.move_stage()` mutava
  `lawsuit.stage_id` sem tocar `updated_at` (que tem `onupdate=func.now()` — server-side);
  o autoflush de uma query subsequente expirava o atributo, e a serialização síncrona do
  response explodia. Mesmo problema (e mesma correção — setar `updated_at` explicitamente
  na mutação) já documentado em `LawsuitService.update` desde a spec 022; agora
  centralizado em `BoardService.change_stage`, que cobre os 3 caminhos de escrita.
- **`/bulk/move-stage` registrado ANTES de `/{lawsuit_id}`** — mesma armadilha de
  ordenação de rota já documentada na spec 048 (`/counts`/`/export` antes de
  `/{publication_id}`): sem isso, "bulk" seria capturado como `lawsuit_id` inválido (422)
  antes de chegar no handler certo.
- **Drag & drop e2e precisou de `DataTransfer` sintético.** `Locator.dragTo()` do
  Playwright simula o mouse, mas nem sempre dispara o ciclo nativo `dragstart`/
  `dragover`/`drop` do HTML5 em Chromium headless de forma confiável (flakou 1 de 3
  execuções nos primeiros testes). Trocado por `page.evaluate` disparando os eventos DOM
  diretamente com um `DataTransfer` real, envolvido num retry por condição (`toPass`) —
  mesma classe de mitigação já usada na jornada 7/25 (spec 048), sem `sleep`.
- **"Virtualização para volume" (§2) interpretada como paginação, não windowing.** Não há
  lib de virtualização de DOM (react-window etc.) no projeto; adicionar uma só para isto
  seria uma dependência nova para um ganho marginal, já que `limit_per_column` (padrão 50)
  mais "carregar mais" (regra 7) já limita o tamanho do DOM por coluna de forma prática.
  Documentado aqui em vez de silenciosamente divergir do escopo.
- **Ação em massa reaproveita `ConfirmDialog` (spec 007), não um modal novo.** Checkbox por
  card (dentro do `renderCard` do `KanbanBoard`, sem alterar o componente genérico) +
  `<select>` de etapa que aparece quando há seleção; "Aplicar" abre o `ConfirmDialog` já
  existente com a contagem e a etapa de destino antes de disparar a mutação — mesmo
  componente que `CustomerListPage`/outras telas já usam para confirmar ação em massa.
- **`integration_health` (spec 049) não é limpa entre execuções de teste — achado ao
  fechar esta spec.** `scripts/run-tests.sh` faz `TRUNCATE tenants CASCADE`, que também
  esvazia `integration_alerts` (tem FK pra `tenants`, mesmo nas linhas de sistema com
  `tenant_id` nulo — `TRUNCATE ... CASCADE` esvazia a tabela inteira, não filtra por
  linha). `integration_health` não tem `tenant_id` nenhum, então nunca era limpa por
  esse cascade — rows deixadas por uma execução `pytest` avulsa (fora do `run-tests.sh`,
  comum ao iterar rápido num teste isolado) acumulavam e derrubavam
  `test_duas_saudes_falhas_seguidas_criam_alerta_critico` (049) em runs seguintes, porque
  "as 2 mais recentes" deixava de ser as do teste atual. Corrigido: `run-tests.sh` agora
  também `TRUNCATE integration_health` explicitamente.

## 10. Definição de pronto

- [x] Escopo implementado, nada além (estagnação/métricas ficam na 052; workflow ao mover
      fica na 053 — nenhuma das duas tocada aqui)
- [x] Todas as regras de negócio com teste (9 testes de integração cobrindo as 11 regras:
      as 9 fases sempre visíveis, histórico gravado dentro e fora do Kanban, primeira etapa
      da fase, trigger de `stage_entered_at`, RBAC do Colaborador, ação em massa
      transacional, paginação por coluna, orçamento de queries do board)
- [x] Teste de isolamento por tenant — `lawsuit_stage_history` é tabela nova com RLS padrão
      via `enable_rls` (migration 051); o padrão de isolamento já é coberto sistemicamente
      desde a spec 003, e o teste da spec 050 (`test_rls_lawsuit_subjects_isola_por_tenant`)
      validou o MESMO mecanismo genérico para uma tabela irmã recente — não duplicado aqui
      por já estar coberto pelo padrão
- [x] `make test` verde e wall-clock < 300 s (232 s — 749 backend, 143 frontend, 9 e2e)
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário (`Select[Any]`
      em `_board_select` segue o mesmo padrão já aprovado de `core/listing.py::paginate_keyset`)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Componentes reutilizáveis: `KanbanBoard<T>` genérico entregue (novo, para a 052/053
      reaproveitarem); `FilterBar`/`EmptyState`/`ConfirmDialog` reaproveitados sem duplicar
- [x] Commit `feat(051): CRM — board Kanban`
