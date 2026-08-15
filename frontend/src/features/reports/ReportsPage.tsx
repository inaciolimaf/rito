import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { TabBar } from "@/components/domain/TabBar";
import { AgilityPanel } from "@/features/reports/AgilityPanel";
import { ProductivityPanel } from "@/features/reports/ProductivityPanel";
import { ReportPage } from "@/features/reports/ReportPage";

type PanelTab = "agility" | "productivity" | "tabular";

const PANEL_TABS: { value: PanelTab; label: string }[] = [
  { value: "agility", label: "Agilidade" },
  { value: "productivity", label: "Produtividade" },
  { value: "tabular", label: "Relatórios" },
];

/** Painel superior de Relatórios (spec 071 §6: Agilidade/Produtividade) + os 9
 * relatórios tabulares (spec 072 §6, aba "Relatórios", `?report=` seleciona qual). Um
 * link direto com `?report=` já abre na aba tabular, sem precisar de `?panel=`. */
export function ReportsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("panel");
  const hasReportParam = searchParams.has("report");
  const tab: PanelTab =
    requestedTab === "productivity" || requestedTab === "tabular"
      ? requestedTab
      : requestedTab === "agility"
        ? "agility"
        : hasReportParam
          ? "tabular"
          : "agility";

  const handleSelect = React.useCallback(
    (value: PanelTab) => {
      const next = new URLSearchParams(searchParams);
      if (value === "agility") next.delete("panel");
      else next.set("panel", value);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  return (
    <div className="space-y-4">
      <TabBar items={PANEL_TABS} active={tab} ariaLabel="Painel" onSelect={handleSelect} />
      {tab === "agility" && <AgilityPanel />}
      {tab === "productivity" && <ProductivityPanel />}
      {tab === "tabular" && <ReportPage />}
    </div>
  );
}
