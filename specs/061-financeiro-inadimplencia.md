# 061 — Financeiro: inadimplência

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 059 · **Status:** ✅ concluída

---

## 1. Objetivo

Honorário atrasado que ninguém cobra vira prejuízo. Esta spec identifica o atraso e monta a
régua de cobrança automática.

## 2. Escopo

- Identificação de atrasados com faixas de aging
- Régua de cobrança configurável por marcos
- Envio por e-mail (adapters de SMS e WhatsApp atrás de interface, sem provider real)
- Registro de cada tentativa
- Painel de inadimplência por cliente

## 3. Fora de escopo

- Provider real de SMS/WhatsApp (interface pronta, implementação fora do escopo)
- Boleto e cartão — o Rito não integra gateway de pagamento

## 4. Modelo de dados

```sql
CREATE TABLE dunning_rules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  days_offset SMALLINT NOT NULL,      -- negativo = antes do vencimento
  channel TEXT NOT NULL,              -- 'email' | 'sms' | 'whatsapp'
  template TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  UNIQUE (tenant_id, days_offset, channel)
);

CREATE TABLE dunning_attempts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
  rule_id UUID REFERENCES dunning_rules(id),
  channel TEXT NOT NULL,
  sent_to TEXT NOT NULL,
  status TEXT NOT NULL,               -- 'sent' | 'failed' | 'skipped'
  error TEXT,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (transaction_id, rule_id)
);
CREATE INDEX ix_dunning_tx ON dunning_attempts (transaction_id, sent_at DESC);
```
RLS nas duas. Migration `061_dunning.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/transactions/overdue?aging=&customer_id=&cursor=` | financial ≥ READ_ONLY |
| GET | `/api/v1/transactions/overdue/summary` | financial ≥ READ_ONLY |
| GET/PUT | `/api/v1/dunning-rules` | financial = FULL |
| POST | `/api/v1/transactions/{id}/dunning/send` | financial = FULL — manual |
| GET | `/api/v1/transactions/{id}/dunning/attempts` | financial ≥ READ_ONLY |

## 6. Front-end

**Reutiliza:** `DataTable`, `StatCard`, `FilterBar`, `ConfirmDialog`
**Cria:** `OverduePanel`, `AgingChart`, `DunningRulesForm`, `DunningHistoryDrawer`,
`TemplateEditor` (com variáveis)
**Rota:** `/transactions?tab=overdue`

## 7. Regras de negócio

1. Atrasado = `due_date < hoje`, `payment_date IS NULL`, `NOT is_internal`, tipo RECEITA.
2. Faixas de aging: 1–15, 16–30, 31–60, 61–90, 90+ dias.
3. Régua dispara por `days_offset` relativo ao vencimento. Negativo = lembrete antes.
4. **Uma tentativa por regra por lançamento** (`UNIQUE`) — não há cobrança repetida da mesma régua.
5. Cliente sem o contato do canal (sem e-mail, por exemplo) gera tentativa com `status = skipped` e motivo — silêncio nunca.
6. Baixa do lançamento cancela as réguas futuras dele.
7. Template aceita variáveis: nome do cliente, valor, vencimento, dias de atraso, número do processo, nome do escritório.
8. Envio manual é sempre permitido, mesmo que a régua já tenha rodado, e fica registrado como manual.
9. Canais SMS e WhatsApp ficam atrás de `MessagingChannel`; sem provider configurado, geram `skipped` com motivo — não quebram o fluxo.
10. Worker diário processa as réguas do dia; falha em um lançamento não afeta os outros.
11. Resumo mostra total atrasado, por faixa e os 10 maiores devedores.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | atrasados excluem interno, pago e despesa | ~0,4 s |
| integração | faixas de aging (tabela parametrizada) | ~0,4 s |
| integração | régua dispara no offset certo | ~0,4 s |
| integração | lembrete antes do vencimento (offset negativo) | ~0,3 s |
| integração | **mesma régua não dispara duas vezes** | ~0,4 s |
| integração | sem canal → `skipped` com motivo | ~0,3 s |
| integração | baixa cancela réguas futuras | ~0,3 s |
| integração | variáveis do template resolvem | ~0,3 s |
| integração | envio manual sempre permitido e registrado | ~0,3 s |
| integração | canal sem provider → `skipped`, sem quebrar | ~0,3 s |
| integração | falha em um não afeta os outros | ~0,3 s |
| frontend | painel de aging | ~0,4 s |

