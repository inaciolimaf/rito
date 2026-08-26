import { ChevronDown, Menu } from "lucide-react";
import * as React from "react";

import { ThemeToggle } from "@/components/ThemeToggle";
import { GlobalSearch } from "@/components/shell/GlobalSearch";
import { NotificationBell } from "@/components/shell/NotificationBell";
import { QuickAddMenu } from "@/components/shell/QuickAddMenu";
import { CopilotPanel } from "@/features/ai/CopilotPanel";
import { useAuth } from "@/providers/AuthProvider";

export interface HeaderProps {
  onToggleMobileSidebar: () => void;
  onNewTask: () => void;
}

function UserMenu(): JSX.Element {
  const { user, logout } = useAuth();
  const [isOpen, setIsOpen] = React.useState(false);
  const containerRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent): void {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
        className="flex items-center gap-1 rounded px-2 py-1 text-sm text-primary hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        {user?.name}
        <ChevronDown className="h-3 w-3" />
      </button>

      {isOpen && (
        <ul
          role="menu"
          className="absolute right-0 top-full z-10 mt-1 w-48 rounded border border-default bg-surface py-1 shadow-lg"
        >
          <li role="none">
            <button
              type="button"
              role="menuitem"
              onClick={() => void logout()}
              className="block w-full px-3 py-2 text-left text-sm text-primary hover:bg-surface-muted"
            >
              Sair
            </button>
          </li>
        </ul>
      )}
    </div>
  );
}

export function Header({ onToggleMobileSidebar, onNewTask }: HeaderProps): JSX.Element {
  return (
    <header className="flex items-center gap-3 border-b border-default bg-surface px-4 py-3">
      <button
        type="button"
        aria-label="Abrir menu de navegação"
        onClick={onToggleMobileSidebar}
        className="rounded p-2 text-muted hover:bg-surface-muted hover:text-primary md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      <GlobalSearch />

      <div className="ml-auto flex items-center gap-2">
        <QuickAddMenu onNewTask={onNewTask} />
        {/* Spec 085, regra 10: o painel some sozinho quando não há IA configurada. */}
        <CopilotPanel />
        <NotificationBell />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
