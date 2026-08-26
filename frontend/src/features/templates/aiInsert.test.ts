import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { describe, expect, it } from "vitest";

import {
  insertAiSuggestion,
  replaceSelectionWithAi,
  selectedText,
} from "@/features/templates/aiInsert";

function makeEditor(content: string): Editor {
  // StarterKit é o mesmo conjunto do editor de produção (spec 065) — inclusive o
  // histórico, que é o que este teste exercita.
  return new Editor({ extensions: [StarterKit], content });
}

describe("inserção de texto da IA", () => {
  it("Ctrl+Z desfaz a sugestão inteira de uma vez (spec 088, regra 1)", () => {
    const editor = makeEditor("<p>Dos fatos.</p>");
    const original = editor.getHTML();

    insertAiSuggestion(
      editor,
      "<p>Primeiro parágrafo.</p><p>Segundo parágrafo.</p><p>Terceiro.</p>",
    );
    expect(editor.getHTML()).toContain("Terceiro");

    editor.commands.undo();

    // Um único desfazer devolve o documento ao estado anterior — não sobra parágrafo.
    expect(editor.getHTML()).toBe(original);
    editor.destroy();
  });

  it("reescrita substitui só a seleção, preservando o resto (regra 3)", () => {
    const editor = makeEditor("<p>Antes</p><p>trecho velho</p><p>Depois</p>");
    // Seleciona exatamente o parágrafo do meio.
    const posicao = editor.getHTML().indexOf("trecho velho");
    expect(posicao).toBeGreaterThan(-1);
    editor.commands.setTextSelection({ from: 9, to: 21 });

    replaceSelectionWithAi(editor, "trecho novo");

    const html = editor.getHTML();
    expect(html).toContain("Antes");
    expect(html).toContain("Depois");
    expect(html).toContain("trecho novo");
    expect(html).not.toContain("trecho velho");
    editor.destroy();
  });

  it("a seleção vira o texto que vai para a IA", () => {
    const editor = makeEditor("<p>um dois três</p>");
    editor.commands.setTextSelection({ from: 1, to: 8 });

    expect(selectedText(editor)).toBe("um dois");
    editor.destroy();
  });
});
