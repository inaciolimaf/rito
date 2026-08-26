import Color from "@tiptap/extension-color";
import Image from "@tiptap/extension-image";
import { TableKit } from "@tiptap/extension-table";
import TaskItem from "@tiptap/extension-task-item";
import TaskList from "@tiptap/extension-task-list";
import TextAlign from "@tiptap/extension-text-align";
import { TextStyle } from "@tiptap/extension-text-style";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  Bold,
  Italic,
  List,
  ListChecks,
  ListOrdered,
  Minus,
  Quote,
  Redo,
  Strikethrough,
  Table as TableIcon,
  Underline as UnderlineIcon,
  Undo,
} from "lucide-react";
import * as React from "react";

import { VariablePicker } from "@/features/templates/VariablePicker";
import { cn } from "@/lib/utils";
import { EditorAiAssistant } from "@/features/templates/EditorAiAssistant";

const TEXT_COLORS = ["#111827", "#dc2626", "#2563eb", "#16a34a", "#ca8a04"];

function ToolbarButton({
  onClick,
  active,
  label,
  children,
}: {
  onClick: () => void;
  active?: boolean;
  label: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "rounded p-1.5 text-primary hover:bg-surface-muted",
        active && "bg-surface-muted text-accent",
      )}
    >
      {children}
    </button>
  );
}

function Toolbar({ editor }: { editor: Editor }): JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-default p-1">
      <ToolbarButton
        label="Negrito"
        active={editor.isActive("bold")}
        onClick={() => editor.chain().focus().toggleBold().run()}
      >
        <Bold className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        label="Itálico"
        active={editor.isActive("italic")}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      >
        <Italic className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        label="Sublinhado"
        active={editor.isActive("underline")}
        onClick={() => editor.chain().focus().toggleUnderline().run()}
      >
        <UnderlineIcon className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        label="Tachado"
        active={editor.isActive("strike")}
        onClick={() => editor.chain().focus().toggleStrike().run()}
      >
        <Strikethrough className="h-4 w-4" />
      </ToolbarButton>

      <select
        aria-label="Título"
        className="h-8 rounded border border-default bg-surface px-1 text-sm text-primary"
        value={
          editor.isActive("heading", { level: 1 })
            ? "h1"
            : editor.isActive("heading", { level: 2 })
              ? "h2"
              : editor.isActive("heading", { level: 3 })
                ? "h3"
                : "p"
        }
        onChange={(event) => {
          const value = event.target.value;
          if (value === "p") {
            editor.chain().focus().setParagraph().run();
          } else {
            const level = Number(value.replace("h", "")) as 1 | 2 | 3;
            editor.chain().focus().toggleHeading({ level }).run();
          }
        }}
      >
        <option value="p">Texto</option>
        <option value="h1">Título 1</option>
        <option value="h2">Título 2</option>
        <option value="h3">Título 3</option>
      </select>

      <select
        aria-label="Alinhamento"
        className="h-8 rounded border border-default bg-surface px-1 text-sm text-primary"
        value={
          (["left", "center", "right", "justify"] as const).find((align) =>
            editor.isActive({ textAlign: align }),
          ) ?? "left"
        }
        onChange={(event) => editor.chain().focus().setTextAlign(event.target.value).run()}
      >
        <option value="left">Esquerda</option>
        <option value="center">Centro</option>
        <option value="right">Direita</option>
        <option value="justify">Justificado</option>
      </select>

      <select
        aria-label="Cor do texto"
        className="h-8 rounded border border-default bg-surface px-1 text-sm text-primary"
        value=""
        onChange={(event) => {
          if (event.target.value) editor.chain().focus().setColor(event.target.value).run();
        }}
      >
        <option value="">Cor</option>
        {TEXT_COLORS.map((color) => (
          <option key={color} value={color} style={{ color }}>
            {color}
          </option>
        ))}
      </select>

      <ToolbarButton
        label="Lista com marcadores"
        active={editor.isActive("bulletList")}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      >
        <List className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        label="Lista numerada"
        active={editor.isActive("orderedList")}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      >
        <ListOrdered className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        label="Checklist"
        active={editor.isActive("taskList")}
        onClick={() => editor.chain().focus().toggleTaskList().run()}
      >
        <ListChecks className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        label="Citação"
        active={editor.isActive("blockquote")}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
      >
        <Quote className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarButton
        label="Inserir tabela"
        onClick={() =>
          editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
        }
      >
        <TableIcon className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        label="Inserir imagem"
        onClick={() => {
          const url = window.prompt("URL da imagem");
          if (url) editor.chain().focus().setImage({ src: url }).run();
        }}
      >
        <span className="text-xs font-medium">IMG</span>
      </ToolbarButton>
      <ToolbarButton
        label="Quebra de página"
        onClick={() => editor.chain().focus().setHorizontalRule().run()}
      >
        <Minus className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarButton label="Desfazer" onClick={() => editor.chain().focus().undo().run()}>
        <Undo className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton label="Refazer" onClick={() => editor.chain().focus().redo().run()}>
        <Redo className="h-4 w-4" />
      </ToolbarButton>

      <VariablePicker onInsert={(token) => editor.chain().focus().insertContent(token).run()} />
    </div>
  );
}

export interface TemplateEditorProps {
  content: string;
  onChange: (html: string) => void;
  /** Spec 088: id do modelo em edição e processo de contexto, quando houver. */
  templateId?: string;
  lawsuitId?: string;
}

/** Editor rico do corpo do modelo (spec 065) — cabeçalho/rodapé/marca d'água ficam
 * fora daqui (regra 1), são campos de texto próprios em `TemplateEditorPage`. */
export function TemplateEditor({
  content,
  onChange,
  templateId,
  lawsuitId,
}: TemplateEditorProps): JSX.Element | null {
  const editor = useEditor({
    extensions: [
      StarterKit,
      TextStyle,
      Color,
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      TableKit.configure({ table: { resizable: true } }),
      Image,
      TaskList,
      TaskItem.configure({ nested: true }),
    ],
    content,
    autofocus: "end",
    onUpdate: ({ editor: current }) => onChange(current.getHTML()),
    editorProps: {
      attributes: {
        class: "min-h-[300px] p-4 text-sm text-primary focus:outline-none",
      },
    },
  });

  if (!editor) return null;

  return (
    <div className="rounded border border-default bg-surface">
      <Toolbar editor={editor} />
      <EditorContent editor={editor} />
      {/* Spec 088: a assistência mora ao lado do texto, nunca por cima dele. */}
      <EditorAiAssistant editor={editor} templateId={templateId} lawsuitId={lawsuitId} />
    </div>
  );
}
