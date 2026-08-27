# 092 — Automação: gatilhos e ações

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 038 · **Status:** ✅ concluída

---

## 1. Objetivo

Motor de automação no modelo **gatilho → ação → tempo**. Generaliza o workflow de 038: em vez
de só "mudou de etapa, cria tarefas", passa a ser qualquer evento disparando qualquer ação.

## 2. Escopo

- Tabelas de automação, gatilho, ação e execução
- Gatilhos: tarefa concluída, mudança de etapa, processo criado, intimação recebida, lançamento vencido
- Ações: criar tarefa, definir responsável, mudar etapa, notificar, aguardar condição
- Controle de tempo: imediato, N dias úteis ou corridos, condicionado
- Editor visual
- Log de execução

## 3. Fora de escopo

- Webhooks → 093 · Decisão por LLM → 094

## 4. Modelo de dados

```sql
CREATE TABLE automations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  trigger_kind TEXT NOT NULL,
  trigger_config JSONB NOT NULL DEFAULT '{}',   -- ex.: task_type_id, stage_id
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);
CREATE INDEX ix_automations_trigger ON automations (tenant_id, trigger_kind) WHERE is_active;

CREATE TABLE automation_actions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  automation_id UUID NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
  position SMALLINT NOT NULL,
  action_kind TEXT NOT NULL,
  action_config JSONB NOT NULL DEFAULT '{}',
  delay_kind TEXT NOT NULL DEFAULT 'immediate',  -- immediate | business_days | calendar_days | after_previous
  delay_value SMALLINT,
  condition JSONB,                                -- executa só se
  UNIQUE (automation_id, position)
);

CREATE TABLE automation_runs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  automation_id UUID NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
  trigger_payload JSONB NOT NULL,
  subject_type TEXT, subject_id UUID,
  status TEXT NOT NULL DEFAULT 'running',
  actions_completed SMALLINT NOT NULL DEFAULT 0,
  error TEXT,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);
CREATE INDEX ix_runs_automation ON automation_runs (automation_id, started_at DESC);
```
RLS nas três. Migration `092_automations.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/automations?status=` | ADMINISTRADOR |
| POST/PUT/DELETE | `/api/v1/automations[/{id}]` | GESTOR |
| POST | `/api/v1/automations/{id}/test` → simula sem executar | GESTOR |
| GET | `/api/v1/automations/{id}/runs?cursor=` | ADMINISTRADOR |
| POST | `/api/v1/automations/{id}/toggle` | GESTOR |

## 6. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `EntityPicker`, `ConfirmDialog`
**Cria:** `AutomationBuilder` (gatilho no topo, ações em sequência), `TriggerSelect`,
`ActionRow` (tipo + configuração + tempo + condição), `AutomationTestDialog`,
`RunsTimeline`
**Rota:** `/settings/automations`

## 7. Regras de negócio

1. Gatilhos disponíveis: `task.completed`, `lawsuit.stage_changed`, `lawsuit.created`,
   `publication.received`, `transaction.overdue`.
2. `trigger_config` restringe o gatilho — "tarefa concluída" pode valer só para um tipo de tarefa.
3. Ações são executadas **em sequência**, respeitando `position`.
4. `delay_kind = after_previous` encadeia: a ação só roda quando a anterior for concluída (útil para tarefa que depende de tarefa).
5. Dias úteis usam `app/core/dates.py` (040), com feriados.
6. `condition` avalia campos do sujeito antes de executar; falsa, a ação é pulada e registrada como tal.
7. **Proteção contra laço:** uma automação não dispara a si mesma, e a cadeia é limitada a 10 automações encadeadas por evento original.
8. Execução de ação é idempotente por `(run_id, position)` — reprocesso não duplica.
9. Falha em uma ação interrompe a execução e registra; as anteriores permanecem.
10. Teste simula tudo e mostra o que aconteceria, **sem persistir**.
11. Desativar não afeta execuções em andamento.
12. Automação de escrita respeita as permissões do **criador**, não de quem disparou.
13. Máximo de 20 ações por automação.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | os 5 gatilhos disparam (parametrizado) | ~0,7 s |
| integração | `trigger_config` restringe corretamente | ~0,4 s |
| integração | ações executam em sequência | ~0,4 s |
| integração | `after_previous` encadeia | ~0,4 s |
| integração | atraso em dias úteis pula feriado | ~0,3 s |
| integração | condição falsa pula e registra | ~0,3 s |
| integração | **automação não dispara a si mesma** | ~0,4 s |
| integração | **cadeia limitada a 10** | ~0,4 s |
| integração | reprocesso é idempotente | ~0,4 s |
| integração | falha interrompe e preserva as anteriores | ~0,4 s |
| integração | teste não persiste | ~0,3 s |
| integração | permissão é a do criador | ~0,3 s |
| integração | 21ª ação → 422 | ~0,2 s |
| frontend | builder monta gatilho e ações | ~0,5 s |

