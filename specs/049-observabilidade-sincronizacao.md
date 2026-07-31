# 049 — Observabilidade da sincronização

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 048 · **Status:** ⬜ pendente

---

## 1. Objetivo

Sincronização quebrada em silêncio é prazo perdido. Esta spec garante que falha vire **tarefa
para uma pessoa**, não linha de log que ninguém lê.

## 2. Escopo

- Painel de status por termo monitorado e por integração
- Histórico de execuções com contadores
- **Falha vira tarefa** para o responsável
- Alertas de integração com banner global
- Métricas de captura
- Job de saúde diário

## 3. Fora de escopo

- Notificação por e-mail/WhatsApp → 069 · Observabilidade da aplicação → 097

## 4. Modelo de dados

```sql
ALTER TABLE monitored_terms
  ADD COLUMN consecutive_failures SMALLINT NOT NULL DEFAULT 0,
  ADD COLUMN alert_post_id UUID REFERENCES posts(id);

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

**Reutiliza:** `StatCard`, `DataTable`, `EmptyState`, `IntegrationAlertBanner`
**Cria:** `IntegrationStatusPanel`, `TermHealthCard`, `SyncRunsTimeline`, `CaptureMetricsChart`
**Rotas:** `/settings/integrations`, painel no topo de `/publications`

## 7. Regras de negócio

1. **Três falhas consecutivas** no mesmo termo criam uma tarefa de alerta para o responsável
   (ou para o GESTOR, se não houver), com instruções de correção.
2. A tarefa de alerta é **uma só por termo**: `alert_post_id` evita enxurrada. Nova falha
   comenta na tarefa existente em vez de criar outra.
3. Sucesso após falha zera `consecutive_failures`, resolve o alerta e comenta na tarefa que foi normalizado.
4. Alerta crítico de integração (401 do DataJud, por exemplo) mostra banner global para ADMINISTRADOR e GESTOR.
5. Job de saúde diário faz uma chamada leve a cada integração e grava latência.
6. Duas verificações de saúde falhas seguidas geram alerta crítico.
7. Métricas de captura: publicações por dia, por tribunal, por termo, e taxa de vínculo automático.
8. **Taxa de vínculo automático abaixo de 70%** em 7 dias gera alerta de aviso — indica cadastro de processo com número errado.
9. Histórico de execuções mantido por 90 dias.
10. Painel é somente leitura, exceto resolver alerta.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | 3 falhas criam tarefa de alerta | ~0,5 s |
| integração | 4ª falha comenta, não cria segunda tarefa | ~0,4 s |
| integração | sucesso zera contador e resolve alerta | ~0,4 s |
| integração | sucesso comenta normalização na tarefa | ~0,3 s |
| integração | 401 do DataJud gera banner crítico | ~0,3 s |
| integração | job de saúde grava latência | ~0,3 s |
| integração | 2 saúdes falhas → alerta crítico | ~0,3 s |
| integração | taxa de vínculo < 70% gera aviso | ~0,4 s |
| integração | status agrega termos corretamente | ~0,4 s |
| integração | Colaborador → 403 | ~0,2 s |
| frontend | banner só para ADMIN e GESTOR | ~0,3 s |
| frontend | card de saúde do termo | ~0,3 s |

**Total:** ~4,1 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Falha vira tarefa, sem enxurrada · Commit `feat(049): observabilidade da sincronização`
