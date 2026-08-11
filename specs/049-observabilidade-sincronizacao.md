# 049 — Observabilidade da sincronização

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 048 · **Status:** ⬜ pendente

---

## 1. Objetivo

Sincronização quebrada em silêncio é prazo perdido. Esta spec garante que falha vire **alerta
atribuído a uma pessoa**, não linha de log que ninguém lê.

## 2. Escopo

- Painel de status por termo monitorado e por integração
- Histórico de execuções com contadores
- **Falha vira alerta** atribuído ao responsável
- Alertas de integração com banner global
- Métricas de captura
- Job de saúde diário

## 3. Fora de escopo

- Notificação por e-mail/WhatsApp → 069 · Observabilidade da aplicação → 097

## 4. Modelo de dados

> **Decisão (bloqueio resolvido com o usuário):** o esboço original usava `alert_post_id`
> referenciando `posts` — mas `posts.lawsuit_id` é `NOT NULL` por desenho desde a spec 032
> (toda tarefa pertence a um processo) e um alerta de sincronização não tem processo. A
> alternativa escolhida foi reaproveitar `integration_alerts` (spec 046) em vez de criar uma
> tarefa: menos rico (sem pontuação/produtividade), mas não força mudança de modelo em 9
> specs anteriores. `alert_post_id` virou `alert_id` (FK para `integration_alerts`), que por
> sua vez ganhou `responsible_user_id` e `resolved_by`.

```sql
ALTER TABLE monitored_terms
  ADD COLUMN consecutive_failures SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN alert_id UUID REFERENCES integration_alerts(id);

ALTER TABLE integration_alerts
  ADD COLUMN responsible_user_id UUID REFERENCES users(id),
  ADD COLUMN resolved_by UUID REFERENCES users(id);

CREATE TABLE integration_health (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  integration TEXT NOT NULL,
  checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_healthy BOOLEAN NOT NULL,
  latency_ms INTEGER,
  detail TEXT
);
CREATE INDEX ix_health_recent ON integration_health (integration, checked_at DESC);
```
`integration_health` é taxonomia/telemetria global do sistema (mesmo padrão de
`cnj_movement_codes`, spec 046): sem `tenant_id`, sem RLS — saúde da integração em si, não
dado de nenhum tenant.

Migration `049_sync_observability.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/integrations/status` | ADMINISTRADOR |
| GET | `/api/v1/integrations/alerts?resolved=false` | ADMINISTRADOR |
| POST | `/api/v1/integrations/alerts/{id}/resolve` | GESTOR |
| GET | `/api/v1/monitored-terms/{id}/health` | ADMINISTRADOR |
| GET | `/api/v1/publications/metrics?period=` | ADMINISTRADOR |

`status` devolve, por integração: saudável, última execução com sucesso, latência média,
falhas em 24 h e termos por status.

## 6. Front-end

**Reutiliza:** `StatCard`, `DataTable`, `EmptyState`, `IntegrationAlertBanner`,
`SyncRunsTable` (spec 043/044 — mesmo papel do `SyncRunsTimeline` do esboço original, não
duplicado)
**Cria:** `IntegrationStatusPanel`, `TermHealthCard`, `CaptureMetricsChart`
**Rotas:** `/settings/integrations`, painel no topo de `/publications`

## 7. Regras de negócio

1. **Três falhas consecutivas** no mesmo termo criam um `IntegrationAlert` de aviso
   (`integration="djen"`, `code="term_sync_failed"`) atribuído ao responsável do termo (ou ao
   GESTOR mais antigo, se não houver), com a mensagem de erro da execução.
2. O alerta é **um só por termo**: `monitored_terms.alert_id` evita enxurrada. Nova falha
   atualiza a mensagem do alerta existente em vez de criar outro.
3. Sucesso após falha zera `consecutive_failures`, resolve o alerta (`resolved_at`) e anexa a
   mensagem com uma nota de normalização.
4. Alerta crítico de integração (401 do DataJud, por exemplo) mostra banner global — restrito
   a ADMINISTRADOR e GESTOR (o Colaborador não vê o banner).
5. Job de saúde diário faz uma chamada leve a cada integração e grava latência.
6. Duas verificações de saúde falhas seguidas geram alerta crítico.
7. Métricas de captura: publicações por dia e por tribunal, e taxa de vínculo automático.
   Métrica "por termo" fica de fora — `publications` não grava qual termo casou a captura
   (`TermSyncService._process_item` nunca recebeu esse dado); exige uma coluna nova fora do
   §4 desta spec, então vira Descoberta para uma spec futura em vez de scope creep aqui.
