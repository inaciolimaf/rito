import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { StatCard } from "@/components/domain/StatCard";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import {
  exportFinancialReport,
  getFinancialReport,
  listBankAccounts,
  type FinancialReportGroupRow,
} from "@/features/financial/api";
import { ApiError } from "@/lib/errors";
import { formatBrl } from "@/lib/money";
import { cn } from "@/lib/utils";

type ReportTab = "dre" | "dfc";

const REPORT_TABS: { value: ReportTab; label: string }[] = [
  { value: "dre", label: "DRE" },
  { value: "dfc", label: "DFC" },
];

function todayIsoMonthStart(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

const REPORT_COLUMNS: DataTableColumn<FinancialReportGroupRow>[] = [
  { id: "dre_group_name", header: "Grupo DRE", cell: (row) => row.dre_group_name },
  { id: "receita", header: "Receita", cell: (row) => formatBrl(row.receita) },
  { id: "despesa", header: "Despesa", cell: (row) => formatBrl(row.despesa) },
  { id: "total", header: "Total", cell: (row) => formatBrl(row.total) },
];

/** DRE e DFC (spec 062) — mesma tela alterna entre os dois relatórios; o regime de
 * data (competência × pagamento) é decidido pelo backend por trás de cada rota, o
 * front só troca qual rota chama (regra 1/2). */
export function FinancialReportPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("report");
  const reportTab: ReportTab = requestedTab === "dfc" ? "dfc" : "dre";

  const { data: accountsPage } = useQuery({
    queryKey: ["bank-accounts", "for-financial-report"],
    queryFn: () => listBankAccounts({ status: "active" }),
  });

  const filterFields: FilterFieldDef[] = React.useMemo(
    () => [
      { key: "from", label: "De", type: "date" },
      { key: "to", label: "Até", type: "date" },
      {
        key: "account_id",
        label: "Conta",
        type: "select",
        options: (accountsPage?.items ?? []).map((account) => ({
          value: account.id,
          label: account.name,
        })),
      },
    ],
    [accountsPage],
  );

  const { values } = useFilters(filterFields);
  const from = typeof values.from === "string" ? values.from : todayIsoMonthStart();
  const to = typeof values.to === "string" ? values.to : todayIso();
  const accountId = typeof values.account_id === "string" ? values.account_id : undefined;

  const { data, isLoading, error } = useQuery({
    queryKey: ["financial-report", reportTab, { from, to, accountId }],
    queryFn: () => getFinancialReport(reportTab, { from, to, account_id: accountId }),
  });

  const [exporting, setExporting] = React.useState(false);

  async function handleExport(format: "xlsx" | "pdf"): Promise<void> {
    setExporting(true);
    try {
      await exportFinancialReport(reportTab, format, { from, to, account_id: accountId });
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
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

      <div role="tablist" aria-label="Relatório" className="flex gap-1 border-b border-default">
        {REPORT_TABS.map((item) => (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={reportTab === item.value}
            className={cn(
              "rounded-t px-3 py-2 text-sm font-medium",
              reportTab === item.value
                ? "border-b-2 border-accent text-primary"
                : "text-muted hover:text-primary",
            )}
            onClick={() => {
              const next = new URLSearchParams(searchParams);
              if (item.value === "dre") next.delete("report");
              else next.set("report", item.value);
              setSearchParams(next, { replace: true });
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      <FilterBar fields={filterFields} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <StatCard label="Receita" value={formatBrl(data?.total_receita ?? 0)} isLoading={isLoading} />
        <StatCard label="Despesa" value={formatBrl(data?.total_despesa ?? 0)} isLoading={isLoading} />
        <StatCard
          label="Resultado"
          value={formatBrl(data?.resultado ?? 0)}
          isLoading={isLoading}
          negative={(data?.resultado ?? 0) < 0}
        />
      </div>

      <DataTable
        columns={REPORT_COLUMNS}
        data={data?.rows ?? []}
        getRowId={(row) => String(row.dre_group_id)}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum lançamento no período."
      />
    </div>
  );
}
