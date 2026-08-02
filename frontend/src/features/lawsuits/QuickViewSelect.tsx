import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { Label } from "@/components/ui/label";

export const LAWSUIT_VIEWS: { value: string; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "active", label: "Ativos" },
  { value: "moved_30d", label: "Movimentados (30 dias)" },
  { value: "moved_7d", label: "Movimentados (7 dias)" },
  { value: "moved_today", label: "Movimentados hoje" },
  { value: "never_captured", label: "Nunca capturados" },
  { value: "idle_30d", label: "Parados +30 dias" },
  { value: "idle_45d", label: "Parados +45 dias" },
  { value: "idle_90d", label: "Parados +90 dias" },
  { value: "closed_this_month", label: "Fechados no mês" },
  { value: "filed_this_month", label: "Distribuídos no mês" },
  { value: "archived_this_month", label: "Arquivados no mês" },
];

const SELECT_CLASS =
  "h-10 rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

/** As 12 visões rápidas (spec 027 §6) — a visão vive na URL como qualquer outro filtro
 * (regra 9), combinável com o resto (regra 1). */
export function QuickViewSelect(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const view = searchParams.get("view") ?? "all";

  function handleChange(event: React.ChangeEvent<HTMLSelectElement>): void {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (event.target.value === "all") {
          next.delete("view");
        } else {
          next.set("view", event.target.value);
        }
        return next;
      },
      { replace: true },
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Label htmlFor="quick-view">Visão</Label>
      <select id="quick-view" className={SELECT_CLASS} value={view} onChange={handleChange}>
        {LAWSUIT_VIEWS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
