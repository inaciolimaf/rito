import { EmptyState } from "@/components/domain/EmptyState";
import type { DelayedUserItem } from "@/features/reports/api";

export interface DelayedUsersCardProps {
  users: DelayedUserItem[];
  isLoading?: boolean;
}

/** Colaboradores com mais atraso (spec 071 §2). */
export function DelayedUsersCard({ users, isLoading }: DelayedUsersCardProps): JSX.Element {
  if (!isLoading && users.length === 0) {
    return (
      <EmptyState
        title="Ninguém com atraso"
        description="Nenhum colaborador concluiu tarefas fora do prazo até agora."
      />
    );
  }

  return (
    <section aria-label="Colaboradores com mais atraso" className="space-y-2">
      <h3 className="text-sm font-medium text-primary">Colaboradores com mais atraso</h3>
      <ul className="divide-y divide-default rounded border border-default">
        {users.map((user) => (
          <li key={user.user_id} className="flex items-center justify-between px-3 py-2 text-sm">
            <span className="text-primary">{user.user_name}</span>
            <span className="text-right text-xs text-muted">
              <span className="text-danger">{user.late_count} atrasada(s)</span>
              {" · média "}
              {user.avg_delay_days} dia(s)
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