**Total:** ~5,4 s

## 9. Descobertas

- **O schema da spec não guardava o passo pulado, e isso quebra o suporte.** `§4` previa
  só `actions_completed` na execução. A regra 6 diz que a condição falsa "é pulada e
  registrada como tal" — sem uma linha por passo, condição falsa e ação nunca alcançada
  ficam indistinguíveis, e "por que a tarefa não foi criada?" (a pergunta que chega ao
  suporte) não tem resposta. Entrou `automation_run_steps`, com `UNIQUE (run_id,
  position)` — que é a regra 8 escrita no banco em vez de confiada ao código.
- **Uma execução precisa saber ONDE parou.** `next_position` mais
  `next_action_at`/`waiting_on_id` foram acrescentados a `automation_runs` porque atraso
  em dias e `after_previous` transformam a execução em algo que dura semanas. Retomar é
  reler esse estado, nunca recomeçar — recomeçar recriaria as tarefas do passo 1.
- **`after_previous` é encadeamento de verdade, não um atraso torcendo.** A alternativa
  fácil seria "espere 3 dias e assuma que a revisão terminou". O que a regra 4 pede é
  outra coisa: a execução fica `waiting` com `waiting_on_id` na tarefa criada, e quem a
  acorda é o próprio gatilho `task.completed`. "Protocolar" só acontece depois de
  "revisar" acontecer de fato.
- **Dois dos cinco gatilhos não nascem de uma escrita.** `task.completed`,
  `lawsuit.created` e `lawsuit.stage_changed` são emitidos de dentro do use case que já
  existia — uma linha cada. `transaction.overdue` é uma DATA que passou, e `wait`/atraso
  precisa de alguém que acorde a execução: os dois viraram varredura
  (`app/domain/automations/sweep.py` + worker de 15 em 15 minutos). A varredura de
  vencidos olha o **dia exato**, porque "tudo que está vencido" republicaria o mesmo
  lançamento todo dia e a régua de cobrança dispararia de novo a cada tick.
- **O gatilho de etapa mora no `change_stage`, não no router.** É o mesmo lugar onde a
  051 pôs o histórico de etapa, e pelo mesmo motivo: mudar de etapa pelo PUT do processo
  é mudar de etapa. Emitir do endpoint do Kanban teria deixado metade das mudanças sem
  automação — e ninguém descobriria, porque a automação simplesmente não rodaria.
- **Nenhuma ação escreve direto na tabela.** `create_task` passa pelo `CreatePostUseCase`,
  `change_stage` pelo `BoardService.change_stage`, `notify` pelo `NotificationService`. A
  validação que reprova um humano reprova a automação — e a duplicata de tarefa, que o
  domínio já sabia reconhecer desde a 032, virou de graça a proteção contra a automação
  rodar duas vezes sobre o mesmo processo.
- **A execução de cada ação roda dentro de um SAVEPOINT.** Custou um teste vermelho: com
  uma etapa inexistente, a FK estourava, a transação inteira ficava abortada e o registro
  da própria falha não conseguia ser gravado. Mesmo idioma da 084 e pelo mesmo motivo —
  parte das validações só falha no banco, e o usuário precisa poder ler o que falhou.
- **A condição é um avaliador declarativo e deliberadamente burro.** `{campo, operador,
  valor}`, nove operadores, sem expressão livre: expressão livre num campo de configuração
  é execução de código com outro nome, e quem escreve a automação é advogado. A comparação
  é por texto porque o payload vem de JSON — comparar um UUID string com um UUID objeto
  faria a condição certa falhar em silêncio, que é a pior forma de falhar.
- **A proteção contra laço tem duas metades, e as duas têm teste.** Uma automação não se
  dispara (o caso real é "tarefa concluída → criar tarefa", que se auto-alimentaria na
  primeira conclusão), e a profundidade viaja com o evento, parando no décimo elo — que é
  o que impede duas automações de se alimentarem em pingue-pongue.
- **A simulação não executa nem em rascunho.** Ela recalcula as datas e devolve o que
  aconteceria, e a resposta traz `persisted: false` como campo. Um "teste" que grava é a
  pior armadilha possível numa tela chamada Testar.

## 10. Definição de pronto

- [x] Checklist padrão
- [x] Proteção contra laço provada — nos dois caminhos (auto-disparo e profundidade)
- [x] Commit `feat(092): automação — gatilhos e ações`
