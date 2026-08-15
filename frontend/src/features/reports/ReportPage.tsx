import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { DataTable } from "@/components/domain/DataTable";
import { EmptyState } from "@/components/domain/EmptyState";
import { FilterBar } from "@/components/domain/FilterBar";
import { useFilters } from "@/components/domain/useFilters";
import { exportTabularReport, getTabularReport, type ReportKey } from "@/features/reports/api";
import { ReportSelect } from "@/features/reports/ReportSelect";
import { filterFieldsFor, REPORT_DEFINITIONS } from "@/features/reports/reportDefinitions";
import { ReportTotalsRow } from "@/features/reports/ReportTotalsRow";
import { ApiError } from "@/lib/errors";

const DEFAULT_REPORT: ReportKey = "productivity";

/** Página genérica dos 9 relatórios tabulares (spec 072 regra 1) — uma tela dirigida
 * por metadados (`reportDefinitions.tsx`), não 9 telas escritas à mão. */
export function ReportPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedKey = searchParams.get("report") as ReportKey | null;
  const reportKey: ReportKey =
    requestedKey && requestedKey in REPORT_DEFINITIONS ? requestedKey : DEFAULT_REPORT;
  const definition = REPORT_DEFINITIONS[reportKey];

  const filterFields = React.useMemo(() => filterFieldsFor(definition), [definition]);
  const { values } = useFilters(filterFields);
  const from = typeof values.from === "string" ? values.from : undefined;
  const to = typeof values.to === "string" ? values.to : undefined;

  const [cursorStack, setCursorStack] = React.useState<string[]>([]);
  const currentCursor = cursorStack[cursorStack.length - 1];

  React.useEffect(() => {
    setCursorStack([]);
  }, [reportKey, from, to]);

  const { data, isLoading, error } = useQuery({
    queryKey: ["tabular-report", reportKey, { from, to, cursor: currentCursor }],
    queryFn: () => getTabularReport(reportKey, { from, to, cursor: currentCursor }),
  });

  const [exporting, setExporting] = React.useState(false);

  async function handleExport(format: "xlsx" | "pdf"): Promise<void> {
    setExporting(true);
    try {
      await exportTabularReport(reportKey, format, { from, to });
    } finally {
      setExporting(false);
    }
  }

  function handleReportChange(next: ReportKey): void {
    const params = new URLSearchParams(searchParams);
    if (next === DEFAULT_REPORT) params.delete("report");
    else params.set("report", next);
    setSearchParams(params, { replace: true });
  }

  if (data?.disabled_reason) {
    return (
      <div className="space-y-4">
        <ReportSelect value={reportKey} onChange={handleReportChange} />
        <EmptyState title={definition.label} description={data.disabled_reason} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <ReportSelect value={reportKey} onChange={handleReportChange} />
        <div className="flex gap-2">
          <button
            type="button"
            disabled={exporting}
            className="rounded border border-default px-3 py-1.5 text-sm text-primary hover:bg-surface-muted disabled:opacity-50"
            onClick={() => handleExport("xlsx")}
          >
            Exportar xlsx
          </button>
          <button
            type="button"
            disabled={exporting}
            className="rounded border border-default px-3 py-1.5 text-sm text-primary hover:bg-surface-muted disabled:opacity-50"
            onClick={() => handleExport("pdf")}
          >
            Exportar pdf
          </button>
        </div>
      </div>

      <FilterBar fields={filterFields} />

      <div className="rounded border border-default">
        <DataTable
          columns={definition.columns}
          data={data?.items ?? []}
          getRowId={definition.rowId}
          isLoading={isLoading}
          error={error instanceof ApiError ? error.message : null}
          emptyMessage={definition.emptyMessage}
          pagination={{
            hasPreviousPage: cursorStack.length > 0,
            hasNextPage: data?.next_cursor != null,
            onPreviousPage: () => setCursorStack((stack) => stack.slice(0, -1)),
            onNextPage: () => {
              if (data?.next_cursor) {
                setCursorStack((stack) => [...stack, data.next_cursor as string]);
              }
            },
          }}
        />
        {definition.showPointsTotal && data && (
          <ReportTotalsRow pointsTotal={data.points_total ?? 0} />
        )}
      </div>
    </div>
  );
}
