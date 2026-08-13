# 069 — Notificações

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 035 · **Status:** ✅ concluída

---

## 1. Objetivo

A notificação in-app já existe (spec 035, só menção). Esta spec generaliza: um evento
do sistema (novo cliente, novo processo, intimação) tem um responsável configurável
e pode disparar e-mail/SMS/WhatsApp além do sino, respeitando o que cada usuário
desligou pra si.

## 2. Escopo

- Config por evento: `NOVO_CLIENTE`, `NOVO_PROCESSO`, `INTIMACAO` — responsável (ou
  "não notificar") + quais canais além do in-app.
- Preferência por usuário: ligar/desligar cada canal pra si (aplica a todo evento —
  o levantamento não pede granularidade por evento, só "preferências por usuário").
- `NotificationDispatcher`: ponto único de disparo — resolve a regra, cria a
  notificação in-app, manda pelos canais configurados respeitando a preferência.
- Ligado aos 3 gatilhos reais que já existem no sistema: criar contato (017), criar
  processo (022), publicação roteada — automática (044/045) e manual (045).

## 3. Fora de escopo

- Evento "parceiros" — o levantamento cita, mas o módulo de parceiros é a spec 079,
  ainda não existe; catálogo de evento fica com os 3 que têm gatilho real hoje. Um 4º
  evento entra quando a 079 chegar, sem precisar tocar `NotificationDispatcher`.
- Preferência por evento (ex.: "email só pra novo processo, não pra intimação") — o
  levantamento pede só "preferências por usuário", não uma matriz usuário×evento.
- SMS/WhatsApp com provider real — mesma interface sem implementação real da spec
  061 (`ChannelNotConfiguredError`, silencioso no disparo, nunca quebra o evento).

## 4. Modelo de dados

```sql
CREATE TABLE notification_rules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  event TEXT NOT NULL,                    -- 'NOVO_CLIENTE' | 'NOVO_PROCESSO' | 'INTIMACAO'
  responsible_user_id UUID REFERENCES users(id),  -- NULL = "não notificar"
  channels TEXT[] NOT NULL DEFAULT '{}',  -- subconjunto de 'EMAIL'/'SMS'/'WHATSAPP'
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, event)
);

CREATE TABLE user_notification_preferences (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID NOT NULL REFERENCES users(id),
  channel TEXT NOT NULL,                  -- 'EMAIL' | 'SMS' | 'WHATSAPP'
  enabled BOOLEAN NOT NULL DEFAULT true,
  UNIQUE (tenant_id, user_id, channel)
);
```
RLS nas duas. Migration `069_notification_rules.py`.

## 5. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| GET | `/api/v1/notification-rules` | — | `200 [{event, responsible_user_id, channels}]` (as 3, sempre) | Gestor |
| PUT | `/api/v1/notification-rules/{event}` | `{responsible_user_id?, channels}` | `200 rule` | Gestor |
| GET | `/api/v1/notification-preferences` | — | `200 [{channel, enabled}]` | autenticado (só as próprias) |
| PUT | `/api/v1/notification-preferences/{channel}` | `{enabled}` | `200 preference` | autenticado |

Erros: `422` (evento/canal fora dos valores aceitos).

## 6. Front-end

**Componentes reutilizados:** `EntityPicker` (escolher responsável).
**Componentes criados:** nenhum — a tela é um formulário simples por evento/canal,
mesmo padrão de outras telas de configuração desta fase.
**Rota:** `/settings/notifications` — regras (Gestor) + preferências (qualquer
usuário) na mesma tela, sem aba (não é volume o bastante pra justificar).
**Estados:** loading, salvando, erro.

## 7. Regras de negócio

1. Sem regra configurada para o evento → nada acontece (nem in-app, nem canal) —
   config é opt-in, mesmo espírito do roteamento de intimação (spec 045: sem termo/
   grupo configurado, não routea).
2. `responsible_user_id = NULL` é "não notificar" explícito — mesmo efeito da regra 1,
   mas é um estado configurado (a regra existe, só que desligada), não ausência de
   config.
3. Notificação in-app sempre acontece quando há responsável (regra do sino, spec 035)
   — os canais extras (`channels`) são complemento, nunca substituem o in-app.
4. Canal listado na regra só dispara se a preferência do usuário responsável pra
   aquele canal estiver ligada (regra 7 — default ligado, sem registro).
5. Canal sem `to` resolvível (e-mail vazio pro canal EMAIL, celular vazio pro canal
   SMS/WHATSAPP) ou sem provider configurado nunca quebra o evento que disparou —
   best-effort, mesmo padrão da spec 061 regra 9.
