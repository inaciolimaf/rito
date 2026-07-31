# 069 — Notificações

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 035 · **Status:** ⬜ pendente

---

## 1. Objetivo

Centralizar o roteamento de avisos: qual evento notifica quem, por qual canal. Hoje cada módulo
notifica do seu jeito — aqui vira infraestrutura única.

## 2. Escopo

- Configuração por evento com responsável ou "não notificar"
- Preferências por usuário e por canal
- Canais: in-app, e-mail e interfaces para SMS e WhatsApp
- Digest diário opcional
- Central de notificações no header
- Tela `Configurações > Notificações`

## 3. Fora de escopo

- Provider real de SMS/WhatsApp · Push mobile (fora do escopo)

## 4. Modelo de dados

```sql
CREATE TABLE notification_settings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  event_key TEXT NOT NULL,
  user_id UUID REFERENCES users(id),     -- NULL = não notificar
  UNIQUE (tenant_id, event_key)
);

CREATE TABLE user_notification_preferences (
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_key TEXT NOT NULL,
  in_app BOOLEAN NOT NULL DEFAULT true,
  email BOOLEAN NOT NULL DEFAULT false,
  sms BOOLEAN NOT NULL DEFAULT false,
  whatsapp BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY (user_id, event_key)
);

ALTER TABLE users
  ADD COLUMN daily_digest BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN digest_hour SMALLINT NOT NULL DEFAULT 8;

ALTER TABLE notifications
  ADD COLUMN event_key TEXT,
  ADD COLUMN channels_sent TEXT[] NOT NULL DEFAULT '{}';
```
RLS ligado. Migration `069_notifications_config.py`.

**Eventos** (`event_key`): `customer.created` · `lawsuit.created` · `publication.received` ·
`partner.shared` · `task.assigned` · `task.mentioned` · `task.deadline_near` ·
`transaction.overdue` · `sync.failed` · `ai.action_pending`

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET/PUT | `/api/v1/notification-settings` | GESTOR |
| GET/PUT | `/api/v1/me/notification-preferences` | próprio usuário |
| GET | `/api/v1/notifications?unread=&cursor=` | autenticado |
| POST | `/api/v1/notifications/{id}/read` · `/read-all` | autenticado |

## 6. Front-end

**Reutiliza:** `FormModal`, `DataTable`, `EmptyState`
**Cria:** `NotificationSettingsForm` (matriz evento × responsável),
`UserPreferencesMatrix` (evento × canal), `NotificationCenter` (dropdown no header),
`DigestSettings`
**Rotas:** `/settings/notifications`, `/settings/me/notifications`

## 7. Regras de negócio

1. Dois níveis: o **tenant** define quem recebe cada evento; o **usuário** define por quais canais.
2. `user_id = NULL` na configuração do tenant significa "não notificar ninguém" — o evento é ignorado.
3. Eventos de destinatário implícito (menção, atribuição, prazo) vão para o envolvido, ignorando a configuração do tenant.
4. Canal in-app é sempre entregue; os demais dependem da preferência do usuário.
5. Canal sem contato cadastrado é pulado, com o motivo registrado em `channels_sent`.
6. Digest diário agrupa o não lido e envia um e-mail no horário configurado, no timezone da conta.
7. Com digest ligado, o e-mail individual é suprimido, exceto para eventos críticos (`sync.failed`, `task.deadline_near`).
8. Notificação in-app é retida por 90 dias.
9. Envio é assíncrono; falha em um canal não impede os outros.
10. Deduplicação: o mesmo evento para o mesmo usuário em 5 minutos gera uma notificação só.
11. Canais atrás de `NotificationChannel`; sem provider, o envio vira no-op registrado.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | configuração do tenant roteia o evento | ~0,4 s |
| integração | `user_id = NULL` ignora o evento | ~0,2 s |
| integração | menção ignora a configuração do tenant | ~0,3 s |
| integração | preferência do usuário filtra canais | ~0,4 s |
| integração | in-app sempre entregue | ~0,2 s |
| integração | canal sem contato é pulado com motivo | ~0,3 s |
| integração | digest agrupa e suprime individuais | ~0,4 s |
| integração | evento crítico fura o digest | ~0,3 s |
| integração | deduplicação em 5 min | ~0,3 s |
| integração | falha em um canal não afeta os outros | ~0,3 s |
| integração | digest respeita o timezone da conta | ~0,3 s |
| frontend | matriz de preferências | ~0,4 s |
| frontend | central mostra não lidas e marca todas | ~0,4 s |

**Total:** ~4,2 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Dois níveis de configuração testados · Commit `feat(069): notificações`
