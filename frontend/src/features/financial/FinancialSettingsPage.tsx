import { useSearchParams } from "react-router-dom";

import { TabBar } from "@/components/domain/TabBar";
import { BankAccountsListPage } from "@/features/financial/BankAccountsListPage";
import { CostCentersListPage } from "@/features/financial/CostCentersListPage";
import { DreGroupsListPage } from "@/features/financial/DreGroupsListPage";
import { FinancialCategoriesListPage } from "@/features/financial/FinancialCategoriesListPage";

type Tab = "categories" | "accounts" | "cost-centers" | "dre-groups";

const TABS: { value: Tab; label: string }[] = [
  { value: "categories", label: "Categorias" },
  { value: "accounts", label: "Contas e cartões" },
  { value: "cost-centers", label: "Centros de custo" },
  { value: "dre-groups", label: "Grupos DRE" },
];

const TAB_VALUES: Tab[] = ["accounts", "cost-centers", "dre-groups"];

/** 4 abas na mesma tela (spec 054 §6 + spec 055 §6, rota `/settings/financial`) —
 * mesmo padrão de `/settings/users?tab=squads` (spec 013). */
export function FinancialSettingsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab");
  const tab: Tab = TAB_VALUES.includes(requested as Tab) ? (requested as Tab) : "categories";

  return (
    <div>
      <TabBar
        items={TABS}
        active={tab}
        ariaLabel="Seções do Financeiro"
        className="px-6 pt-4"
        onSelect={(value) => setSearchParams(value === "categories" ? {} : { tab: value })}
      />

      {tab === "categories" && <FinancialCategoriesListPage />}
      {tab === "accounts" && <BankAccountsListPage />}
      {tab === "cost-centers" && <CostCentersListPage />}
      {tab === "dre-groups" && <DreGroupsListPage />}
    </div>
  );
}
