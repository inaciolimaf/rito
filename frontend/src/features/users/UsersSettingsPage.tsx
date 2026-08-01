import { useSearchParams } from "react-router-dom";

import { SquadsListPage } from "@/features/squads/SquadsListPage";
import { UsersListPage } from "@/features/users/UsersListPage";
import { cn } from "@/lib/utils";

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
      <div
        role="tablist"
        aria-label="Seções de Usuários"
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
            onClick={() =>
              setSearchParams(item.value === "collaborators" ? {} : { tab: item.value })
            }
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "collaborators" ? <UsersListPage /> : <SquadsListPage />}
    </div>
  );
}
