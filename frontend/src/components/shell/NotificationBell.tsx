import { Bell } from "lucide-react";
import * as React from "react";

import { EmptyState } from "@/components/domain/EmptyState";

/** Notificações reais ficam para a spec 069 — este é só o ponto de entrada na UI. */
export function NotificationBell(): JSX.Element {
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
        aria-label="Notificações"
        aria-haspopup="true"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
        className="rounded p-2 text-muted hover:bg-surface-muted hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <Bell className="h-4 w-4" />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full z-10 mt-1 w-72 rounded border border-default bg-surface shadow-lg">
          <EmptyState title="Nenhuma notificação por enquanto." />
        </div>
      )}
    </div>
  );
}
