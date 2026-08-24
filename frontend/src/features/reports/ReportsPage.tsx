import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { TabBar } from "@/components/domain/TabBar";
import { AgilityPanel } from "@/features/reports/AgilityPanel";
import { BiTabs } from "@/features/reports/BiTabs";
import { PipelinePanel } from "@/features/reports/PipelinePanel";
import { ProductivityPanel } from "@/features/reports/ProductivityPanel";
import { ReportPage } from "@/features/reports/ReportPage";
import { TimeFeesPanel } from "@/features/reports/TimeFeesPanel";
import { VintagePanel } from "@/features/reports/VintagePanel";

type PanelTab = "agility" | "productivity" | "tabular" | "bi";

const PANEL_TABS: { value: PanelTab; label: string }[] = [
  { value: "agility", label: "Agilidade" },
  { value: "productivity", label: "Produtividade" },
  { value: "tabular", label: "Relatórios" },
  { value: "bi", label: "BI" },
];

const BI_TAB_VALUES = ["pipeline", "vintage", "time-fees", "custos"];

/** Painel superior de Relatórios (spec 071 §6: Agilidade/Produtividade) + os 9
 * relatórios tabulares (spec 072 §6, aba "Relatórios", `?report=` seleciona qual) + a
 * seção de BI (spec 074 §6, rota `/reports?tab=pipeline` — o `tab=` com valor de BI
 * seleciona o painel "BI" e o `BiTabs` cuida da navegação entre as 4 abas). Um link
 * direto com `?report=` já abre na aba tabular, sem precisar de `?panel=`. */
export function ReportsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("panel");
  const requestedBiTab = searchParams.get("tab");
  const hasReportParam = searchParams.has("report");
  const tab: PanelTab =
    requestedBiTab !== null && BI_TAB_VALUES.includes(requestedBiTab)
      ? "bi"
      : requestedTab === "productivity" || requestedTab === "tabular"
        ? requestedTab
        : requestedTab === "agility"
          ? "agility"
          : hasReportParam
            ? "tabular"
            : "agility";

  const handleSelect = React.useCallback(
    (value: PanelTab) => {
      const next = new URLSearchParams(searchParams);
      next.delete("panel");
      next.delete("tab");
      if (value === "bi") next.set("tab", "pipeline");
      else if (value !== "agility") next.set("panel", value);
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
      {tab === "bi" && (
        <div className="space-y-4">
          <BiTabs />
          {requestedBiTab === "vintage" ? (
            <VintagePanel />
          ) : requestedBiTab === "time-fees" ? (
            <TimeFeesPanel />
          ) : requestedBiTab === "custos" ? (
            <p className="text-sm text-muted">Esta aba de BI ainda não está disponível.</p>
          ) : (
            <PipelinePanel />
          )}
        </div>
      )}
    </div>
  );
}
