import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import * as React from "react";

import { NotificationPanel } from "@/features/notifications/NotificationPanel";
import { listNotifications } from "@/features/notifications/api";

/** Sino de notificações do header (spec 035 §6): o badge conta as não lidas; o painel
 * abre com a lista in-app (os canais — e-mail/SMS/WhatsApp — são da 069). */
export function NotificationBell(): JSX.Element {
  const [isOpen, setIsOpen] = React.useState(false);
  const containerRef = React.useRef<HTMLDivElement>(null);

  // Só o total de não lidas, para o badge — a lista completa carrega ao abrir.
  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => listNotifications(true),
  });
  const unreadCount = unread?.total ?? 0;

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
        aria-label={unreadCount > 0 ? `Notificações (${unreadCount} não lidas)` : "Notificações"}
        aria-haspopup="true"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((current) => !current)}
        className="relative rounded p-2 text-muted hover:bg-surface-muted hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-medium text-danger-foreground">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full z-10 mt-1 w-80 rounded border border-default bg-surface shadow-lg">
          <NotificationPanel />
        </div>
      )}
    </div>
  );
}
