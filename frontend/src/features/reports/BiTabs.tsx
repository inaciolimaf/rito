import { useSearchParams } from "react-router-dom";

import { cn } from "@/lib/utils";

export type BiTab = "pipeline" | "vintage" | "time-fees" | "costs";

interface BiTabItem {
  value: BiTab;
  label: string;
  /** Abas de specs futuras ficam visíveis, mas desabilitadas. */
  enabled: boolean;
  upcomingSpec?: string;
}

const BI_TAB_ITEMS: readonly BiTabItem[] = [
  { value: "pipeline", label: "Estoque e Prospecção", enabled: true },
  { value: "vintage", label: "Safra e Qualidade", enabled: true },
  { value: "time-fees", label: "Tempo e Honorários", enabled: true },
  { value: "costs", label: "Custos", enabled: true },
];

/** Navegação entre as 4 abas de BI (spec 074 §6) por `tab=` na URL — mesma convenção
 * do `TabBar` de domínio, mas com abas futuras desabilitadas em vez de escondidas. */
export function BiTabs(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("tab");
  const active: BiTab =
    requested === "vintage" || requested === "time-fees" || requested === "costs"
      ? requested
      : "pipeline";

  function handleSelect(value: BiTab): void {
    const next = new URLSearchParams(searchParams);
    next.set("tab", value);
    setSearchParams(next, { replace: true });
  }

  return (
    <div role="tablist" aria-label="BI" className="flex gap-1 border-b border-default">
      {BI_TAB_ITEMS.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={active === item.value}
          disabled={!item.enabled}
          title={item.enabled ? undefined : `Disponível a partir da spec ${item.upcomingSpec}`}
          className={cn(
            "rounded-t px-3 py-2 text-sm font-medium",
            active === item.value
              ? "border-b-2 border-accent text-primary"
              : "text-muted hover:text-primary",
            !item.enabled && "cursor-not-allowed opacity-50 hover:text-muted",
          )}
          onClick={() => handleSelect(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
