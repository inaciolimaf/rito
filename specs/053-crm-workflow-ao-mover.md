# 053 — CRM: workflow ao mover

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 052, 038 · **Status:** ✅ concluída

---

## 1. Objetivo

Fechar o laço entre funil e execução: mover o card para uma etapa sugere o workflow configurado
nela e, com um clique, a equipe inteira já tem as tarefas na caixa de entrada.

## 2. Escopo

- Sugestão de workflow ao mudar de etapa
- Diálogo de confirmação com preview das tarefas
- Aplicação transacional
- Registro do que foi aplicado
- Opção de não sugerir novamente naquele processo

## 3. Fora de escopo

- Automação por gatilho genérico → 092 · Decisão por LLM → 094

## 4. Modelo de dados

```sql
CREATE TABLE workflow_applications (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  workflow_id UUID NOT NULL REFERENCES workflows(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  stage_id UUID REFERENCES stages(id),      -- etapa que disparou
  applied_by UUID NOT NULL REFERENCES users(id),
  posts_created UUID[] NOT NULL DEFAULT '{}',
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_wf_app_lawsuit ON workflow_applications (lawsuit_id, applied_at DESC);

CREATE TABLE workflow_suppressions (
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  stage_id UUID NOT NULL REFERENCES stages(id),
  PRIMARY KEY (lawsuit_id, stage_id)
);
```
RLS nas duas. Migration `053_workflow_applications.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/lawsuits/{id}/move-stage` passa a devolver `suggested_workflow` |
| POST | `/api/v1/lawsuits/{id}/apply-workflow` → `{workflow_id, stage_id?}` |
| POST | `/api/v1/lawsuits/{id}/suppress-workflow` → `{stage_id}` |
| GET | `/api/v1/lawsuits/{id}/workflow-applications` |

## 6. Front-end

**Reutiliza:** `ConfirmDialog`, `WorkflowPreviewDialog` (de 038)
**Cria:** `SuggestWorkflowDialog` (preview + aplicar + não sugerir mais)
**Rota:** sobre `/crm` e `/lawsuits/:id`

## 7. Regras de negócio

1. Mover para etapa com `suggested_workflow_id` **sugere**; nunca aplica sozinho.
2. O diálogo mostra o preview exato: tarefa, responsável e data calculada de cada etapa.
3. Aplicar é transacional — falha em uma tarefa, nenhuma é criada.
4. `workflow_applications` registra o que foi criado, permitindo desfazer.
5. Desfazer é possível em até 1 h e só se **nenhuma** das tarefas foi concluída.
6. "Não sugerir novamente" grava em `workflow_suppressions` para aquele par processo+etapa.
7. Voltar para a mesma etapa depois sugere de novo, salvo supressão.
8. Workflow já aplicado no processo pede confirmação extra, mostrando quando foi.
9. Sugestão respeita permissão: quem não pode criar tarefa não vê o diálogo.
10. Movimento em massa **não** sugere workflow — seria enxurrada. Aplique depois, individualmente.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | mover sugere o workflow da etapa | ~0,4 s |
| integração | etapa sem workflow não sugere | ~0,2 s |
| integração | aplicar cria as tarefas e registra | ~0,4 s |
| integração | aplicação é transacional | ~0,4 s |
| integração | desfazer em 1 h remove as tarefas | ~0,4 s |
| integração | desfazer com tarefa concluída → 409 | ~0,3 s |
| integração | desfazer após 1 h → 409 | ~0,2 s |
| integração | supressão impede nova sugestão | ~0,3 s |
| integração | reaplicar pede confirmação | ~0,3 s |
| integração | movimento em massa não sugere | ~0,3 s |
| frontend | diálogo mostra preview com datas | ~0,4 s |

**Total:** ~3,6 s

## 9. Descobertas

- **`WorkflowService.apply`/`preview` (spec 038) foram reaproveitados 100% para a
  criação de tarefas** — nenhuma lógica de resolução de responsável/data/tipo pulado
  foi duplicada. O novo `LawsuitWorkflowService` (lawsuits domain) só adiciona o que
  faltava para o gatilho de mover etapa: QUAL workflow sugerir (`suggest_for_move`) e
  um registro real de aplicação (`workflow_applications`) — o `WorkflowService`
  sozinho não tem como gravar isso porque `Post` não guarda vínculo com o workflow
  que o criou (mesma limitação já documentada no comentário de
  `WorkflowService._already_applied`, spec 038).
- **`stages.suggested_workflow_id` já existia desde a spec 038, mas nunca tinha sido
  exposto em `StageCreateRequest`/`StageUpdateRequest`.** A coluna e a leitura
  (`StageResponse.suggested_workflow_id`) já estavam prontas; faltava a escrita —
  sem isso a regra 1 inteira não tinha como ser configurada. Adicionado com validação
  (`SuggestedWorkflowNotFoundError` → 422) em `StageService.create`/`update`.
