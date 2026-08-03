import * as React from "react";

import { applyMention, findMentionToken } from "@/features/comments/mentions";

export interface MentionOption {
  id: string;
  name: string;
}

export interface CommentEditorProps {
  /** Busca assíncrona do autocomplete de `@` (spec 035 §6) — injetada para o teste
   * não depender de rede. */
  onSearchMentions: (query: string) => Promise<MentionOption[]>;
  onSubmit: (body: string) => Promise<void>;
  initialValue?: string;
  submitLabel?: string;
  onCancel?: () => void;
}

/** Editor de comentário com autocomplete de `@menção` (spec 035 §6): digitar `@`
 * seguido de letras abre a lista; escolher insere `@Nome Completo` no texto — o
 * backend resolve o nome para id na gravação (regra 1). */
export function CommentEditor({
  onSearchMentions,
  onSubmit,
  initialValue = "",
  submitLabel = "Comentar",
  onCancel,
}: CommentEditorProps): JSX.Element {
  const [value, setValue] = React.useState(initialValue);
  const [options, setOptions] = React.useState<MentionOption[]>([]);
  const [token, setToken] = React.useState<{ start: number; query: string } | null>(null);
  const [submitting, setSubmitting] = React.useState(false);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  async function refreshSuggestions(text: string, cursor: number): Promise<void> {
    const active = findMentionToken(text, cursor);
    setToken(active && active.query.length > 0 ? active : null);
    if (active && active.query.length > 0) {
      setOptions(await onSearchMentions(active.query));
    } else {
      setOptions([]);
    }
  }

  function handleChange(event: React.ChangeEvent<HTMLTextAreaElement>): void {
    const text = event.target.value;
    setValue(text);
    void refreshSuggestions(text, event.target.selectionStart ?? text.length);
  }

  function pickOption(option: MentionOption): void {
    if (!token) {
      return;
    }
    const next = applyMention(value, token, option.name);
    setValue(next);
    setToken(null);
    setOptions([]);
    textareaRef.current?.focus();
  }

  async function handleSubmit(): Promise<void> {
    if (!value.trim() || submitting) {
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(value.trim());
      setValue("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative space-y-2">
      <textarea
        ref={textareaRef}
        aria-label="Comentário"
        rows={3}
        placeholder="Escreva um comentário… use @ para mencionar"
        value={value}
        onChange={handleChange}
        className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      />
      {options.length > 0 && (
        <ul
          role="listbox"
          aria-label="Sugestões de menção"
          className="absolute z-10 max-h-40 w-64 overflow-auto rounded border border-default bg-surface py-1 shadow-lg"
        >
          {options.map((option) => (
            <li key={option.id}>
              <button
                type="button"
                role="option"
                aria-selected="false"
                onClick={() => pickOption(option)}
                className="block w-full px-3 py-1 text-left text-sm text-primary hover:bg-surface-muted"
              >
                {option.name}
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!value.trim() || submitting}
          onClick={() => void handleSubmit()}
          className="rounded bg-accent px-3 py-1 text-sm text-accent-foreground hover:bg-accent/90 disabled:opacity-50"
        >
          {submitLabel}
        </button>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-default px-3 py-1 text-sm text-primary hover:bg-surface-muted"
          >
            Cancelar
          </button>
        )}
      </div>
    </div>
  );
}
