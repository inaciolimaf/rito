# 053 — CRM: workflow ao mover

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 052, 038 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Nada é aplicado sem confirmação · Commit `feat(053): CRM — workflow ao mover`
