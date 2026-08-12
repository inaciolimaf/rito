import * as React from "react";

import { Label } from "@/components/ui/label";

const VARIABLES: { token: string; label: string }[] = [
  { token: "{{customer_name}}", label: "Cliente" },
  { token: "{{amount}}", label: "Valor" },
  { token: "{{due_date}}", label: "Vencimento" },
  { token: "{{days_overdue}}", label: "Dias de atraso" },
  { token: "{{process_number}}", label: "Processo" },
  { token: "{{tenant_name}}", label: "Escritório" },
];

export interface TemplateEditorProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
}

/** Textarea de modelo de cobrança com inserção de variáveis (spec 061, regra 7) — as 6
 * variáveis que `render_template` (backend) sabe resolver; desconhecida passa direto. */
export function TemplateEditor({ id, value, onChange, error }: TemplateEditorProps): JSX.Element {
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  function insertVariable(token: string): void {
    const textarea = textareaRef.current;
    if (!textarea) {
      onChange(`${value}${token}`);
      return;
    }
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const next = `${value.slice(0, start)}${token}${value.slice(end)}`;
    onChange(next);
    requestAnimationFrame(() => {
      textarea.focus();
      const cursor = start + token.length;
      textarea.setSelectionRange(cursor, cursor);
    });
  }

  return (
    <div className="space-y-1">
      <Label htmlFor={id}>Modelo da mensagem</Label>
      <div className="flex flex-wrap gap-1.5">
        {VARIABLES.map((variable) => (
          <button
            key={variable.token}
            type="button"
            className="rounded border border-default bg-surface px-2 py-1 text-xs text-muted hover:text-primary"
            onClick={() => insertVariable(variable.token)}
          >
            + {variable.label}
          </button>
        ))}
      </div>
      <textarea
        id={id}
        ref={textareaRef}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={4}
        className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      />
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}
