import { ChevronLeft, ChevronRight } from "lucide-react";
import * as React from "react";
import { Link, useLocation } from "react-router-dom";

import { NAV_ITEMS } from "@/components/shell/navItems";
import { useAuth } from "@/providers/AuthProvider";
import { cn } from "@/lib/utils";

const COLLAPSED_STORAGE_KEY = "rito.sidebar-collapsed";

export interface SidebarProps {
  onNavigate?: () => void;
  onOpenPlaceholderModal: (label: string) => void;
}

export function Sidebar({ onNavigate, onOpenPlaceholderModal }: SidebarProps): JSX.Element {
  const { user } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = React.useState(
    () => localStorage.getItem(COLLAPSED_STORAGE_KEY) === "true",
  );

  function toggleCollapsed(): void {
    setCollapsed((current) => {
      const next = !current;
      localStorage.setItem(COLLAPSED_STORAGE_KEY, String(next));
      return next;
    });
  }

  const capabilities = user?.capabilities ?? [];
  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.capability || capabilities.includes(item.capability),
  );

  return (
    <nav
      aria-label="Navegação principal"
      className={cn(
        "flex h-full flex-col border-r border-default bg-surface transition-[width]",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <ul className="flex-1 space-y-1 overflow-y-auto p-2">
        {visibleItems.map((item) => {
          const Icon = item.icon;
          const isActive = item.path !== undefined && location.pathname.startsWith(item.path);

          return (
            <li key={item.label}>
              {item.path ? (
                <Link
                  to={item.path}
                  onClick={onNavigate}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded px-3 py-2 text-sm text-primary hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                    isActive && "bg-surface-muted font-medium",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {!collapsed && <span>{item.label}</span>}
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={() => onOpenPlaceholderModal(item.label)}
                  className="flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm text-primary hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {!collapsed && <span>{item.label}</span>}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      <button
        type="button"
        onClick={toggleCollapsed}
        aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
        className="flex items-center justify-center gap-2 border-t border-default p-3 text-muted hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
      </button>
    </nav>
  );
}
