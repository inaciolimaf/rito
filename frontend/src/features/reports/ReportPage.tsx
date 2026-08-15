import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { DataTable } from "@/components/domain/DataTable";
import { EmptyState } from "@/components/domain/EmptyState";
import { FilterBar } from "@/components/domain/FilterBar";
import { useFilters } from "@/components/domain/useFilters";
import { exportTabularReport, getTabularReport, type ReportKey } from "@/features/reports/api";
import { ReportSelect } from "@/features/reports/ReportSelect";
import {
  REPORT_OPTIONS,
  filterFieldsFor,
  REPORT_DEFINITIONS,
} from "@/features/reports/reportDefinitions";
import { ReportTotalsRow } from "@/features/reports/ReportTotalsRow";
import { TimesheetReport } from "@/features/reports/TimesheetReport";
import { ApiError } from "@/lib/errors";

const DEFAULT_REPORT: ReportKey = "productivity";

// Spec 073 §6: "Livro de ponto" entra no mesmo seletor, mas não é um dos 9 report_key
// tabulares da 072 — tem tela própria (grade de dias, não DataTable genérica).
const PAGE_OPTIONS = [...REPORT_OPTIONS, { value: "timesheet", label: "Livro de ponto" }];

/** Página genérica dos 9 relatórios tabulares (spec 072 regra 1) + livro de ponto
 * (spec 073) — dirigida por metadados (`reportDefinitions.tsx`), não telas à mão. */
export function ReportPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedKey = searchParams.get("report");
  const isTimesheet = requestedKey === "timesheet";
  const reportKey: ReportKey =
    requestedKey && requestedKey in REPORT_DEFINITIONS
      ? (requestedKey as ReportKey)
      : DEFAULT_REPORT;
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
    enabled: !isTimesheet,
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

  function handleReportChange(next: string): void {
    const params = new URLSearchParams(searchParams);
    if (next === DEFAULT_REPORT) params.delete("report");
    else params.set("report", next);
    setSearchParams(params, { replace: true });
  }

  if (isTimesheet) {
    return (
      <div className="space-y-4">
        <ReportSelect value="timesheet" options={PAGE_OPTIONS} onChange={handleReportChange} />
        <TimesheetReport />
      </div>
    );
  }

  if (data?.disabled_reason) {
    return (
      <div className="space-y-4">
        <ReportSelect value={reportKey} options={PAGE_OPTIONS} onChange={handleReportChange} />
        <EmptyState title={definition.label} description={data.disabled_reason} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <ReportSelect value={reportKey} options={PAGE_OPTIONS} onChange={handleReportChange} />
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
