# 073 — Registro de acessos e livro de ponto

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 012 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Rastreamento desligado por padrão · Commit `feat(073): registro de acessos e livro de ponto`
