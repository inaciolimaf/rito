# 088 — IA no editor

**Fase:** 8 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 087 · **Status:** ✅ concluída

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

- **Aqui o streaming por token passou a ser real.** A 085 tinha deixado registrado que
  token a token esbarrava no tool calling dentro do nó do grafo; continuar, reescrever e
  ajustar o tom **não usam ferramenta**, então essas três passam direto pelo
  `provider.stream()` da 081 via um `AiRunner.stream()` novo. Sem fallback de propósito:
  refazer em outro modelo uma resposta que a pessoa já está lendo contradiria o que está
  na tela. O uso continua sendo registrado (regra 6 da 081), com os tokens de saída
  estimados por caractere — o protocolo nem sempre manda o número no fim, e estimar é
  mais honesto que gravar zero.
- **Um evento terminal, não dois.** O `done` que vem do provider é engolido pelo service,
  que emite o seu próprio com o id da ação — é com ele que o editor manda o feedback
  (regra 10). Custou um teste vermelho: o cliente pegava o primeiro `done`, que não tinha
  id nenhum.
- **A regra 1 mora numa `chain()`.** Inserir a sugestão numa cadeia única faz o TipTap
  agrupar tudo numa transação, e é isso que faz um Ctrl+Z desfazer a sugestão inteira.
  Uma sugestão de cinco parágrafos desfeita em cinco cliques seria uma armadilha — o
  teste usa o `Editor` de verdade, com o mesmo StarterKit da produção, e desfaz.
- **A revisão devolve sempre os cinco eixos**, mesmo os que o modelo não avaliou (viram
  `nao_avaliado`). Uma revisão com quatro itens parece completa e não é — e a pessoa não
  tem como saber que faltou olhar a fundamentação.
- **`document_changed: false` é campo da resposta**, não comentário: a regra 6 diz que a
  revisão não altera o documento, e o cliente não deveria precisar confiar na descrição
  da rota para saber disso. O teste confere o conteúdo no banco depois da revisão.
- **A fundamentação reusa o guarda-corpo da 087** (`strip_unsupported_citations`), sem
  copiar: a tentação de inventar súmula é a mesma no editor e no agente, e duas
  implementações da mesma proteção divergiriam na primeira correção.
- **O `EditorAiAssistant` é um componente separado do `TemplateEditor`** e devolve
  `null` quando não há IA configurada (regra 11) — o editor continua sendo exatamente o
  mesmo da 065 para quem não usa IA, sem nenhum caminho novo.
- **`getAccessToken()` foi exposto no client de API** porque o streaming é POST e não
  passa pelo `apiRequest`: `EventSource` só faz GET, e a seleção precisa ir no corpo.
  É o único consumidor.

## 10. Definição de pronto

- [x] Checklist padrão
- [x] Tudo reversível em um Ctrl+Z — teste com o editor real, não com mock
- [x] Revisão não altera texto — conferido no banco, e sinalizado na resposta
- [x] Commit `feat(088): IA no editor`
