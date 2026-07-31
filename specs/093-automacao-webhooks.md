# 093 — Automação: webhooks outbound

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 092 · **Status:** ⬜ pendente

---

## 1. Objetivo

Ação de automação que envia dados para fora: n8n, CRM, ERP, o que o escritório usar. Envio
unidirecional com payload padronizado, assinatura e retry.

## 2. Escopo

- Ação `http_request` na automação
- Payload padronizado por tipo de gatilho
- Assinatura HMAC
- Retry com backoff
- Log de entrega com corpo da resposta
- Reenvio manual

## 3. Fora de escopo

- Webhooks de entrada (fora do escopo) · Decisão por LLM → 094

## 4. Modelo de dados

```sql
CREATE TABLE webhook_endpoints (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  secret TEXT NOT NULL,                -- para HMAC
  headers JSONB NOT NULL DEFAULT '{}',
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE webhook_deliveries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  endpoint_id UUID NOT NULL REFERENCES webhook_endpoints(id) ON DELETE CASCADE,
  run_id UUID REFERENCES automation_runs(id) ON DELETE SET NULL,
  event_kind TEXT NOT NULL,
  payload JSONB NOT NULL,
  attempt SMALLINT NOT NULL DEFAULT 1,
  status_code SMALLINT,
  response_body TEXT,
  duration_ms INTEGER,
  error TEXT,
  delivered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_deliveries_endpoint ON webhook_deliveries (endpoint_id, created_at DESC);
CREATE INDEX ix_deliveries_failed ON webhook_deliveries (tenant_id, created_at DESC)
  WHERE delivered_at IS NULL;
```
RLS nas duas. Migration `093_webhooks.py`.

## 5. Payloads padronizados

**Gatilho `task.completed`:**
```json
{ "event": "task.completed", "occurred_at": "...", "tenant_id": "...",
  "task": { "id", "title", "notes", "location", "scheduled_date", "deadline_date",
            "completed_at", "points" },
  "lawsuit": { "id", "process_number", "protocol_number", "stage", "responsible_id",
               "customers": [{ "id","name","identification","origin","cellphone","phone","email" }] },
  "users": [{ "id","name","completed_at","important","urgent" }] }
```

**Gatilho `lawsuit.stage_changed`:**
```json
{ "event": "lawsuit.stage_changed", "occurred_at": "...", "tenant_id": "...",
  "lawsuit": { "id", "process_number", "protocol_number", "notes",
               "from_stage", "to_stage", "responsible_id",
               "customers": [ ... ] },
  "changed_by": { "id", "name" } }
```

Estrutura inspirada no contrato do Flowter documentado em
`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §8.

## 6. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/webhook-endpoints` | ADMINISTRADOR |
| POST/PUT/DELETE | `/api/v1/webhook-endpoints[/{id}]` | GESTOR |
| POST | `/api/v1/webhook-endpoints/{id}/test` | GESTOR |
| GET | `/api/v1/webhook-deliveries?endpoint_id=&status=&cursor=` | ADMINISTRADOR |
| POST | `/api/v1/webhook-deliveries/{id}/retry` | ADMINISTRADOR |

## 7. Regras de negócio

1. Envio é **unidirecional**: o Rito manda e não espera resposta de negócio. `2xx` é entrega bem-sucedida, ponto.
2. Assinatura HMAC-SHA256 do corpo, no header `X-Rito-Signature`, com timestamp em `X-Rito-Timestamp` para evitar replay.
3. Retry em falha de conexão, timeout e `5xx`: 3 tentativas com backoff de 1 min, 5 min e 15 min. `4xx` não é retentado.
4. Timeout de 10 s por tentativa.
5. Corpo da resposta é guardado truncado em 10 KB, para diagnóstico.
6. URL precisa ser HTTPS. HTTP só é aceito para `localhost`, em desenvolvimento.
7. **SSRF:** IP privado, `localhost` (fora de dev), `169.254.169.254` e redirecionamento para host privado são bloqueados. Validação na resolução do DNS, não só na string da URL.
8. Segredo é gerado pelo sistema, exibido uma vez e pode ser rotacionado.
9. Teste envia payload de exemplo e mostra a resposta completa.
10. Endpoint com 20 falhas consecutivas é desativado, com alerta.
11. Reenvio manual usa o payload original.
12. Retenção de entregas: 30 dias.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | payload de `task.completed` bate com o contrato | ~0,4 s |
| integração | payload de `lawsuit.stage_changed` bate com o contrato | ~0,4 s |
| unit | assinatura HMAC é verificável | ~0,2 s |
| integração | retry em 500, com backoff | ~0,4 s |
| integração | 400 não é retentado | ~0,3 s |
| integração | timeout conta como falha e retenta | ~0,3 s |
| integração | **URL http externa é rejeitada** | ~0,2 s |
| integração | **IP privado é bloqueado (SSRF)** | ~0,3 s |
| integração | **redirecionamento para host privado é bloqueado** | ~0,4 s |
| integração | 20 falhas desativa e alerta | ~0,4 s |
| integração | reenvio usa o payload original | ~0,3 s |
| integração | resposta truncada em 10 KB | ~0,2 s |
| frontend | segredo exibido uma vez só | ~0,3 s |

**Total:** ~4,1 s

> Os três testes de SSRF são obrigatórios. Webhook configurável pelo usuário é o vetor clássico
> de acesso à rede interna.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · SSRF bloqueado em 3 caminhos · Commit `feat(093): automação — webhooks outbound`