6. Os 3 gatilhos (criar contato, criar processo, publicação roteada — automática e
   manual) disparam o dispatcher depois que o registro principal já foi criado, na
   mesma transação — falha no disparo de notificação nunca desfaz a criação do
   contato/processo/roteamento.
7. Preferência sem registro é tratada como habilitada (regra 4) — o usuário só
   aparece na tabela quando desliga algo, não precisa de seed.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | sem regra configurada → nenhuma notificação | `tests/integration/test_notification_dispatch.py` | ~0,3 s |
| integração | regra com responsável e canal EMAIL → in-app + e-mail (mailer fake, padrão `test_dunning.py`) | idem | ~0,3 s |
| integração | `responsible_user_id = NULL` ("não notificar") → nada | idem | ~0,2 s |
| integração | preferência desligada pro canal → só in-app, sem canal | idem | ~0,3 s |
| integração | canal sem provider → segue sem quebrar (best-effort) | idem | ~0,2 s |
| integração | criar contato dispara `NOVO_CLIENTE` quando configurado | `tests/integration/test_customers.py` (novo caso) | ~0,3 s |
| integração | criar processo dispara `NOVO_PROCESSO` quando configurado | `tests/integration/test_lawsuits.py` (novo caso) | ~0,3 s |
| integração | publicação roteada (manual) dispara `INTIMACAO` | `tests/integration/test_publications.py` (novo caso) | ~0,3 s |
| integração | CRUD de regras (Gestor) e preferências (usuário) | `tests/integration/test_notification_rules.py` | ~0,4 s |

**Total estimado:** ~2,6 s
**Fixtures externas:** nenhuma — mailer/canais sempre injetados fake nos testes.

## 9. Descobertas

`NotificationDispatcher` centraliza a regra 1-5 num único ponto (resolve a regra →
notifica in-app → tenta os canais respeitando a preferência, sempre
`contextlib.suppress(Exception)` por canal). Os 3 gatilhos reais threadeiam um
`channels: Mapping[str, MessagingChannel] | None = None` opcional através da cadeia de
quem já existia — `CustomerService`/`LawsuitService` não mudaram, o disparo entra no
router (mesmo padrão de `invalidate_stats_cache` em `lawsuits/router.py`) logo depois do
`session.flush()` que persiste o registro principal, então falha no disparo nunca desfaz
a criação; `PublicationRoutingService` ganhou o dispatcher no `__init__` porque o disparo
acontece dentro de `_apply` (regra 6: só quando a tarefa é criada de fato), e o parâmetro
`channels` propaga por `PublicationRoutingService` → `TermSyncService` →
`workers/djen_sync.py` (que já montava `create_messaging_channels()` no padrão do worker
de cobrança, `workers/dunning.py`) e pelos 3 endpoints do router de publicações
(import/link/reprocess). Em teste, `SmtpEmailChannel`/`SmsChannel`/`WhatsAppChannel`
reais (sem SMTP_HOST configurado em `.env`) bastam para exercitar o caminho best-effort
via HTTP real (`ChannelNotConfiguredError` é engolida pelo dispatcher) — só o teste do
dispatcher em si usa um `FakeEmailChannel`/`BrokenChannel` dedicado, mesmo padrão de
`test_dunning.py`.

O teste do gatilho de `INTIMACAO` foi colocado em `test_publication_routing.py` (não em
`test_publications.py` como o plano original previa) — é lá que já existem os helpers de
`RoutingSetup`/`make_publication`/`route()` usados pelas outras 15 variações de
casamento/roteamento, então reaproveitar em vez de duplicar infraestrutura de setup em um
arquivo novo. Wall-clock do gate cheio ficou em 293 s (orçamento 300 s, 7 s de folga) —
dentro do previsto pelo orçamento declarado de +4 s frente aos 862 s medidos após a 070.

Front-end: sem componente novo, como previsto no §6 — `EntityPicker` reusado para
escolher o responsável por evento, `Checkbox` de shadcn (primeiro uso no projeto) para os
3 canais por regra e as 3 preferências do usuário. Rota `/settings/notifications`
adicionada sem entrada em `navItems.ts` (a lista de 15 itens da sidebar é fixa, mesmo
padrão de `/settings/goals` e `/settings/monitored-terms`, que também não têm entrada
própria) — alcançável só por URL direta até uma futura tela-índice de Configurações.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] `make test` verde e wall-clock < 300 s
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(069): notificações`
