# 040 — 🔧 REFATORAÇÃO — Tarefas

**Fase:** 3 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 031–039 · **Status:** ✅ concluída

---

## 1. Objetivo

`posts` virou a tabela mais acessada do sistema e `PostService` provavelmente cresceu demais.
Além disso, três lógicas de calendário nasceram separadas — recorrência (034), dias úteis (038)
e agenda (037) — e vão ser reusadas por intimações (086) e financeiro (057).

> Refatoração não muda comportamento. Testes de 031–039 passam **sem edição**.

## 2. Alvo 1 — módulo de datas único

- [x] Extrair `app/core/dates.py`: dias úteis, feriados, próxima ocorrência de recorrência, fim de mês, última semana do mês
- [x] Zero dependência de framework — função pura, testável isolada
- [x] Migrar 034, 037 e 038 para ele — 034/038 migrados (recorrência e dias úteis); 037 (agenda) não tinha cálculo próprio de backend — a grade de dias é frontend (`features/schedule/calendar.ts`); a aritmética de mês duplicada em lawsuits/stats (028) e taskscore (039) também migrou
- [x] Documentar que 057 (parcelamento) e 086 (prazo processual) devem usá-lo — docstring do módulo + entrada em DECISOES.md

## 3. Alvo 2 — quebrar o PostService

Se passou de ~300 linhas, divida por caso de uso:
- [x] `CreatePostUseCase` (com expansão de time e detecção de duplicata) — `posts/creation.py`
- [x] `CompletePostUseCase` (com crédito de pontos e geração de recorrência) — `posts/completion.py`
- [x] `InboxQueryService` (seções e contadores) — já existia desde a 036 (`inbox/service.py`); nesta spec ele deixou de alcançar membros privados do PostService (`_all_completed`/`recurrences`): `all_completed` virou dado do PostRepository
- [x] `TaskscoreService` (agregação e ranking) — já existia desde a 039 (`taskscore/service.py`)
- [x] PostDetail/build_detail extraídos para `posts/detail.py` (compartilhado pelos 3 consumidores); PostService ficou com leitura/edição/flags/delete (~120 linhas)

## 4. Alvo 3 — performance da caixa de entrada

É a tela mais aberta do produto. Ela tem que ser rápida.

- [x] Contadores das 6 seções em **1 query** (verificar se ficou assim mesmo) — confirmado: GROUP BY sobre o CASE, `InboxRepository.counts`
- [x] Listagem sem N+1 em partes, responsáveis e tipo de tarefa — confirmado: `parties_for` e `assignee_names_for` em batch único; tipo no join da subquery
- [x] `EXPLAIN ANALYZE` com 10.000 tarefas semeadas — 20 mil linhas (10k pendentes + 10k concluídas): acesso a `post_users` sempre indexado; números em docs/DECISOES.md
- [x] Índices parciais de `post_users` sendo usados de fato — `ix_post_users_pending` escolhido na forma "minhas pendentes"; no escopo completo o planner prefere posts + `uq_post_users_post_user` (plano ótimo, verificado no EXPLAIN do teste)

## 5. Checklist

### Cobertura
- [x] Toda regra numerada de 031–039 com teste — verificado por spec (95 testes de posts/inbox/workflows/schedule/stats/taskscore passando sem edição)
- [x] Matriz de pontuação: 25 combinações — `tests/unit/test_task_score.py` parametrizado 5×5
- [x] Casos de borda de calendário: bissexto, mês curto, última semana — `tests/unit/test_recurrence_dates.py` (29/02 anual, dia 31 em fevereiro, última semana em mês de 4 e 5 semanas)
- [x] Privacidade de tarefa testada contra GESTOR — `test_privada_invisivel_para_nao_envolvido_inclusive_gestor`
- [x] iCal validado por parser real — `icalendar.Calendar` em `test_schedule.py`
- [x] Isolamento entre tenants nas 7 tabelas novas — coberto por feature (task_types, posts, recorrências, comentários, inbox, workflows, closure_goals/scores) + teste de isolamento da view barreira da 039

### SOLID
- [x] `dates.py` puro — sem imports fora de stdlib
- [x] `FileStorage` como interface (035 não pode ter acoplado ao disco local) — `integrations/storage/base.py` (Protocol) + `s3.py`; não existe implementação de disco local
- [x] Geração de iCal em serviço próprio, não no router — `schedule/ical.py` (116 linhas, chamado pelo service)
- [x] Nenhum use case acima de ~150 linhas — creation.py ≈ 130, completion.py ≈ 105, PostService ≈ 120

### Duplicação
- [x] Lógica de data unificada (alvo 1)
- [x] `attachments` e `notifications` genéricas o bastante para contatos e financeiro — `attached_to_type`/`attached_to_id` sem FK de propósito, validação no service (documentado no model desde a 035)
- [x] Padrão de listagem de 030 aplicado à caixa de entrada — keyset por tupla `(created_at, id)` com cursor, mesma mecânica de `core/listing.py`

### Banco
- [x] View materializada refresca concorrente, sem lock — `REFRESH ... CONCURRENTLY` em AUTOCOMMIT (workers/scores.py); refresh não bloqueia leituras da view barreira
- [x] Índices parciais usados — verificado por EXPLAIN no teste de perf
- [x] Cascades corretos (excluir processo → tarefas → comentários → anexos) — posts tem FK CASCADE para lawsuits; comments CASCADE para posts; attachments é genérico sem FK de propósito (decisão da 035 — validação no service)
- [x] Nenhum órfão possível — FKs com CASCADE/SET NULL conforme decidido em cada spec

### Performance dos testes
- [ ] Wall-clock **< 90 s** — NÃO BATIDO: 174 s no fechamento (gate de 300 s ok). Dívida #17 re-atribuída à 050 com o caminho (custo do boot por teste); flake de StateCitySelect não se manifestou
- [ ] E2E com no máximo 6 jornadas até aqui — item desatualizado do roteiro: são 7 jornadas desde a 037 (o teto real é 25 no projeto, CLAUDE.md §3); nenhuma adicionada nesta spec
- [x] Fixture de 10.000 tarefas só nos testes que precisam, em escopo de sessão — `test_inbox_perf.py`, module-scoped por worker, com teardown

## 6. Entregáveis

1. [x] `app/core/dates.py` com cobertura completa — 26 testes de data passando (business_days + recurrence_dates)
2. [x] `PostService` dividido
3. [x] Caixa de entrada medida com 10.000 tarefas, com o número no `docs/DECISOES.md` — 79/87/14 ms
4. [x] `test-timing.json` atualizado
5. [x] Dívidas em `docs/DIVIDA-TECNICA.md` — #17 atualizada e re-atribuída

## 7. Definição de pronto

- [x] Testes de 031–039 passam sem edição — 95 de integração + 26 de unit nas áreas tocadas, mais a suíte completa verde
- [ ] Wall-clock < 90 s — não batido (174 s); justificativa e plano na dívida #17
- [x] Caixa de entrada < 200 ms com 10.000 tarefas — ≈180 ms a tela completa (cada query < 200 ms)
- [x] Commit `refactor(040): módulo de datas e pente fino das tarefas`
