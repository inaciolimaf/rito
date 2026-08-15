import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { TabBar } from "@/components/domain/TabBar";
import { AgilityPanel } from "@/features/reports/AgilityPanel";
import { ProductivityPanel } from "@/features/reports/ProductivityPanel";

type PanelTab = "agility" | "productivity";

const PANEL_TABS: { value: PanelTab; label: string }[] = [
  { value: "agility", label: "Agilidade" },
  { value: "productivity", label: "Produtividade" },
];

/** Painel superior de Relatórios (spec 071 §6) — Agilidade e Produtividade. Os
 * relatórios tabulares (spec 072) entram na mesma rota via `?report=`. */
export function ReportsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("panel");
  const tab: PanelTab = requestedTab === "productivity" ? "productivity" : "agility";

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
      {tab === "agility" ? <AgilityPanel /> : <ProductivityPanel />}
    </div>
  );
}
