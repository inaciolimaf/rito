import { Button } from "@/components/ui/button";

export interface SqlPreviewProps {
  sql: string;
  relations: string[];
  touchesFinancial: boolean;
  isRunning?: boolean;
  onRun: () => void;
  onCancel: () => void;
}

/** O SQL que a IA escreveu, antes de rodar (spec 089, regra 3).
 *
 * Mostrar a consulta não é transparência decorativa: é a única chance de alguém
 * perceber que a pergunta foi entendida errado ANTES de olhar para um número errado
 * com cara de verdade. */
export function SqlPreview({
  sql,
  relations,
  touchesFinancial,
  isRunning = false,
  onRun,
  onCancel,
}: SqlPreviewProps): JSX.Element {
  return (
    <section
      data-testid="sql-preview"
      aria-label="Consulta gerada pela IA"
      className="space-y-2 rounded border border-default bg-surface p-3"
    >
      <p className="text-sm text-primary">
        Esta é a consulta que será executada. Confira antes de rodar.
      </p>
      <pre
        data-testid="sql-text"
        className="overflow-x-auto rounded bg-surface-muted p-2 text-xs text-primary"
      >
        {sql}
      </pre>
      <p className="text-xs text-muted">
        Lendo de: {relations.join(", ")}
        {touchesFinancial && " · inclui dados financeiros"}
      </p>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" disabled={isRunning} onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="button" disabled={isRunning} onClick={onRun}>
          {isRunning ? "Consultando…" : "Rodar consulta"}
        </Button>
      </div>
    </section>
  );
}
