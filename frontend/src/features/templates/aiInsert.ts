import type { Editor } from "@tiptap/react";

/** Insere a sugestão da IA no ponto do cursor (spec 088, regras 1 e 2).
 *
 * Tudo numa `chain()` só de propósito: o TipTap agrupa a cadeia numa transação única, e
 * é isso que faz um Ctrl+Z desfazer a inserção inteira em vez de tirar um parágrafo por
 * vez. Uma sugestão de cinco parágrafos desfeita em cinco cliques seria uma armadilha. */
export function insertAiSuggestion(editor: Editor, html: string): void {
  editor.chain().focus().insertContent(html).run();
}

/** Substitui APENAS a seleção (regra 3): a formatação em volta continua onde estava,
 * e a troca também é uma transação só. */
export function replaceSelectionWithAi(editor: Editor, html: string): void {
  const { from, to } = editor.state.selection;
  editor.chain().focus().insertContentAt({ from, to }, html).run();
}

/** O que está selecionado, em texto puro — é o que vai para a IA e o que a barra de
 * seleção usa para decidir se aparece. */
export function selectedText(editor: Editor): string {
  const { from, to } = editor.state.selection;
  return editor.state.doc.textBetween(from, to, " ");
}
