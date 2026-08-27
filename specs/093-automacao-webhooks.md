# 093 — Automação: webhooks outbound

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 092 · **Status:** ✅ concluída

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

- **A peneira de SSRF roda a cada envio, não só ao salvar.** Validar no cadastro é o
  óbvio; o que o óbvio não cobre é DNS que muda depois. `interno.exemplo.com` pode apontar
  para `8.8.8.8` no dia do cadastro e para `10.0.0.5` na semana seguinte, e o servidor
  continua dentro da rede privada. É por isso que a validação é na **resolução**, e é por
  isso que ela acontece antes de cada tentativa.
- **O redirecionamento é o caminho mais fácil de esquecer.** O destino pode ser
  perfeitamente público e devolver um `Location` apontando para `169.254.169.254` —
  seguir redirect com `follow_redirects=True` desfaz toda a validação feita na URL
  original, em uma linha. O transporte segue os saltos à mão, no máximo três, passando
  cada um pela mesma peneira. Foi o terceiro teste obrigatório da spec e o único que
  exigiu mexer no transporte.
- **Retry não cabe dentro da request.** O backoff é de 1, 5 e 15 minutos (regra 3): segurar
  a request do usuário por 21 minutos seria absurdo, e retentar em memória perderia tudo
  num deploy. A tentativa fica marcada com `next_attempt_at` na própria linha de entrega, e
  quem volta é o worker. Retry usa a MESMA linha (`attempt` incrementa); só o reenvio manual
  cria linha nova, porque ele é outro evento na vida do escritório.
- **`failure_streak` é sequência, e a distinção importa.** Vinte falhas SEGUIDAS significam
  destino morto (regra 10); vinte falhas espalhadas ao longo de um ano significam internet
  ruim, e desativar por isso seria pior que o problema. Uma entrega boa zera o contador, e
  existe teste para exatamente isso.
- **Desativar em silêncio trocaria um problema visível por um invisível.** A desativação
  automática grava um `IntegrationAlert` crítico — reusando o mesmo canal do DataJud e do
  DJEN (spec 046), porque para quem administra o escritório é o mesmo tipo de aviso:
  "uma integração parou".
- **Cabeçalho do escritório não sobrescreve a assinatura.** O endpoint aceita headers
  customizados (token de API do destino, por exemplo), mas `X-Rito-Signature` e os outros
  três do protocolo são aplicados por último. Sem isso, um header configurado por engano
  desligaria a validação que a assinatura existe para dar.
- **O timestamp entra no que é assinado, não só num header ao lado.** Assinar apenas o
  corpo deixaria a mesma mensagem válida para sempre — quem capturasse um envio poderia
  reenviá-lo indefinidamente. A verificação é `compare_digest`, não `==`: comparação de
  string vaza o tamanho do prefixo comum pelo tempo, e assinatura conferida com `==` é
  assinatura conferida pela metade.
- **O reenvio usa o payload gravado, e é por isso que ele fica gravado.** Remontar a partir
  do estado atual mandaria dados diferentes dos do momento do evento — transformaria
  "reenviar" em "mandar outra coisa", que é justamente o que quebra a conciliação do outro
  lado.
- **A ação `http_request` não falha quando o destino responde erro.** Entrega é assíncrona
  por natureza: o n8n do escritório estar fora do ar não pode interromper a automação que
  já criou o prazo, e a entrega vai ser retentada de qualquer forma. Só configuração errada
  (endpoint inexistente ou desativado) reprova o passo — a diferença entre "não deu para
  entregar agora" e "isto nunca vai funcionar".
- **O contrato do payload virou teste de campo a campo.** As chaves são públicas: o n8n do
  escritório lê `task.title`, `lawsuit.customers[].identification`. Renomear uma quebra a
  integração de quem já ligou os fios, e um teste que comparasse só "tem as chaves
  principais" deixaria isso passar. `important`/`urgent` são da TAREFA no Rito e vêm por
  usuário no contrato do Flowter — replicamos o valor da tarefa em cada linha, que é o mais
  fiel possível sem inventar um campo que o produto não tem.

## 10. Definição de pronto

- [x] Checklist padrão
- [x] SSRF bloqueado em 3 caminhos — IP privado, HTTP externo e redirecionamento
- [x] Commit `feat(093): automação — webhooks outbound`
