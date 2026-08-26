import { useQuery } from "@tanstack/react-query";
import type { Editor } from "@tiptap/react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { listFeatureConfig } from "@/features/ai/api";
import { AiSuggestionOverlay } from "@/features/templates/AiSuggestionOverlay";
import {
  insertAiSuggestion,
  replaceSelectionWithAi,
  selectedText,
} from "@/features/templates/aiInsert";
import { ReviewChecklistPanel } from "@/features/templates/ReviewChecklistPanel";
import { SelectionToolbar } from "@/features/templates/SelectionToolbar";
import { SlashCommandMenu, type SlashCommand } from "@/features/templates/SlashCommandMenu";
import {
  reviewDocument,
  sendEditorFeedback,
  streamEditorAction,
  suggestGrounding,
  type EditorTone,
  type ReviewItem,
} from "@/features/templates/editorAi";

export interface EditorAiAssistantProps {
  editor: Editor;
  templateId?: string;
  lawsuitId?: string;
}

type Pending = { kind: "continue" | "rewrite" | "tone" | "ground"; selection: string } | null;

/** A camada de IA do editor (spec 088): `/` abre os comandos, a seleção abre a barra, e
 * o que a IA escreve fica em cinza até alguém apertar Tab.
 *
 * O estado vive aqui, e não dentro do `TemplateEditor`, para que o editor continue
 * funcionando exatamente igual quando não há IA configurada (regra 11). */
export function EditorAiAssistant({
  editor,
  templateId,
  lawsuitId,
}: EditorAiAssistantProps): JSX.Element | null {
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [suggestion, setSuggestion] = React.useState("");
  const [streaming, setStreaming] = React.useState(false);
  const [pending, setPending] = React.useState<Pending>(null);
  const [actionId, setActionId] = React.useState<string | null>(null);
  const [instruction, setInstruction] = React.useState("");
  const [review, setReview] = React.useState<ReviewItem[] | null>(null);
  const [selectionLength, setSelectionLength] = React.useState(0);
  const [error, setError] = React.useState<string | null>(null);

  const { data: config } = useQuery({
    queryKey: ["ai-feature-config"],
    queryFn: listFeatureConfig,
  });
  const feature = config?.items.find((item) => item.feature_key === "editor_assist");
  const aiAvailable = (config?.is_configured ?? false) && (feature?.is_enabled ?? false);

  React.useEffect(() => {
    function onSelection(): void {
      setSelectionLength(selectedText(editor).length);
    }
    editor.on("selectionUpdate", onSelection);
    return () => {
      editor.off("selectionUpdate", onSelection);
    };
  }, [editor]);

  React.useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (event.key === "/" && aiAvailable) setMenuOpen(true);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [aiAvailable]);

  async function run(
    path: "continue" | "rewrite" | "tone",
    body: Record<string, unknown>,
    kind: Pending extends null ? never : NonNullable<Pending>["kind"],
  ): Promise<void> {
    setSuggestion("");
    setError(null);
    setStreaming(true);
    setPending({ kind, selection: selectedText(editor) });
    await streamEditorAction(
      path,
      { ...body, template_id: templateId ?? null },
      {
        onChunk: (text) => setSuggestion((current) => current + text),
        onDone: (id) => {
          setActionId(id);
          setStreaming(false);
        },
        onError: (message) => {
          setError(message);
          setStreaming(false);
        },
      },
    );
  }

  function accept(): void {
    if (!suggestion) return;
    // Regra 1: uma transação só — Ctrl+Z desfaz a ação inteira.
    if (pending?.kind === "rewrite" || pending?.kind === "tone") {
      replaceSelectionWithAi(editor, suggestion);
    } else {
      insertAiSuggestion(editor, suggestion);
    }
    if (actionId) void sendEditorFeedback(actionId, true);
    reset();
  }

  function discard(): void {
    if (actionId) void sendEditorFeedback(actionId, false);
    reset();
  }

  function reset(): void {
    setSuggestion("");
    setPending(null);
    setActionId(null);
    setStreaming(false);
  }

  async function pick(command: SlashCommand): Promise<void> {
    setMenuOpen(false);
    if (command.id === "continue") {
      const before = editor.getHTML();
      await run("continue", { context_before: before }, "continue");
    }
    if (command.id === "review" && templateId) {
      const resultado = await reviewDocument(templateId, lawsuitId);
      setReview(resultado.items);
    }
    if (command.id === "ground" && lawsuitId) {
      const resultado = await suggestGrounding(selectedText(editor), lawsuitId, templateId);
      setSuggestion(resultado.output);
      setActionId(resultado.action_id);
      setPending({ kind: "ground", selection: selectedText(editor) });
    }
  }

  if (!aiAvailable) return null;

  return (
    <div className="space-y-2 border-t border-default p-3">
      <SlashCommandMenu
        open={menuOpen}
        aiAvailable={aiAvailable}
        onPick={(command) => void pick(command)}
        onClose={() => setMenuOpen(false)}
      />

      <SelectionToolbar
        selectionLength={selectionLength}
        aiAvailable={aiAvailable}
        isBusy={streaming}
        onRewrite={() =>
          void run(
            "rewrite",
            { selection: selectedText(editor), instruction: instruction || "melhore o trecho" },
            "rewrite",
          )
        }
        onTone={(tone: EditorTone) =>
          void run("tone", { selection: selectedText(editor), tone }, "tone")
        }
        onGround={() => void pick({ id: "ground", label: "", description: "" })}
      />

      {selectionLength > 0 && (
        <Input
          aria-label="Instrução para reescrever"
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          placeholder="Ex.: deixe mais direto, cite o artigo do CDC…"
        />
      )}

      <AiSuggestionOverlay
        suggestion={suggestion}
        isStreaming={streaming}
        onAccept={accept}
        onDiscard={discard}
      />

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {review && <ReviewChecklistPanel items={review} />}

      {review && (
        <Button type="button" size="sm" variant="ghost" onClick={() => setReview(null)}>
          Fechar revisão
        </Button>
      )}
    </div>
  );
}
