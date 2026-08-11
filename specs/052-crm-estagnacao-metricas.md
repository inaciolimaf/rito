# 052 — CRM: estagnação e métricas

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 051 · **Status:** ✅ concluída

---

## 1. Objetivo

Processo parado é dinheiro parado e cliente insatisfeito. Aqui o funil passa a apontar
sozinho o que travou.

## 2. Escopo

- Cálculo de estagnação por etapa
- Destaque visual do card estagnado
- Filtro: todos / só estagnados / só em andamento
- Cards de topo do CRM
- Job diário de recálculo

## 3. Fora de escopo

- Workflow ao mover → 053 · BI de tempo → 076 · Detecção de risco por IA → 089

## 4. Modelo de dados

```sql
ALTER TABLE lawsuits
  ADD COLUMN is_stagnant BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN stagnant_since DATE;

CREATE INDEX ix_lawsuits_stagnant ON lawsuits (tenant_id, is_stagnant)
  WHERE is_stagnant AND NOT is_archived;
```
Migration `052_stagnation.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/crm/board?display_stagnant=all\|stagnant\|active` |
| GET | `/api/v1/crm/stats` |
| POST | `/api/v1/crm/recalculate-stagnation` (ADMINISTRADOR, manual) |

`stats`: `total_lawsuits`, `received_this_month`, `total_value`, `stagnant_count`,
`stagnant_value`, `by_step[]`.

## 6. Front-end

**Reutiliza:** `StatCard`, `FilterBar`, `KanbanCard`
**Cria:** `StagnantBadge`, `CrmStatsBar`, `StagnationTooltip`
**Rota:** topo de `/crm`

## 7. Regras de negócio

1. Estagnado quando a etapa tem `enable_stagnant_days = true` **e** o processo está nela há mais
   dias do que `stagnant_days`, contados a partir de `stage_entered_at`.
2. Etapa sem estagnação configurada nunca marca — a regra é da etapa, não global.
3. O cálculo considera **dias corridos**, não úteis. É indicador de gestão, não prazo processual.
4. Job diário às 3h recalcula todo o tenant; mover o processo recalcula na hora.
5. `stagnant_since` guarda quando entrou em estagnação, para ordenar por gravidade.
6. Processo arquivado nunca é estagnado.
7. Card estagnado mostra badge com os dias e tooltip explicando a regra da etapa.
8. `stagnant_value` soma o valor da causa dos estagnados — é o número que dói.
9. Recálculo manual é limitado a uma vez por hora por tenant.
10. Mudar `stagnant_days` da etapa recalcula os processos dela em background.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | marca estagnado ao passar do limite | ~0,4 s |
| integração | etapa sem configuração nunca marca | ~0,3 s |
| integração | mover reseta `stage_entered_at` e desmarca | ~0,4 s |
| integração | arquivado nunca estagna | ~0,2 s |
| integração | job diário recalcula o tenant | ~0,4 s |
| integração | mudar `stagnant_days` recalcula a etapa | ~0,4 s |
| integração | filtro dos 3 modos | ~0,4 s |
| integração | `stagnant_value` soma correto | ~0,3 s |
| integração | recálculo manual 2× em 1 h → 429 | ~0,3 s |
| frontend | badge mostra dias e tooltip | ~0,4 s |

**Total:** ~3,5 s

## 9. Descobertas

- **`enable_stagnant_days`/`stagnant_days` já existiam em `stages` desde a spec 015** — o
  formulário de etapa (spec 015) e o schema já validavam `stagnant_days > 0` quando
  ativo. Esta spec só precisou LER essa configuração; nenhuma migração em `stages`.
- **`stagnant_since` guarda a data em que o processo CRUZOU o limite, não "hoje".**
  `stage_entered_at + stagnant_days` é 100% derivado do estado atual (etapa +
  `stagnant_days`), então `StagnationService.recalculate_stage` recalcula do zero a
  cada chamada sem precisar preservar valor anterior — é isso que dá a ordenação por
  gravidade (regra 5) sem uma segunda coluna ou histórico.
- **Mover processo zera `is_stagnant`/`stagnant_since` direto em
  `BoardService.change_stage`, sem chamar `StagnationService`.** Zero dias na etapa
  nova nunca pode ser estagnação (todo `stagnant_days` configurado é > 0), então gastar
  uma query extra recalculando seria desperdício — a regra 4 ("recalcula na hora") é
  satisfeita por essa certeza lógica, não por uma consulta.
