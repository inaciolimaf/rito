import * as React from "react";

import { bulkComplete, bulkRead, bulkStar } from "@/features/inbox/api";

export interface BulkActionBarProps {
  selectedIds: string[];
  onClear: () => void;
  /** Chamado depois da ação — a página invalida as queries da inbox. */
  onDone: () => void;
}

/** Barra de ações em massa (spec 036 §6): aparece só com seleção ativa; as ações
 * são transacionais no backend (regra 6 — falha parcial vira 409 com os ids). */
export function BulkActionBar({
  selectedIds,
  onClear,
  onDone,
}: BulkActionBarProps): JSX.Element | null {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  if (selectedIds.length === 0) {
    return null;
  }

  async function run(action: (ids: string[]) => Promise<void>): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await action(selectedIds);
      onClear();
      onDone();
    } catch {
      setError("Não foi possível concluir a ação em massa — nenhuma tarefa foi alterada.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="toolbar"
      aria-label="Ações em massa"
      className="flex items-center gap-3 rounded border border-default bg-surface-muted px-3 py-2"
    >
      <span className="text-sm font-medium text-primary">{selectedIds.length} selecionada(s)</span>
      <button
        type="button"
        disabled={busy}
        onClick={() => void run(bulkComplete)}
        className="text-sm text-accent underline disabled:opacity-50"
      >
        Concluir
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => void run((ids) => bulkRead(ids))}
        className="text-sm text-accent underline disabled:opacity-50"
      >
        Marcar lida
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={() => void run((ids) => bulkStar(ids))}
        className="text-sm text-accent underline disabled:opacity-50"
      >
        Favoritar
      </button>
      <button
        type="button"
        onClick={onClear}
        className="ml-auto text-sm text-muted hover:text-primary"
      >
        Limpar seleção
      </button>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
