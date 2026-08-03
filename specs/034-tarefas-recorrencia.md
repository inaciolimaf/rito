# 034 — Tarefas: recorrência

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 033 · **Status:** ✅ concluída (2026-08-03)

---

## 1. Objetivo

Tarefas que se repetem — relatório mensal, reunião semanal, cobrança quinzenal. Oito
periodicidades e cinco modos de repetição no mês.

## 2. Escopo

- Tabela `post_recurrences`
- 8 periodicidades: diária, semanal, quinzenal, mensal, bimestral, trimestral, semestral, anual
- 5 modos: dia exato, 1ª / 2ª / 3ª / última semana do mês
- Geração da próxima ocorrência ao concluir
- Encerrar série
- Worker de segurança para ocorrências não geradas

## 3. Fora de escopo

- Recorrência financeira → 057 (regra diferente, não reutilize sem revisar)

## 4. Modelo de dados

```sql
CREATE TYPE recurrence_period AS ENUM
  ('DIARIA','SEMANAL','QUINZENAL','MENSAL','BIMESTRAL','TRIMESTRAL','SEMESTRAL','ANUAL');
CREATE TYPE recurrence_week AS ENUM
  ('DIA_EXATO','PRIMEIRA','SEGUNDA','TERCEIRA','ULTIMA');

CREATE TABLE post_recurrences (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  template_post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  period recurrence_period NOT NULL,
  repeat_on recurrence_week NOT NULL DEFAULT 'DIA_EXATO',
  until_date DATE,
  max_occurrences INTEGER,
  occurrences_created INTEGER NOT NULL DEFAULT 0,
  last_generated_date DATE,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE posts ADD COLUMN recurrence_id UUID REFERENCES post_recurrences(id);
CREATE INDEX ix_posts_recurrence ON posts (recurrence_id) WHERE recurrence_id IS NOT NULL;
```
Migration `034_post_recurrences.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/posts` passa a aceitar `recurrence: {period, repeat_on, until_date?, max_occurrences?}` |
| GET | `/api/v1/posts/{id}/recurrence` |
| PUT | `/api/v1/posts/{id}/recurrence` |
| DELETE | `/api/v1/posts/{id}/recurrence` — encerra a série, preserva o já gerado |
| GET | `/api/v1/posts/{id}/recurrence/preview?count=5` |

## 6. Front-end

**Reutiliza:** `FormModal`
**Cria:** `RecurrenceFields` (checkbox → periodicidade → modo → limite),
`RecurrencePreview` (mostra as 5 próximas datas)

## 7. Regras de negócio

1. A próxima ocorrência é gerada **ao concluir** a atual — não há geração antecipada em massa.
2. Worker diário de segurança gera ocorrências de séries ativas cuja data já passou sem conclusão.
3. `DIA_EXATO` em mês curto: dia 31 em fevereiro cai no **último dia do mês**, nunca em março.
4. `ULTIMA` semana resolve corretamente em meses de 4 e de 5 semanas — é a última ocorrência do dia da semana no mês.
5. Quinzenal = a cada 14 dias corridos, não "duas vezes por mês".
6. Série encerra por `until_date` ou `max_occurrences`, o que vier primeiro.
7. Encerrar a série não apaga as ocorrências já criadas.
8. Editar a recorrência afeta só as ocorrências futuras.
9. Cada ocorrência é um `post` independente, com seu próprio `reward_snapshot`.
10. Excluir a ocorrência atual não interrompe a série.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | **8 periodicidades: próxima data** (tabela) | ~0,3 s |
| unit | dia 31 → último dia de fevereiro | ~0,1 s |
| unit | `ULTIMA` semana em mês de 4 e de 5 semanas | ~0,2 s |
| unit | quinzenal = +14 dias | ~0,1 s |
| unit | ano bissexto no 29/02 anual | ~0,1 s |
| integração | concluir gera a próxima | ~0,4 s |
| integração | `until_date` encerra a série | ~0,3 s |
| integração | `max_occurrences` encerra a série | ~0,3 s |
| integração | encerrar preserva o já gerado | ~0,3 s |
| integração | editar afeta só o futuro | ~0,3 s |
| integração | worker gera atrasada sem duplicar | ~0,4 s |
| frontend | preview mostra 5 próximas | ~0,4 s |