- **Recálculo por troca de `stagnant_days` segue o padrão fire-and-forget de
  `schedule_scores_refresh` (spec 039, `workers/scores.py`).**
  `schedule_stage_recalculation` é no-op em `app_env=test` e best-effort via Celery em
  produção (`workers/stagnation.py`); o teste da regra 10 chama
  `StagnationService.recalculate_stage` direto para provar que o CÁLCULO reage à
  config nova — o mesmo desenho já usado pra "concluir tarefa reagenda o refresh do
  score" (nenhum teste toca fila, CLAUDE.md §3).
- **`StagnantBadge`/`StagnationTooltip` não trouxeram `@radix-ui/react-tooltip`.**
  Um tooltip por hover com Tailwind (`group`/`group-hover`) resolve sem dependência
  nova — mesma decisão já registrada na spec 051 sobre não adicionar lib de
  virtualização por um ganho marginal.
- **`display_stagnant` entrou no `LawsuitFiltersQuery` compartilhado, não num filtro
  exclusivo do CRM.** O board do CRM já reaproveita esse schema inteiro desde a spec
  051 (regra 8 — "mesmos filtros de `/lawsuits`"), então estender o schema único é
  reuso de verdade; criar um segundo tipo de filtro só para o CRM duplicaria a
  tradução `filters_from_query`.
- **Investigação de 2 falhas em `test_sync_observability.py` (spec 049) ao rodar o
  gate desta spec — confirmadas alheias ao escopo.** `integration_alerts` (spec 046)
  tem `tenant_id` nullable para alertas de sistema (DataJud/DJEN); os testes
  `test_quarta_falha_atualiza_mensagem_sem_duplicar` e
  `test_duas_saudes_falhas_seguidas_criam_alerta_critico` falharam num banco de teste
  sujo por invocações `pytest` avulsas feitas durante o desenvolvimento desta spec
  (fora do `run-tests.sh`, que só limpa no INÍCIO da própria execução). Reproduzido
  isoladamente: falham sujo, passam limpo. Verificado que `TRUNCATE tenants CASCADE`
  já esvazia `integration_alerts` por inteiro (inclusive linhas com `tenant_id` nulo —
  `TRUNCATE ... CASCADE` trunca a tabela dependente inteira, não filtra por FK) — ao
  contrário do gap real de `integration_health` achado na spec 051, aqui não havia
  lacuna nenhuma em `run-tests.sh`; nenhuma mudança nele foi necessária.
- **Flake isolado de orçamento em `test_inbox_perf.py`** (spec 033, fora do escopo
  desta spec — módulo de inbox/posts) observado uma vez sob contenção de CPU das 3
  suítes rodando concorrentes (267 ms vs. 200 ms de orçamento); confirmado passando
  limpo quando rodado sozinho. Não é um problema desta spec; registrado aqui só porque
  apareceu durante o fechamento do gate.

## 10. Definição de pronto

- [x] Escopo implementado, nada além (workflow ao mover fica pra 053; BI de tempo pra
      076; detecção de risco por IA pra 089 — nenhum tocado aqui)
- [x] Todas as regras de negócio com teste (10 testes de integração cobrindo as 10
      regras: cálculo por etapa, etapa sem config nunca marca, dias corridos,
      job diário/gatilho manual recalculam o tenant, `stagnant_since` como data de
      entrada em estagnação, arquivado nunca estagna, badge com tooltip, `stagnant_value`
      soma certo, recálculo manual 1x/hora, troca de `stagnant_days` recalcula a etapa)
- [x] Teste de isolamento por tenant — `is_stagnant`/`stagnant_since` são colunas em
      `lawsuits`, tabela já coberta por RLS desde a spec 022; nenhuma tabela nova
      criada nesta spec (só 2 colunas + índice parcial), então não há RLS novo a testar
- [x] `make test` verde e wall-clock < 300 s (226 s — 758 backend, 145 frontend, 9 e2e;
      nenhuma jornada e2e nova, dentro do orçamento de +4 s previsto no §8)
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
      (`int(result.rowcount)  # type: ignore[attr-defined]` em `StagnationService`
      segue o mesmo padrão já aprovado em `posts/repository.py`/`lawsuits/folders.py`)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Componentes reutilizáveis: `StagnantBadge`/`StagnationTooltip` novos em
      `components/domain/` (genéricos, sem acoplamento a `Lawsuit`); `StatCard`,
      `FilterBar` e o card do Kanban (`LawsuitCard`, spec 051) reaproveitados sem
      duplicar — nada escrito 3x que justificasse extrair algo além disso
- [x] Commit `feat(052): CRM — estagnação e métricas`
