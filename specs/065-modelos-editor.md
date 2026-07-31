# 065 — Modelos: editor

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +8 s
**Depende de:** 064 · **Status:** ⬜ pendente

---

## 1. Objetivo

Editor de texto rico com o que uma peça jurídica exige: cabeçalho e rodapé timbrados, marca
d'água, tabelas, numeração e formatação completa. É a spec mais pesada de frontend do projeto.

## 2. Escopo

- Editor TipTap com barra de ferramentas completa
- Cabeçalho, rodapé e marca d'água configuráveis
- Tabelas, imagens, listas, quebra de página
- Autosave com indicador
- Localizar e substituir
- Desfazer e refazer
- Atalhos de teclado

## 3. Fora de escopo

- Variáveis → 066 · PDF → 067 · IA no editor → 088
- Digitação por voz (fora do escopo)
- Edição colaborativa em tempo real (fora do escopo)

## 4. Modelo de dados

```sql
CREATE TABLE template_autosaves (
  template_id UUID PRIMARY KEY REFERENCES document_templates(id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  content JSONB NOT NULL,
  saved_by UUID NOT NULL REFERENCES users(id),
  saved_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
RLS ligado. Migration `065_template_autosaves.py`.

Autosave em tabela separada para não poluir o histórico do modelo com salvamentos parciais.

## 5. Contratos de API

| Método | Rota |
|---|---|
| PUT | `/api/v1/templates/{id}/content` — salvamento explícito |
| PUT | `/api/v1/templates/{id}/autosave` — rascunho |
| GET | `/api/v1/templates/{id}/autosave` |
| DELETE | `/api/v1/templates/{id}/autosave` — descartar rascunho |
| POST | `/api/v1/templates/{id}/images` — imagem inline |

## 6. Front-end

**Reutiliza:** `ConfirmDialog`, `FileDropzone`
**Cria:** `DocumentEditor` (TipTap), `EditorToolbar`, `HeaderFooterEditor`,
`WatermarkSettings`, `FindReplaceDialog`, `PageBreakNode`, `AutosaveIndicator`
**Rota:** `/library/:id/edit`

**Barra de ferramentas:** desfazer/refazer · localizar e substituir · fonte, tamanho, cor ·
negrito, itálico, sublinhado, tachado · alinhamentos · listas numerada, marcadores, checklist ·
indentação · tabela · imagem · quebra de página · cabeçalho, rodapé, marca d'água

## 7. Regras de negócio

1. Conteúdo em JSON do TipTap. HTML é só saída de renderização, nunca formato de armazenamento.
2. Autosave a cada **10 segundos** de inatividade, quando há alteração; indicador mostra "salvando", "salvo às HH:MM" ou "erro".
3. Ao abrir com rascunho mais novo que o salvo, o usuário escolhe entre recuperar ou descartar.
4. Salvamento explícito descarta o rascunho e regenera `content_text`.
5. Cabeçalho e rodapé são documentos TipTap próprios, com suporte a numeração de página (resolvida em 067).
6. Marca d'água aceita texto ou imagem, com opacidade e rotação.
7. Imagem inline sobe pelo `FileStorage` e é referenciada por URL assinada de longa duração.
8. Quebra de página é um nó do documento, respeitado na geração do PDF.
9. Tabela suporta mesclar células, cabeçalho e redimensionamento de coluna.
10. Sair com alteração não salva dispara o dirty guard.
11. Atalhos: Ctrl+B/I/U, Ctrl+Z/Y, Ctrl+F, Ctrl+S (salva explicitamente).
12. Documento acima de 5 MB de JSON avisa sobre desempenho.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| frontend | formatação básica aplica e desfaz | ~0,6 s |
| frontend | tabela: inserir, mesclar, redimensionar | ~0,6 s |
| frontend | quebra de página vira nó no documento | ~0,3 s |
| frontend | localizar e substituir, com "substituir tudo" | ~0,5 s |
| frontend | autosave dispara após inatividade | ~0,5 s |
| frontend | indicador reflete os 3 estados | ~0,3 s |
| frontend | dirty guard ao sair | ~0,3 s |
| frontend | atalhos de teclado | ~0,4 s |
| integração | salvar regenera `content_text` | ~0,3 s |
| integração | rascunho mais novo oferece recuperação | ~0,4 s |
| integração | salvamento explícito descarta rascunho | ~0,3 s |
| integração | upload de imagem inline | ~0,4 s |
| integração | RLS no autosave | ~0,3 s |
| e2e | **jornada 10/25:** criar modelo → formatar → salvar → reabrir | ~5 s |

**Total:** ~10,2 s

> Acima do orçamento. Se o wall-clock apertar, mova a jornada e2e para integração —
> a 070 vai cobrar.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Documento reabre idêntico ao salvo · Commit `feat(065): modelos — editor`
