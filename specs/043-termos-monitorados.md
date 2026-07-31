# 043 — Termos monitorados

**Fase:** 4 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 042 · **Status:** ⬜ pendente

---

## 1. Objetivo

O que o escritório quer vigiar: OAB, CPF ou CNPJ. Cada termo vira uma consulta periódica ao
DJEN. Sem termo cadastrado, não há captura.

## 2. Escopo

- Tabela `monitored_terms`
- CRUD com validação por tipo
- Vínculo opcional a usuário responsável
- Status de monitoramento
- Histórico de sincronização
- Tela `Configurações > Termos monitorados`

## 3. Fora de escopo

- Execução da sincronização → 044 · Painel de status → 049
- Certificado A1 e QR Code — **não existem no Rito**, por decisão de arquitetura

## 4. Modelo de dados

```sql
CREATE TYPE term_kind AS ENUM ('OAB','CPF','CNPJ');
CREATE TYPE term_status AS ENUM ('PENDENTE','SINCRONIZANDO','ATIVO','FALHA','PAUSADO');

CREATE TABLE monitored_terms (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  kind term_kind NOT NULL,
  value TEXT NOT NULL,                    -- OAB: só números; CPF/CNPJ: só dígitos
  oab_state CHAR(2) REFERENCES states(code),   -- obrigatório se kind=OAB
  label TEXT,
  user_id UUID REFERENCES users(id),      -- responsável padrão pelas intimações do termo
  status term_status NOT NULL DEFAULT 'PENDENTE',
  status_message TEXT,
  last_sync_at TIMESTAMPTZ,
  last_success_at TIMESTAMPTZ,
  next_sync_at TIMESTAMPTZ,
  backfill_from DATE,                     -- janela inicial de captura
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, kind, value, oab_state),
  CHECK (kind <> 'OAB' OR oab_state IS NOT NULL)
);
CREATE INDEX ix_terms_due ON monitored_terms (next_sync_at)
  WHERE is_active AND status <> 'PAUSADO';

CREATE TABLE term_sync_runs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  term_id UUID NOT NULL REFERENCES monitored_terms(id) ON DELETE CASCADE,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  found_count INTEGER NOT NULL DEFAULT 0,
  new_count INTEGER NOT NULL DEFAULT 0,
  error TEXT
);
CREATE INDEX ix_sync_runs_term ON term_sync_runs (term_id, started_at DESC);
```
RLS nas duas. Migration `043_monitored_terms.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/monitored-terms?status=&kind=&q=` | ADMINISTRADOR |
| POST/PUT/DELETE | `/api/v1/monitored-terms[/{id}]` | GESTOR |
| POST | `/api/v1/monitored-terms/{id}/sync` | ADMINISTRADOR — sync manual |
| POST | `/api/v1/monitored-terms/{id}/pause` · `/resume` | GESTOR |
| GET | `/api/v1/monitored-terms/{id}/runs?cursor=` | ADMINISTRADOR |

## 6. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `FilterBar`, `ConfirmDialog`, `EmptyState`
**Cria:** `MonitoredTermForm` (tipo → campos condicionais), `TermStatusBadge`, `SyncRunsTable`
**Rota:** `/settings/monitored-terms`

Colunas: Termo · Tipo · Responsável · Status · Última sincronização · Capturadas

## 7. Regras de negócio

1. `kind = OAB` exige `oab_state` (constraint) e número só com dígitos.
2. `kind = CPF/CNPJ` valida com o algoritmo real (reusa 018).
3. Termo duplicado no tenant → 409. A mesma OAB pode existir em outro tenant.
4. `user_id` define o responsável padrão das intimações daquele termo; vazio cai na regra de grupo de ação (045).
5. Termo nasce `PENDENTE`; a primeira sincronização o move para `ATIVO` ou `FALHA`.
6. `backfill_from` limita a captura inicial. Padrão: 30 dias atrás. Máximo: 12 meses.
7. Pausar interrompe o agendamento sem apagar o histórico.
8. Excluir termo **não** apaga as publicações já capturadas.
9. `next_sync_at` é calculado após cada execução (diário, conforme `DJEN_SYNC_CRON`).
10. Sync manual respeita o rate limit e não pode rodar se já houver execução em andamento → 409.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD dos 3 tipos | ~0,5 s |
| integração | OAB sem UF → 422 | ~0,2 s |
| integração | CPF inválido → 422 | ~0,2 s |
| integração | duplicado no tenant → 409 | ~0,3 s |
| integração | mesmo termo em outro tenant é aceito | ~0,3 s |
| integração | `backfill_from` acima de 12 meses → 422 | ~0,2 s |
| integração | pausar impede o agendamento | ~0,3 s |
| integração | excluir termo preserva publicações | ~0,3 s |
| integração | sync manual concorrente → 409 | ~0,3 s |
| integração | Colaborador → 403 | ~0,2 s |
| frontend | formulário alterna campos por tipo | ~0,4 s |
| frontend | badge reflete os 5 status | ~0,3 s |

**Total:** ~3,5 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(043): termos monitorados`