**Total:** ~3,2 s

## 9. Descobertas

- **Gatilho da geração (regra 1):** a spec diz "ao concluir a atual" sem definir "atual"
  com conclusão POR RESPONSÁVEL (033). Decisão: a série só avança quando a tarefa fecha
  **como um todo** (todos os responsáveis — regra 3 da 033) E a ocorrência concluída é
  a **mais recente gerada** (`scheduled_date == last_generated_date`). Concluir uma
  atrasada depois que o worker adiantou a série não volta no tempo — a geração sempre
  parte de `last_generated_date`, nunca da data da ocorrência concluída.
- **Worker faz catch-up completo:** a varredura gera todas as ocorrências atrasadas até
  `last_generated_date >= hoje` (não uma por dia), com teto defensivo de 366 por
  varredura contra série diária abandonada há anos; o worker do dia seguinte continua.
  A guarda `series_date_exists` torna conclusão + worker idempotentes (nunca duas
  ocorrências na mesma data).
- **Clonagem do template:** `end_date`/`deadline_date` andam pelo mesmo delta da data do
  compromisso (ciclo relativo preservado); responsáveis, flags, local e descrição vêm do
  estado ATUAL do template (que é editável); `reward_snapshot` copiado do template (já
  congelado — regra 3 da 032 compõe com a regra 9 desta).
- **`posts.recurrence_id` com `ON DELETE SET NULL`:** excluir uma ocorrência (regra 10)
  nunca interrompe a série; se o template cair (CASCADE da série), as ocorrências
  geradas sobrevivem sem vínculo. `template_post_id` tem UNIQUE (uma série por template).
- **Preview no modal duplica a regra em TS de propósito:** o endpoint de preview exige
  um post salvo e o modal mostra as datas ANTES de criar. `features/posts/recurrence.ts`
  espelha `recurrence.py`; os testes das duas pontas usam os mesmos casos de borda
  (dia 31, última semana, 29/02). Aritmética em números + `Date.UTC` — `new Date(iso)`
  local andaria um dia para trás em fusos negativos.
- **`create_series` seta `updated_at` explícito:** o UPDATE do `recurrence_id` dispara o
  `onupdate` server-side e o atributo expira — leitura síncrona na resposta explode com
  MissingGreenlet (terceira reincidência da lição da 032; candidata a helper na 040).
- **Flakes de infra observados (não são da spec):** chave `login_attempts:*` do rate
  limit SEM TTL acumulando entre runs no Redis de teste (429 espúrio no
  `test_unknown_email_returns_same_generic_401` — investigar na 040); timeouts de 5 s em
  forms de customers/lawsuits sob contenção (passam isolados); backend 43,6 s isolado vs
  ~115 s concorrente com as 3 suítes num host de 4 cores.
- **Celery sem stubs:** `ignore_missing_imports` para `celery.*` no mypy + `type:
  ignore[untyped-decorator]` no task. O worker roda fora do caminho testado — a regra
  mora no `RecurrenceService.sweep_overdue`, exercitado direto (sem fila, sem broker).

## 10. Definição de pronto

- [x] Migration `034_post_recurrences` aplicada (tabela + RLS + enums + coluna em posts)
- [x] 8 periodicidades × 5 modos com casos de borda de calendário cobertos (17 unit)
- [x] Geração ao concluir (regra 1) e worker de segurança (regra 2) — integração
- [x] Limites `until_date`/`max_occurrences` (regra 6), DELETE preserva (regra 7),
  PUT afeta só o futuro (regra 8) — integração
- [x] Endpoints GET/PUT/DELETE/preview + `recurrence` no POST /posts
- [x] `RecurrenceFields` + `RecurrencePreview` no modal de nova tarefa (4 testes)
- [x] Isolamento de tenant na tabela nova (API 404 + RLS direto no banco)
- [x] `make lint` verde · `make test` verde em **83 s** (orçamento 120 s)
- [x] Commit `feat(034): tarefas — recorrência`
