# 088 — IA no editor

**Fase:** 8 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 087 · **Status:** ⬜ pendente

---

## 1. Objetivo

Assistência de escrita dentro do editor: continuar o texto, reescrever um trecho, ajustar o tom
e revisar a peça com checklist. Tudo com desfazer.

## 2. Escopo

- Continuar escrevendo a partir do cursor
- Reescrever seleção com instrução livre
- Ajustar tom: formal, objetivo, mais técnico
- Revisar peça com checklist estruturado
- Sugerir fundamentação com base no contexto do processo
- Menu de comando por `/`

## 3. Fora de escopo

- Geração de peça inteira → 087 · Correção ortográfica (é do navegador)

## 4. Modelo de dados

```sql
CREATE TABLE editor_ai_actions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  template_id UUID REFERENCES document_templates(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id),
  action TEXT NOT NULL,               -- 'continue' | 'rewrite' | 'tone' | 'review' | 'ground'
  instruction TEXT,
  input_excerpt TEXT NOT NULL,
  output TEXT NOT NULL,
  accepted BOOLEAN,
  model TEXT NOT NULL,
  tokens_used INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_editor_ai_template ON editor_ai_actions (template_id, created_at DESC);
```
RLS ligado. Migration `088_editor_ai.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/ai/editor/continue` → `{template_id, context_before, lawsuit_id?}` |
| POST | `/api/v1/ai/editor/rewrite` → `{selection, instruction, lawsuit_id?}` |
| POST | `/api/v1/ai/editor/tone` → `{selection, tone}` |
| POST | `/api/v1/ai/editor/review` → `{template_id, lawsuit_id?}` |
| POST | `/api/v1/ai/editor/ground` → `{selection, lawsuit_id}` |
| POST | `/api/v1/ai/editor/actions/{id}/feedback` → `{accepted}` |

Todos com streaming.

## 6. Front-end

**Reutiliza:** `DocumentEditor`, `ConfirmDialog`
**Cria:** `SlashCommandMenu` (`/` abre o menu de comandos de IA),
`SelectionToolbar` (aparece ao selecionar texto), `AiSuggestionOverlay`
(texto sugerido em cinza, Tab aceita, Esc descarta), `ReviewChecklistPanel`,
`ToneSelect`
**Rota:** dentro de `/library/:id/edit`

## 7. Regras de negócio

1. Toda ação é **reversível**: o resultado entra como uma transação única no histórico do editor, desfeita com um Ctrl+Z.
2. Continuação aparece como texto fantasma; Tab aceita, Esc descarta. Nada é inserido sem gesto.
3. Reescrita substitui **só a seleção**, preservando a formatação em volta.
4. Tons disponíveis: formal, objetivo, mais técnico, mais simples.
5. Revisão devolve checklist estruturado: estrutura da peça, fundamentação, pedidos, coerência de datas e valores, linguagem. Cada item com status e observação.
6. A revisão **não altera o documento** — só aponta. Correção é sempre ação do usuário.
7. "Sugerir fundamentação" usa o contexto do processo via tool calling; **não inventa citação**, mesma regra de 087.
8. Contexto enviado é limitado: 2.000 caracteres antes do cursor e 500 depois, para controlar custo.
9. Seleção acima de 5.000 caracteres → pede para reduzir.
10. Aceitar ou recusar alimenta `accepted` — métrica de qualidade da feature.
11. Sem chave de IA, o menu `/` não mostra comandos de IA e a barra de seleção não aparece.
12. Todas as ações respeitam o modelo configurado para a feature `editor_assist`.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | continuar gera a partir do contexto (fixture) | ~0,4 s |
| integração | reescrita substitui só a seleção | ~0,4 s |
| integração | os 4 tons produzem saída distinta | ~0,4 s |
| integração | revisão devolve checklist estruturado | ~0,4 s |
| integração | **revisão não altera o documento** | ~0,3 s |
| integração | fundamentação não inventa citação | ~0,4 s |
| integração | contexto respeita o limite de caracteres | ~0,3 s |
| integração | seleção acima de 5.000 → 422 | ~0,2 s |
| integração | feedback grava `accepted` | ~0,2 s |
| integração | sem chave, comandos somem | ~0,3 s |
| frontend | `/` abre o menu de comandos | ~0,4 s |
| frontend | Tab aceita, Esc descarta o fantasma | ~0,5 s |
| frontend | **Ctrl+Z desfaz a ação inteira de uma vez** | ~0,4 s |
| frontend | barra de seleção aparece ao selecionar | ~0,3 s |

**Total:** ~4,9 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Tudo reversível em um Ctrl+Z · Revisão não altera texto · Commit `feat(088): IA no editor`
