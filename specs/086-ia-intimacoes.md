# 086 — IA em intimações

**Fase:** 8 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 085, 045 · **Status:** ⬜ pendente

---

## 1. Objetivo

A aplicação de IA com maior retorno do produto e também a de maior risco: ler a intimação,
resumir, classificar o ato, **calcular o prazo** e sugerir a tarefa. Resolve a dívida que a
spec 045 deixou aberta de propósito.

## 2. Escopo

- Resumo objetivo da publicação
- Classificação do tipo de ato processual
- **Cálculo de prazo** em dias úteis, com feriados
- Sugestão de tarefa com responsável e data
- Leitura automática opcional
- Revisão humana obrigatória do prazo

## 3. Fora de escopo

- Peticionamento automático · Agentes de petição → 087

## 4. Modelo de dados

```sql
CREATE TABLE publication_analyses (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  publication_id UUID NOT NULL UNIQUE REFERENCES publications(id) ON DELETE CASCADE,
  summary TEXT NOT NULL,
  act_type TEXT,                       -- 'sentenca' | 'despacho' | 'intimacao_prazo' | ...
  requires_action BOOLEAN NOT NULL DEFAULT false,
  deadline_days SMALLINT,              -- prazo identificado
  deadline_kind TEXT,                  -- 'uteis' | 'corridos'
  deadline_date DATE,                  -- calculado
  deadline_confidence NUMERIC(3,2),    -- 0..1
  suggested_task_type_id UUID REFERENCES task_types(id),
  suggested_user_id UUID REFERENCES users(id),
  reasoning TEXT,
  model TEXT NOT NULL,
  reviewed_by UUID REFERENCES users(id),
  reviewed_at TIMESTAMPTZ,
  human_correction JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_pub_analyses_review ON publication_analyses (tenant_id, created_at DESC)
  WHERE reviewed_at IS NULL;

ALTER TABLE accounts ADD COLUMN ai_auto_read_publications BOOLEAN NOT NULL DEFAULT false;
```
RLS ligado. Migration `086_publication_analyses.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/publications/{id}/analyze` |
| GET | `/api/v1/publications/{id}/analysis` |
| POST | `/api/v1/publications/{id}/analysis/review` → `{deadline_date?, task_type_id?, user_id?, approved}` |
| PUT | `/api/v1/account/ai-settings` → `{ai_auto_read_publications}` |

## 6. Front-end

**Reutiliza:** `PublicationDetailDrawer`, `AIActionPreview`, `ConfirmDialog`
**Cria:** `PublicationAnalysisCard` (resumo, tipo, prazo, confiança),
`DeadlineReviewField` (data calculada, editável, com o raciocínio ao lado),
`ConfidenceBadge`, `AutoReadToggle`
**Rota:** dentro de `/publications`

## 7. Regras de negócio

1. **O prazo calculado é sempre sugestão.** Nunca vira `deadline_date` da tarefa sem revisão humana. A UI deixa isso explícito: "prazo sugerido pela IA — confirme".
2. Cálculo usa `app/core/dates.py` (040): dias úteis, pulando fim de semana e feriado nacional, a partir de `availability_date` **+ 1 dia útil** (a contagem começa no dia seguinte à publicação).
3. `deadline_kind` distingue prazo em dias úteis (regra do CPC) de dias corridos, quando o texto indicar.
4. `deadline_confidence` abaixo de **0,8** exibe alerta reforçado e não pré-preenche o campo.
5. Publicação sem prazo identificado → `requires_action = false`, sem sugestão de data. Não invente prazo.
6. O resumo tem no máximo 3 parágrafos e nunca substitui o inteiro teor, que fica sempre acessível ao lado.
7. `reasoning` registra como a IA chegou ao prazo — é o que permite ao advogado conferir em segundos.
8. Sugestão de tarefa usa o catálogo do escritório, casando o tipo de ato com a tarefa; sem correspondência, sugere "Analisar intimação".
9. Responsável sugerido segue as 4 rotas de 045.
10. Leitura automática, se ligada, analisa toda publicação nova em background; desligada, é sob demanda.
11. Correção humana é gravada em `human_correction` — é a base para medir a qualidade do modelo ao longo do tempo.
12. Análise custa tokens: um botão de "analisar todas" pede confirmação mostrando a estimativa de custo.
13. Reanálise substitui a anterior, preservando a correção humana no histórico.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | **prazo em dias úteis a partir do dia seguinte** (tabela) | ~0,3 s |
| unit | prazo cruzando feriado nacional | ~0,2 s |
| unit | prazo em dias corridos quando indicado | ~0,2 s |
| integração | análise gera resumo, tipo e prazo (fixture) | ~0,5 s |
| integração | **prazo não é aplicado sem revisão** | ~0,5 s |
| integração | revisão humana aplica na tarefa | ~0,4 s |
| integração | confiança < 0,8 não pré-preenche | ~0,3 s |
| integração | sem prazo identificado não sugere data | ~0,3 s |
| integração | sugestão de tarefa casa com o catálogo | ~0,4 s |
| integração | sem correspondência sugere "Analisar intimação" | ~0,3 s |
| integração | responsável segue as rotas de 045 | ~0,4 s |
| integração | leitura automática processa em background | ~0,4 s |
| integração | correção humana é gravada | ~0,3 s |
| integração | reanálise preserva o histórico | ~0,3 s |
| frontend | badge de confiança e raciocínio visível | ~0,4 s |

**Total:** ~5,2 s

> A tabela de casos do cálculo de prazo é obrigatória e deve incluir: prazo de 5, 15 e 30 dias
> úteis, publicação em sexta-feira, publicação em véspera de feriado prolongado e virada de ano.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Prazo nunca aplicado sem humano · Raciocínio sempre visível · Commit `feat(086): IA em intimações`
