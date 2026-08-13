import { useSearchParams } from "react-router-dom";

import { TabBar } from "@/components/domain/TabBar";
import { SquadsListPage } from "@/features/squads/SquadsListPage";
import { UsersListPage } from "@/features/users/UsersListPage";

type Tab = "collaborators" | "squads";

const TABS: { value: Tab; label: string }[] = [
  { value: "collaborators", label: "Colaboradores" },
  { value: "squads", label: "Times" },
];

/** ADVBOX: "Abas Colaboradores e Times" na mesma tela de Usuários (spec 013, seção 6:
 * rota `/settings/users?tab=squads`, não uma rota separada). */
export function UsersSettingsPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: Tab = searchParams.get("tab") === "squads" ? "squads" : "collaborators";

  return (
    <div>
      <TabBar
        items={TABS}
        active={tab}
        ariaLabel="Seções de Usuários"
        className="px-6 pt-4"
        onSelect={(value) => setSearchParams(value === "collaborators" ? {} : { tab: value })}
      />

      {tab === "collaborators" ? <UsersListPage /> : <SquadsListPage />}
    </div>
  );
}
