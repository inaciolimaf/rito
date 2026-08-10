import type { TermSyncRunData } from "@/features/monitored-terms/api";

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("pt-BR");
}

/** Histórico de execuções do termo (spec 043 §6) — tabela simples dentro do modal
 * de histórico; a paginação keyset da API entra quando o volume justificar. */
export function SyncRunsTable({ runs }: { runs: TermSyncRunData[] }): JSX.Element {
  if (runs.length === 0) {
    return <p className="text-sm text-muted">Nenhuma sincronização executada ainda.</p>;
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-default text-left text-muted">
          <th className="py-1 pr-2 font-medium">Início</th>
          <th className="py-1 pr-2 font-medium">Fim</th>
          <th className="py-1 pr-2 font-medium">Encontradas</th>
          <th className="py-1 pr-2 font-medium">Novas</th>
          <th className="py-1 font-medium">Erro</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <tr key={run.id} className="border-b border-default last:border-0">
            <td className="py-1 pr-2">{formatDateTime(run.started_at)}</td>
            <td className="py-1 pr-2">{formatDateTime(run.finished_at)}</td>
            <td className="py-1 pr-2">{run.found_count}</td>
            <td className="py-1 pr-2">{run.new_count}</td>
            <td className="py-1 text-danger">{run.error ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