**Total:** ~4,1 s
E-mail sempre mockado.

## 9. Descobertas

- Nenhuma integração de e-mail existia no código antes desta spec. Criada
  `app/integrations/messaging/` com `MessagingChannel` (Protocol, DIP) e três
  implementações: `SmtpEmailChannel` (stdlib `smtplib`, síncrono envolto em
  `asyncio.to_thread`, mesmo padrão de `S3FileStorage.upload`), `SmsChannel` e
  `WhatsAppChannel` (regra 9: sempre `ChannelNotConfiguredError`, sem provider real —
  fora de escopo por definição da spec). `SMTP_HOST/PORT/USER/PASSWORD/FROM` já
  existiam em `.env`/`.env.example` desde a spec 002 (nunca usados até agora) —
  `Settings` foi alinhada a esses nomes em vez de inventar novos.
- `rule_id NULL` faz dupla função: marca a tentativa como manual (`is_manual` computado
  na resposta) e nunca colide com a `UNIQUE(transaction_id, rule_id)` — Postgres trata
  `NULL` como distinto, então réguas automáticas e envios manuais nunca disputam a
  mesma constraint (regra 4 × regra 8, desenho documentado no docstring da migration).
- `run_daily_rules` retorna a contagem de **tentativas processadas** (SENT + FAILED),
  não só sucessos — `SKIPPED`/`FAILED` também contam como "processado", já que a régua
  não pode ficar tentando de novo no dia seguinte (regra 4 é por régua, não por
  status). Isso pegou um teste errado (`test_falha_em_um_nao_afeta_os_outros` esperava
  `sent == 1`, o correto é `2`) — corrigido no próprio teste, não é bug de produção.
- `components/domain/BarChart.tsx` ganhou `formatValue?: (value: number) => string`
  (default `String`, comportamento anterior preservado) para `AgingChart` poder
  formatar em R$ sem duplicar a barra SVG — mantém a regra dos 3 usos em vez de criar
  um segundo componente de barra só pra dinheiro.
- Smoke test manual em navegador (tenant descartável, fora do tenant e2e para não
  poluir jornadas existentes): criado lançamento vencido, régua e envio manual real
  contra `smtplib` sem servidor SMTP disponível — o backend registrou corretamente
  `FAILED` com `[Errno 111] Connection refused`, e o histórico mostrou o erro sem
  quebrar a tela. Confirma regra 10 (falha de provider vira `DunningAttempt`, não
  exceção) também pela borda real de rede, não só pelo dublê de teste.

## 10. Definição de pronto

Checklist padrão · Nenhuma cobrança duplicada · Commit `feat(061): financeiro — inadimplência`

- [x] Migration `061_dunning.py` (RLS nas duas tabelas, `UNIQUE`s conforme §4)
- [x] `MessagingChannel` (email real, SMS/WhatsApp sempre skip) atrás de interface
- [x] Endpoints do contrato §5 com RBAC financeiro correto
- [x] `OverduePanel`, `AgingChart`, `DunningRulesForm`, `DunningHistoryDrawer`,
      `TemplateEditor` — reaproveitando `DataTable`/`StatCard`/`FilterBar`/`FormModal`
- [x] Worker diário (`app/workers/dunning.py`) registrado no beat, isolando falha por
      tenant e por lançamento
- [x] 18 testes backend (13 integração + 5 unidade) + 2 frontend — todos os 11 casos
      do plano de testes cobertos
- [x] `make test`: 880 backend, 159 frontend, 10 e2e — wall-clock 134s (orçamento 300s)
- [x] `make lint`: ruff + mypy + eslint + tsc limpos
- [x] Smoke manual em navegador confirmando o fluxo ponta a ponta
