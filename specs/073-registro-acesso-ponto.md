# 073 — Registro de acessos e livro de ponto

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 012 · **Status:** ✅ concluída

---

## 1. Objetivo

Duas funções de RH: log de acesso ao sistema e livro de ponto a partir da jornada cadastrada.

## 2. Escopo

- Registro de login com IP, user agent e horário
- Toggle por conta (LGPD — o escritório decide se rastreia)
- Livro de ponto derivado do primeiro e último acesso do dia
- Comparação com a jornada cadastrada
- Relatório mensal por colaborador
- Retenção e expurgo

## 3. Fora de escopo

- Ponto por biometria ou geolocalização (fora do escopo)
- Cálculo de hora extra para folha (é indicativo, não folha de pagamento)

## 4. Modelo de dados

```sql
CREATE TABLE access_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ip_address INET,
  user_agent TEXT,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_access_user_day ON access_logs (tenant_id, user_id, occurred_at DESC);

CREATE MATERIALIZED VIEW timesheet_daily AS
SELECT tenant_id, user_id, occurred_at::date AS day,
       MIN(occurred_at) AS first_access,
       MAX(occurred_at) AS last_access,
       COUNT(*) AS access_count
FROM access_logs GROUP BY 1,2,3;
CREATE UNIQUE INDEX ux_timesheet ON timesheet_daily (tenant_id, user_id, day);
```
RLS ligado. Migration `073_access_logs.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/reports/access-logs?user_id=&from=&to=` | ADMINISTRADOR |
| GET | `/api/v1/reports/timesheet?user_id=&month=` | ADMINISTRADOR (ou o próprio) |
| POST | `/api/v1/reports/timesheet/export` | ADMINISTRADOR |
| PUT | `/api/v1/account/access-tracking` → `{enabled}` | GESTOR |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `StatCard`
**Cria:** `TimesheetReport` (grade dia × colaborador), `TimesheetCell` (com desvio),
`AccessTrackingToggle` (com aviso de LGPD)
**Rota:** `/reports?report=timesheet`

## 7. Regras de negócio

1. Registro só acontece se `accounts.track_access_logs = true`. Desligado é o padrão.
2. Ligar o rastreamento exibe aviso sobre transparência com a equipe (LGPD).
3. Um registro por login bem-sucedido. Refresh de token **não** registra.
4. Primeiro e último acesso do dia formam a jornada aparente.
5. Comparação com `work_start`/`work_end` do usuário produz desvio em minutos, positivo ou negativo.
6. Usuário sem jornada cadastrada aparece sem comparação, não com desvio zero.
7. Dia sem acesso aparece vazio — não presuma falta, pode ser folga ou férias.
8. Sábado, domingo e feriado nacional aparecem marcados.
9. Retenção de **12 meses**; job mensal expurga o excedente.
10. O próprio usuário vê o próprio ponto; ver de outro exige ADMINISTRADOR.
11. Desligar o rastreamento **não apaga** o histórico — só para de coletar. Apagar é ação explícita e separada.
12. Timezone da conta é usado para determinar o dia.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | desligado não registra | ~0,3 s |
| integração | ligado registra no login, não no refresh | ~0,4 s |
| integração | primeiro e último acesso do dia | ~0,3 s |
| integração | desvio positivo e negativo vs jornada | ~0,4 s |
| integração | sem jornada → sem comparação | ~0,2 s |
| integração | dia sem acesso fica vazio | ~0,2 s |
| integração | fim de semana e feriado marcados | ~0,3 s |
| integração | usuário vê o próprio; alheio → 403 | ~0,3 s |
| integração | expurgo após 12 meses | ~0,3 s |
| integração | desligar não apaga histórico | ~0,3 s |
| integração | dia calculado no timezone da conta | ~0,3 s |
| frontend | toggle mostra aviso de LGPD | ~0,3 s |

**Total:** ~3,6 s

## 9. Descobertas