8. **Taxa de vínculo automático abaixo de 70%** em 7 dias gera alerta de aviso — indica cadastro de processo com número errado.
9. Histórico de execuções mantido por 90 dias.
10. Painel é somente leitura, exceto resolver alerta.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | 3 falhas criam alerta de aviso | ~0,5 s |
| integração | 4ª falha atualiza a mensagem, não cria segundo alerta | ~0,4 s |
| integração | sucesso zera contador e resolve alerta | ~0,4 s |
| integração | sucesso anexa nota de normalização na mensagem | ~0,3 s |
| integração | 401 do DataJud aparece como alerta crítico | ~0,3 s |
| integração | job de saúde grava latência | ~0,3 s |
| integração | 2 saúdes falhas → alerta crítico | ~0,3 s |
| integração | taxa de vínculo < 70% gera aviso | ~0,4 s |
| integração | status agrega termos corretamente | ~0,4 s |
| integração | Colaborador → 403 | ~0,2 s |
| frontend | banner só para ADMIN e GESTOR | ~0,3 s |
| frontend | card de saúde do termo | ~0,3 s |

**Total:** ~4,1 s

## 9. Descobertas

- **Bloqueio de modelo resolvido com o usuário antes de implementar.** O esboço original
  do §4 desenhava `alert_post_id` referenciando `posts` — mas `posts.lawsuit_id` é `NOT NULL`
  por desenho desde a spec 032 (toda tarefa pertence a um processo) e um alerta de
  sincronização de termo não tem processo. Perguntado ao usuário via `AskUserQuestion`
  antes de tocar o modelo; a opção escolhida foi reaproveitar `integration_alerts`
  (spec 046) em vez de mudar `posts` — `alert_post_id` virou `alert_id`, e
  `integration_alerts` ganhou `responsible_user_id`/`resolved_by`. Documentado no §4 da
  própria spec (não só aqui) porque muda o contrato que uma spec futura leria.
- **"Métricas por termo" (regra 7 original) ficou de fora.** `publications` não grava qual
  `monitored_term` casou a captura — `TermSyncService._process_item` nunca recebeu essa
  referência (spec 044). Adicionar essa coluna está fora do §4 desta spec; métricas por dia
  e por tribunal foram implementadas (têm dado pra isso), taxa de vínculo automático também
  (via `matched_by`). Registrar para uma spec futura que precise dessa granularidade.
- **`SyncRunsTimeline` do esboço original já existia como `SyncRunsTable`** (spec 043/044,
  usado no modal "Histórico" de `MonitoredTermsListPage`) — reaproveitado em vez de duplicar
  (regra dos 3 usos, CLAUDE.md §6). `TermHealthCard` novo entra ao lado dele no mesmo modal,
  sem endpoint próprio de histórico (isso já existe em `GET /{id}/runs`).
- **Rollback expira atributos numa `AsyncSession`.** `TermSyncService._execute` já fazia
  `session.rollback()` no caminho de falha (spec 044) e em seguida atribuía novos valores a
  `term.status`/`term.status_message` — SETs, que não disparam I/O. As regras novas da 049
  precisavam LER `term.consecutive_failures`/`term.alert_id`/`term.user_id` depois do
  rollback, e ler um atributo expirado numa sessão assíncrona sem I/O explícito levanta
  `MissingGreenlet` (a sessão não faz lazy-load implícito). Corrigido com
  `await self.session.refresh(term)` logo após o rollback, antes de qualquer leitura.
- **Corrida entre 2 execuções concorrentes do `run-tests.sh`, não do código.** Uma tentativa
  de rodar o gate em background acabou sobrepondo duas invocações completas da suíte contra
  o mesmo Postgres/Redis/porta — wall-clock inflou pra 433-450s e um teste de performance de
  índice (`test_inbox_perf.py`) flakou por contenção de IO, nada relacionado a esta spec. Uma
  execução limpa (processo único, aguardado via notificação de background em vez de `wait`
  manual) confirmou verde: 730 backend, 140 frontend, 8 e2e, 219s.

## 10. Definição de pronto

- [x] Escopo implementado, nada além (notificação por e-mail/WhatsApp continua na 069;
      observabilidade da aplicação continua na 097 — só o §3 desta spec)
- [x] Todas as regras de negócio com teste (10 testes de integração cobrindo as regras 1-4,
      6 e 8-10; a regra 5 — chamada leve por integração — é exercitada com um fake do
      Protocol `IntegrationHealthChecker`, sem chamada real de rede)
- [x] Teste de isolamento por tenant (`integration_alerts`/`monitored_terms` já tinham RLS
      cobrindo isolamento desde as specs 043/046; `integration_health` é telemetria global
      sem tenant, mesmo padrão de `cnj_movement_codes` — não se aplica)
- [x] `make test` verde e wall-clock < 300 s (219 s — 730 backend, 140 frontend, 8 e2e)
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário (os dois
      `# type: ignore[attr-defined]` em `purge_older_than`/`metrics` seguem o padrão já
      estabelecido em `posts`/`notifications`/`task_types` repository para `.rowcount` de
      `AsyncSession.execute`, comentado como tal)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Componentes reutilizáveis extraídos quando bateu 3 usos (`BarChart` da spec 019
      reaproveitado no `CaptureMetricsChart`/`IntegrationStatusPanel` em vez de nova lib de
      gráfico; `StatCard`/`EmptyState` da 007 reaproveitados; `SyncRunsTable` da 043/044
      reaproveitado em vez do `SyncRunsTimeline` do esboço original)
- [x] Commit `feat(049): observabilidade da sincronização`
