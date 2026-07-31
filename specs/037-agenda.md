# 037 — Agenda

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +7 s
**Depende de:** 033 · **Status:** ⬜ pendente

---

## 1. Objetivo

Visualização em calendário e a **única integração externa de saída do produto**: feed iCal por
usuário para Google Agenda, Outlook e Apple Calendar.

## 2. Escopo

- Visões mês, semana, dia e lista
- Filtro por usuário e por data de compromisso vs prazo fatal
- Cores por status: pendente, concluída, atrasada
- **Feed iCal por usuário** com token secreto
- Criar tarefa clicando no dia

## 3. Fora de escopo

- Sincronização de entrada (é unidirecional, por decisão de produto)
- Pauta de audiências como relatório → 072

## 4. Modelo de dados

```sql
ALTER TABLE users ADD COLUMN ical_token TEXT UNIQUE;   -- gerado sob demanda
ALTER TABLE users ADD COLUMN ical_enabled BOOLEAN NOT NULL DEFAULT false;
```
Migration `037_ical.py`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/schedule?from=&to=&user_id=&date_field=scheduled\|deadline&show_completed=` | autenticado |
| POST | `/api/v1/schedule/ical/enable` | próprio usuário |
| POST | `/api/v1/schedule/ical/regenerate` | próprio usuário |
| GET | `/ical/{token}.ics` | **público por token** — fora de `/api/v1` |

## 6. Front-end

**Reutiliza:** `FilterBar`, `EmptyState`, `FormModal`
**Cria:** `CalendarPage`, `MonthView`, `WeekView`, `DayView`, `AgendaListView`,
`ICalSettingsCard`
**Rota:** `/schedules`

## 7. Regras de negócio

1. Só entram na agenda tarefas com `show_in_schedule = true` (na tarefa ou no tipo).
2. `date_field` alterna entre `scheduled_date` e `deadline_date` — muda o eixo do calendário.
3. Cores: pendente (neutro), concluída (verde), atrasada (vermelho). Atrasada = não concluída com data passada.
4. `all_day` ocupa a faixa do dia inteiro; com hora, ocupa o slot.
5. Feed iCal:
   - Token de 32 bytes, aleatório e único; a URL é secreta e o acesso é só por ela
   - Só tarefas do usuário com `show_in_schedule`
   - Cabeçalhos `X-PUBLISHED-TTL: PT1H` e `REFRESH-INTERVAL`
   - `UID` estável por tarefa — reprocessar não duplica no calendário
   - Regenerar invalida o token anterior imediatamente
   - Datas em UTC, respeitando o timezone da conta na conversão
   - Máximo de 12 meses para trás e 12 para frente
6. Sincronização é **unidirecional**. Alteração feita no Google não volta.
7. Clicar num dia abre o `TaskForm` com a data pré-preenchida.
8. Consulta limitada a 90 dias por requisição.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | mês, semana e dia retornam o intervalo certo | ~0,5 s |
| integração | `date_field` troca o eixo | ~0,3 s |
| integração | só tarefas com `show_in_schedule` | ~0,3 s |
| integração | intervalo acima de 90 dias → 422 | ~0,2 s |
| integração | **iCal é RFC 5545 válido** (parser de validação) | ~0,5 s |
| integração | `UID` estável entre duas gerações | ~0,3 s |
| integração | token inválido → 404 | ~0,2 s |
| integração | regenerar invalida o anterior | ~0,3 s |
| integração | iCal não vaza tarefa de outro usuário | ~0,4 s |
| integração | iCal respeita o timezone da conta | ~0,3 s |
| frontend | navegação entre visões | ~0,5 s |
| frontend | cores por status | ~0,3 s |
| frontend | clicar no dia abre o formulário | ~0,4 s |
| e2e | **jornada 6/25:** criar compromisso → ver no mês → abrir | ~4 s |

**Total:** ~8,5 s

> A validação do iCal usa a biblioteca `icalendar` para fazer o parse do que foi gerado —
> não confie em comparação de string.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · iCal validado por parser · Token secreto testado · Commit `feat(037): agenda`