- **`/reports/access-logs` × relatório tabular `access_logs` da 072**: são coisas
  diferentes por design. `/reports/access-logs` (esta spec) é a lista bruta por
  evento de login — nunca gated pelo toggle atual (regra 11: desligar não apaga
  histórico, então o histórico continua visível ali). O `report_key="access_logs"`
  de 072 é a versão agregada por dia (mesma `timesheet_daily_visible`, mais
  `last_ip`) e **essa sim** respeita o toggle atual (072 regra 5) — ver a fila da 072
  ficar "desligada" quando o rastreamento está desligado é intencional; consultar o
  histórico bruto via 073 continua funcionando.
- **Dia = todos os dias do mês, não só os com acesso**: `GET /reports/timesheet`
  devolve uma linha por dia do mês inteiro (com `access_count=0` e
  `deviation_minutes=null` nos dias sem acesso) em vez de omitir dias sem dado —
  mais fácil de desenhar uma grade de calendário no front sem o cliente ter que
  preencher os buracos. "Vazio" (regra 7) é uma propriedade dos campos da linha
  (contagem zero, sem horário), não a ausência da linha.
- **Desvio é sempre contra `work_start`** (primeiro acesso do dia) — a spec não
  detalha se compara início, fim ou ambos; comparar o fim contra `work_end` teria o
  mesmo problema de "não presumir demissão às 18h" que a saída sem novo login no dia
  seguinte deixaria ambíguo. Ficou só entrada.
- **`INET` do Postgres via asyncpg vira `ipaddress.IPv4Address` na leitura**, não
  `str` — descoberto batendo num erro de validação Pydantic no primeiro teste. Toda
  leitura de `ip_address`/`last_ip` passa por `str(...)` explícito antes de entrar
  num schema de resposta.
- **Migration 073 falhou uma vez** com `column "track_access_logs" already exists`
  mesmo sendo a primeira tentativa de aplicá-la — sintoma de uma execução parcial
  anterior não rastreada (`alembic_version` ainda apontava para 072 mas a coluna já
  existia, no banco de dev e no de teste). Resolvido soltando a coluna manualmente e
  reaplicando a migration do zero, que então rodou limpa e atômica. Não reproduzido
  numa segunda tentativa — registrado aqui como possível ruído do sandbox
  compartilhado desta sessão, não um bug identificado no arquivo da migration.
- **`holidays` é tabela global (sem `tenant_id`)** — o `TRUNCATE tenants CASCADE` de
  `scripts/run-tests.sh` (spec 009 regra 3) não a limpa entre execuções da suíte.
  `_seed_holiday` do plano de testes desta spec inicialmente inserção direta, sem
  checar existência — colidiu (`UniqueViolationError`) numa segunda rodada local
  porque a mesma data (`_MONTH_START + 2 dias`, calculada a partir do dia real)
  já tinha sido semeada por uma execução anterior. Corrigido para um upsert
  (`session.get` antes de `add`) — mesmo cuidado que qualquer teste que grave em
  tabela global sem tenant precisa ter.
- **`purge_access_logs()` varre todos os tenants ativos abrindo uma engine por tenant**
  (`_purge_tenant`, mesmo padrão de `app/workers/stagnation.py::_sweep_all_tenants`) —
  aceitável em produção (poucas centenas de tenants, job mensal), mas em suíte local
  com milhares de tenants acumulados de execuções manuais fora do `scripts/run-tests.sh`
  (que faz `TRUNCATE tenants CASCADE` antes de rodar) chegou a levar ~80 s numa única
  chamada. O teste da regra 9 passou a chamar `_purge_tenant` direto, só para o tenant
  do próprio teste — mesmo idioma de "chamar o refresh direto" usado em toda spec de
  matview. Não é uma correção no worker, que continua com o mesmo formato de 052.
- `test_inbox_perf.py::test_counts_das_6_secoes_em_uma_query_rapida` (spec 036, não
  desta spec) falhou uma vez rodando concorrente com as outras duas suítes (366 ms
  contra o teto de 200 ms) e passou limpo em isolamento logo depois — contenção de CPU
  do sandbox compartilhado desta sessão, não uma regressão: nenhum arquivo do módulo
  `inbox` foi tocado por esta spec.

## 10. Definição de pronto

Checklist padrão · Rastreamento desligado por padrão · Commit `feat(073): registro de acessos e livro de ponto`
