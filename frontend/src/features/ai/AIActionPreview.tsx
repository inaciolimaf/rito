import { Button } from "@/components/ui/button";
import type { ActionPreviewData } from "@/features/ai/actions";

const FIELD_LABELS: Record<string, string> = {
  name: "Nome",
  email: "E-mail",
  cellphone: "Celular",
  city: "Cidade",
  state: "UF",
  notes: "Observações",
  folder: "Pasta",
  county: "Comarca",
  stage: "Etapa",
  task_type: "Tipo de tarefa",
  scheduled_date: "Data",
  deadline_date: "Prazo fatal",
  amount: "Valor",
  due_date: "Vencimento",
  kind: "Tipo",
  completed: "Concluída",
  lawsuit_id: "Processo",
  workflow: "Workflow",
};

function label(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "sim" : "não";
  if (Array.isArray(value)) return value.map(String).join(", ");
  return String(value);
}

export interface AIActionPreviewProps {
  preview: ActionPreviewData;
  /** Ausentes quando o preview é histórico (auditoria), não uma decisão pendente. */
  onApprove?: () => Promise<unknown> | void;
  onReject?: () => Promise<unknown> | void;
  isDeciding?: boolean;
}

/** O que a IA quer gravar, campo a campo (spec 084, regra 2).
 *
 * Verde para o que nasce, âmbar para o que muda — e o valor anterior riscado ao lado,
 * porque "mudou de quê para quê" é a pergunta que alguém faz antes de aprovar. */
export function AIActionPreview({
  preview,
  onApprove,
  onReject,
  isDeciding = false,
}: AIActionPreviewProps): JSX.Element {
  const entries = Object.entries(preview.changes ?? {});
  return (
    <section
      data-testid="ai-action-preview"
      aria-label="Prévia da ação da IA"
      className="space-y-3 rounded border border-default bg-surface p-4"
    >
      <div>
        <h3 className="font-medium text-primary">{preview.summary ?? "Ação proposta"}</h3>
        <p className="text-sm text-muted">
          Nada foi gravado ainda. Confira campo a campo antes de confirmar.
        </p>
      </div>

      <dl className="space-y-1">
        {entries.map(([field, change]) => {
          const isNew = change.before === undefined;
          return (
            <div
              key={field}
              data-testid={`change-${field}`}
              data-kind={isNew ? "created" : "updated"}
              className={
                isNew
                  ? "flex flex-wrap items-baseline gap-2 rounded bg-success/10 px-2 py-1 text-sm"
                  : "flex flex-wrap items-baseline gap-2 rounded bg-warning/10 px-2 py-1 text-sm"
              }
            >
              <dt className="text-muted">{label(field)}</dt>
              {!isNew && (
                <dd className="text-muted line-through">{display(change.before)}</dd>
              )}
              <dd className="font-medium text-primary">{display(change.after)}</dd>
            </div>
          );
        })}
        {entries.length === 0 && (
          <p className="text-sm text-muted">Sem alterações de campo nesta ação.</p>
        )}
      </dl>

      {(onApprove || onReject) && (
        <div className="flex justify-end gap-2">
          {onReject && (
            <Button type="button" variant="ghost" disabled={isDeciding} onClick={onReject}>
              Recusar
            </Button>
          )}
          {onApprove && (
            <Button type="button" disabled={isDeciding} onClick={onApprove}>
              Confirmar
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
