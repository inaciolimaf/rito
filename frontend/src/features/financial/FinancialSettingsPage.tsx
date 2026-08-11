import { useSearchParams } from "react-router-dom";

import { CostCentersListPage } from "@/features/financial/CostCentersListPage";
import { DreGroupsListPage } from "@/features/financial/DreGroupsListPage";
import { FinancialCategoriesListPage } from "@/features/financial/FinancialCategoriesListPage";
import { cn } from "@/lib/utils";

type Tab = "categories" | "cost-centers" | "dre-groups";

const TABS: { value: Tab; label: string }[] = [
  { value: "categories", label: "Categorias" },
  { value: "cost-centers", label: "Centros de custo" },
  { value: "dre-groups", label: "Grupos DRE" },
];

/** 3 abas na mesma tela (spec 054 §6, rota `/settings/financial`) — mesmo padrão de
 * `/settings/users?tab=squads` (spec 013). */
export function FinancialSettingsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab");
  const tab: Tab =
    requested === "cost-centers" || requested === "dre-groups" ? requested : "categories";

  return (
    <div>
      <div
        role="tablist"
        aria-label="Seções do Financeiro"
        className="flex gap-1 border-b border-default px-6 pt-4"
      >
        {TABS.map((item) => (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={tab === item.value}
            className={cn(
              "rounded-t px-3 py-2 text-sm font-medium",
              tab === item.value
                ? "border-b-2 border-accent text-primary"
                : "text-muted hover:text-primary",
            )}
            onClick={() => setSearchParams(item.value === "categories" ? {} : { tab: item.value })}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "categories" && <FinancialCategoriesListPage />}
      {tab === "cost-centers" && <CostCentersListPage />}
      {tab === "dre-groups" && <DreGroupsListPage />}
    </div>
  );
}
