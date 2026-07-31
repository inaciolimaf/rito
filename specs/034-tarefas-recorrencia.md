# 034 — Tarefas: recorrência

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 033 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Casos de borda de calendário cobertos · Commit `feat(034): tarefas — recorrência`
