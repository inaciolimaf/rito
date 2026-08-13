# 065 — Modelos: editor

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +8 s
**Depende de:** 064 · **Status:** ✅ concluída

---

## 1. Objetivo

A biblioteca (spec 064) cadastra o modelo, mas o conteúdo até aqui é um textarea cru.
Esta spec entrega o editor de verdade: formatação completa, tabela, imagem,
cabeçalho/rodapé/marca d'água do documento, com autosave — sem perder o que foi
digitado.

## 2. Escopo

- Editor rico (TipTap): negrito/itálico/sublinhado/tachado, títulos, alinhamentos,
  listas numeradas/marcadoras/checklist, cor de texto, tabela, imagem, citação, código,
  linha horizontal (usada como quebra de página), desfazer/refazer.
- Cabeçalho, rodapé e marca d'água — texto próprio do modelo, fora do corpo editável
  (não somem se o usuário der "selecionar tudo + apagar" no corpo).
- Autosave: grava sozinho ~2 s depois de parar de digitar, sem botão "Salvar".
- Tela dedicada de edição (`/library/:id`) — a lista (spec 064) só cria o registro
  (nome + tipo) e navega para cá.

## 3. Fora de escopo

- Localizar e substituir — precisa de uma extensão de busca dedicada; sem uso real
  ainda validado, fica para quando pedirem.
- Digitação por voz — Web Speech API é ortogonal ao editor (grava texto reconhecido
  como qualquer digitação); entra como spec própria se for pedida, não força esta.
- Indentação de parágrafo — não existe extensão pronta no TipTap 3 para isso; um nó
  customizado só para indentar é desproporcional ao valor aqui.
- Cabeçalho/rodapé **timbrado** com logo do escritório — a spec 011 já tem
  `Account.logo_key`; usar isso no cabeçalho é natural, mas puxar imagem por URL
  assinada dentro do editor de texto simples do cabeçalho é complexidade de mais
  para esta spec (o campo aceita texto rico via cabeçalho, o logo fica pra quando a
  geração de PDF, spec 067, também precisar dele).
- Variáveis de preenchimento (`{{cliente.nome}}` etc.) — spec 066.

## 4. Modelo de dados

```sql
ALTER TABLE templates ADD COLUMN header_content TEXT NOT NULL DEFAULT '';
ALTER TABLE templates ADD COLUMN footer_content TEXT NOT NULL DEFAULT '';
ALTER TABLE templates ADD COLUMN watermark_text TEXT;
```
`content`, `header_content`, `footer_content` continuam `TEXT` — guardam o HTML que o
TipTap gera (`editor.getHTML()`), não um formato próprio. Migration `065_template_editor.py`.

## 5. Contratos de API

Nenhuma rota nova. `PUT /api/v1/templates/{id}` (spec 064) ganha 3 campos opcionais no
corpo: `header_content`, `footer_content`, `watermark_text`. `GET`/`POST` devolvem os
mesmos 3 campos na resposta.

## 6. Front-end

**Componentes reutilizados:** nenhum de `components/domain` — o editor é uma peça de
UI própria, sem equivalente hoje.
**Componentes criados:** `TemplateEditorPage` (tela `/library/:id`), `TemplateEditor`
(o TipTap em si + toolbar), `useAutosave` (hook genérico: debounce + grava, reusável
por qualquer editor futuro que precise do mesmo padrão).
**Rotas:** `/library/:id` — chega pelo "Editar" da listagem (spec 064) ou logo após
criar um modelo novo.
**Estados:** carregando, salvando (indicador discreto), erro de salvamento (toast/texto,
não bloqueia a digitação).

## 7. Regras de negócio

1. O corpo do documento é o único campo dentro da área editável do TipTap; cabeçalho,
   rodapé e marca d'água são campos de texto separados, sempre visíveis fora do corpo.
2. Autosave dispara 2 s depois da última mudança (debounce) — nunca a cada tecla.
3. Autosave falho não perde o conteúdo local: o editor mantém o texto na tela e tenta
   de novo na próxima mudança; só mostra um aviso, nunca descarta o que foi digitado.
4. Documento salvo e reabre idêntico: o HTML persistido é o mesmo devolvido no próximo
   `GET`, char a char (aceite da spec).
5. Imagem inserida no corpo vira uma tag `<img>` com a URL informada pelo usuário
   (colar/URL) — upload de arquivo de imagem para o corpo é o mesmo caminho de anexo
   de documento (spec 063), fora do corpo do editor: por ora, só URL.
6. Linha horizontal é o marcador de quebra de página (regra explícita do levantamento:
   "inserir quebra de página") — sem um nó de página dedicado, o efeito real (quebrar a
   impressão) só chega na spec 067 (geração de PDF), que sabe interpretar o `<hr>`.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | `PUT` grava `header_content`/`footer_content`/`watermark_text` | `tests/integration/test_templates.py` | ~0,3 s |
| integração | conteúdo HTML complexo salva e reabre idêntico (regra 4) | idem | ~0,2 s |
| frontend | formata negrito/itálico e o HTML gerado reflete a marcação | `src/features/templates/TemplateEditor.test.tsx` | ~0,4 s |
| frontend | insere tabela e imagem via toolbar | idem | ~0,3 s |
| frontend | autosave dispara `PUT` só depois do debounce (regra 2) | idem | ~0,4 s |
| frontend | cabeçalho/rodapé/marca d'água editam campos separados do corpo | idem | ~0,3 s |

**Total estimado:** ~1,9 s
**Fixtures externas:** nenhuma.

## 9. Descobertas

- `npx tsc --noEmit -p .` (sem apontar pra `tsconfig.app.json`) não checa nada — o
  `tsconfig.json` raiz só tem `references`, sem `files`. O gate real é `npm run lint`
  (`tsc -b --noEmit`, o mesmo do Makefile) — rodar isso pegou 2 erros de tipo que o
  comando solto deixou passar (`DocumentBrowser.tsx`, da spec 063) e formatação do
  Prettier fora do padrão em 8 arquivos acumulados desde a spec 062. Corrigido aqui;
  daqui pra frente, verificar sempre com `npm run lint`, nunca com `tsc` solto.
- jsdom não implementa `Range.getClientRects`/`getBoundingClientRect` nem
  `document.elementFromPoint` — poliriu isso no `src/test/setup.ts` global (qualquer
  teste futuro com ProseMirror/ranges reais precisa disso).
- `@tiptap/extension-table` (pacote raiz) já exporta `Table`/`TableRow`/`TableCell`/
  `TableHeader` e um `TableKit` combinando os 4 — os pacotes `-table-row`/`-table-cell`/
  `-table-header` seriam redundantes, removidos antes de commitar.
- **Orçamento apertado:** o wall-clock da suíte cheia fechou em 294 s de um teto de
  300 s — 6 s de folga. As specs 066/067 (ainda nesta fase) precisam manter os testes
  novos enxutos; se o teto estourar, a spec de refatoração 070 (Documentos e Modelos)
  é o lugar certo pra otimizar de volta.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] `make test` verde e wall-clock < 300 s (294 s — apertado, ver Descobertas)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(065): modelos — editor`