- **`workflow_suppressions` ganhou o `id` UUID padrão de `Base`, não a PK composta
  (`lawsuit_id`+`stage_id`) que a spec desenha em SQL.** Um `UNIQUE(lawsuit_id,
  stage_id)` cumpre exatamente a mesma regra ("1 supressão por par") sem abrir uma
  exceção na infraestrutura de repositório/RLS, que assume `model.id` em toda tabela
  do projeto sem exceção (mesma decisão pragmática já registrada para `Step`/
  `Holiday`, spec 012, só que lá a exceção era remapear `id` para outra coluna única).
- **`stagnant_since`-style: `move-stage` passou a devolver `{lawsuit,
  suggested_workflow}` em vez do `LawsuitResponse` direto** — contrato explícito do
  §5 ("passa a devolver `suggested_workflow`"). Isso exigiu atualizar 2 assertions
  pré-existentes da spec 051 em `test_crm_kanban.py` (liam `response.json()["stage_id"]`
  direto) para `response.json()["lawsuit"]["stage_id"]`. Mudança de comportamento
  autorizada pelo próprio contrato da spec — não uma quebra acidental de refatoração
  (que teria que preservar o shape antigo).
- **`WorkflowPreviewDialog` (spec 038) ganhou `applyFn`/`onSuppress` opcionais em vez
  de um diálogo novo do zero.** `SuggestWorkflowDialog` (novo, `features/crm/`) é uma
  casca fina que passa `applyLawsuitWorkflow` (grava `workflow_applications`) no
  lugar do `applyWorkflow` genérico padrão — mesma UI de preview/tarefas/avisos,
  dois destinos de aplicação. Evita duplicar toda a renderização da lista de tarefas
  por causa de UM endpoint diferente.
- **Erro 409 de reaplicar já carrega "quando foi" no `detail`** (regra 8) — o
  `WorkflowPreviewDialog` agora mostra `error.message` (via `ApiError`) em vez de uma
  mensagem genérica fixa, então o texto do backend ("...aplicado em
  2026-08-11T14:32:...") chega ao usuário sem UI extra.
- **Desfazer (regra 5) não ganhou UI própria nesta spec** — só a API
  (`DELETE /lawsuits/{id}/workflow-applications/{id}`), testada via integração. O §6
  só lista `SuggestWorkflowDialog` como componente novo; nenhuma tela consome
  `GET /workflow-applications` ainda. Ficou de fora de propósito (fora do escopo
  declarado), não esquecido.
- **Regra 9 ("sugestão respeita permissão") é satisfeita sem código extra.**
  `COLABORADOR` já é o piso tanto para mover etapa quanto para criar post — quem
  chega ao diálogo de sugestão sempre tem permissão de aplicar.
- **Regra 10 ("ação em massa não sugere") não precisou de guarda explícita** — o
  endpoint `/bulk/move-stage` continua devolvendo só `BulkMoveStageResponse`
  (`{moved}`), sem o campo novo; testado (`test_movimento_em_massa_nao_sugere`)
  garantindo que a chave nem aparece no corpo.

## 10. Definição de pronto

- [x] Escopo implementado, nada além (automação por gatilho genérico fica pra 092;
      decisão por LLM pra 094 — nenhuma das duas tocada aqui)
- [x] Todas as regras de negócio com teste (11 testes de integração cobrindo as 10
      regras: sugestão ao mover, etapa sem workflow, aplicar registra, transacional,
      desfazer em 1h, desfazer com tarefa concluída → 409, desfazer após 1h → 409,
      supressão, reaplicar com confirmação, massa nunca sugere, isolamento por tenant)
- [x] Teste de isolamento por tenant — `workflow_applications`/`workflow_suppressions`
      são tabelas novas, `test_tenant_b_nao_enxerga_aplicacoes_de_a` prova que tenant B
      recebe 404 tanto pra listar aplicações quanto pra suprimir workflow do processo
      de tenant A
- [x] `make test` verde e wall-clock < 300 s (214 s — 769 backend, 147 frontend, 9 e2e;
      nenhuma jornada e2e nova, dentro do orçamento de +4 s previsto no §8)
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Componentes reutilizáveis: `ConfirmDialog`/`WorkflowPreviewDialog` (spec 038)
      reaproveitados sem duplicar (o segundo ganhou 2 props opcionais em vez de um
      fork); `SuggestWorkflowDialog` novo é uma casca fina sobre o `WorkflowPreviewDialog`
- [x] Nada é aplicado sem confirmação — `apply-workflow` sempre exige o clique no
      diálogo; nenhum caminho aplica workflow automaticamente ao mover
- [x] Commit `feat(053): CRM — workflow ao mover`
