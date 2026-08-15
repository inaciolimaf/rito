import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { EmptyState } from "@/components/domain/EmptyState";
import { exportTimesheet, getTimesheet } from "@/features/reports/api";
import { TimesheetCell } from "@/features/reports/TimesheetCell";
import { useAuth } from "@/providers/AuthProvider";

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** Livro de ponto (spec 073 §6) — grade de dias do mês com jornada aparente
 * (primeiro/último acesso) e desvio contra `work_start` do usuário. */
export function TimesheetReport(): JSX.Element {
  const { user } = useAuth();
  const [month] = React.useState(currentMonth());
  const isAdmin = user?.role === "ADMINISTRADOR" || user?.role === "GESTOR";

  const { data, isLoading, error } = useQuery({
    queryKey: ["timesheet", month],
    queryFn: () => getTimesheet({ month }),
  });

  const [exporting, setExporting] = React.useState(false);

  async function handleExport(): Promise<void> {
    setExporting(true);
    try {
      await exportTimesheet({ month });
    } finally {
      setExporting(false);
    }
  }

  if (error) {
    return (
      <EmptyState
        title="Não foi possível carregar o livro de ponto"
        description="Tente novamente em instantes."
      />
    );
  }

  return (
    <div className="space-y-4">
      {isAdmin && (
        <div className="flex justify-end">
          <button
            type="button"
            disabled={exporting}
            className="rounded border border-default px-3 py-1.5 text-sm text-primary hover:bg-surface-muted disabled:opacity-50"
            onClick={handleExport}
          >
            Exportar
          </button>
        </div>
      )}

      {isLoading && <p className="text-sm text-muted">Carregando...</p>}

      {data && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
          {data.days.map((day) => (
            <TimesheetCell key={day.day} day={day} />
          ))}
        </div>
      )}
    </div>
  );
}
