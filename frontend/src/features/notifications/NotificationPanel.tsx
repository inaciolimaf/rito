import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/domain/EmptyState";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/features/notifications/api";

/** Painel do sino (spec 035 §6): as não lidas primeiro é trabalho do backend
 * (unread=true + ordenação desc); clicar marca como lida e navega pelo link. */
export function NotificationPanel(): JSX.Element {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => listNotifications(false),
  });

  const readMutation = useMutation({
    mutationFn: markNotificationRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const readAllMutation = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const items = data?.items ?? [];
  const unreadCount = items.filter((item) => item.read_at === null).length;

  if (items.length === 0) {
    return <EmptyState title="Nenhuma notificação por enquanto." />;
  }

  return (
    <div className="flex max-h-80 flex-col">
      <div className="flex items-center justify-between border-b border-default px-3 py-2">
        <span className="text-xs font-medium text-muted">
          {unreadCount > 0 ? `${unreadCount} não lida(s)` : "Tudo lido"}
        </span>
        {unreadCount > 0 && (
          <button
            type="button"
            onClick={() => readAllMutation.mutate()}
            className="text-xs text-accent underline"
          >
            Marcar todas como lidas
          </button>
        )}
      </div>
      <ul className="overflow-auto">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              to={item.link ?? "#"}
              onClick={() => {
                if (item.read_at === null) {
                  readMutation.mutate(item.id);
                }
              }}
              className={`block border-b border-default px-3 py-2 hover:bg-surface-muted ${
                item.read_at === null ? "bg-accent/5" : ""
              }`}
            >
              <p className="text-sm font-medium text-primary">{item.title}</p>
              {item.body && <p className="truncate text-xs text-muted">{item.body}</p>}
              <p className="text-xs text-muted">
                {new Date(item.created_at).toLocaleDateString("pt-BR")}
              </p>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
