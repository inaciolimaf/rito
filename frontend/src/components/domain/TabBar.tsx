import { cn } from "@/lib/utils";

export interface TabBarItem<T extends string> {
  value: T;
  label: string;
}

export interface TabBarProps<T extends string> {
  items: readonly TabBarItem<T>[];
  active: T;
  ariaLabel: string;
  onSelect: (value: T) => void;
  className?: string;
}

/** Barra de abas por `tab=` na URL (refatoração 070, regra dos 3 usos) — extraída de
 * 6 telas que repetiam o mesmo `role="tablist"`: Usuários, Financeiro (lançamentos e
 * configurações), processo, relatório financeiro e Meu Painel. Cada tela continua
 * dona da própria lógica de `useSearchParams` — o componente só sabe renderizar e
 * avisar qual aba foi escolhida. */
export function TabBar<T extends string>({
  items,
  active,
  ariaLabel,
  onSelect,
  className,
}: TabBarProps<T>): JSX.Element {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn("flex gap-1 border-b border-default", className)}
    >
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={active === item.value}
          className={cn(
            "rounded-t px-3 py-2 text-sm font-medium",
            active === item.value
              ? "border-b-2 border-accent text-primary"
              : "text-muted hover:text-primary",
          )}
          onClick={() => onSelect(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
