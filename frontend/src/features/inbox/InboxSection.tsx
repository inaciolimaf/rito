import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/domain/EmptyState";
import {
  INBOX_SECTION_LABELS,
  listInbox,
  type InboxRow,
  type InboxSectionKey,
} from "@/features/inbox/api";

export interface InboxSectionProps {
  section: InboxSectionKey;
  count: number;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  selectedIds: Set<string>;
  onToggleRow: (postId: string) => void;
}

function formatDate(iso: string | null): string {
  if (!iso) {
    return "—";
  }
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

function InboxRowLine({
  row,
  selected,
  onToggle,
}: {
  row: InboxRow;
  selected: boolean;
  onToggle: () => void;
}): JSX.Element {
  return (
    <tr className={row.is_read ? "text-muted" : "font-medium text-primary"}>
      <td className="px-2 py-1.5">
        <input
          type="checkbox"
          aria-label={`Selecionar ${row.task_type_name}`}
          checked={selected}
          onChange={onToggle}
        />
      </td>
      <td className="px-2 py-1.5 text-center">{row.is_starred ? "★" : ""}</td>
      <td className="px-2 py-1.5 text-center">
        {row.is_urgent ? "!" : row.is_important ? "!!" : ""}
      </td>
      <td className="px-2 py-1.5 text-center">{row.is_private ? "●" : ""}</td>
      <td className="px-2 py-1.5">
        <Link to={`/posts/${row.post_id}`} className="text-accent underline">
          {row.task_type_name}
        </Link>
      </td>
      <td className="px-2 py-1.5">{row.parties.slice(0, 2).join(", ")}</td>
      <td className="px-2 py-1.5">{formatDate(row.scheduled_date)}</td>
      <td className="px-2 py-1.5">{formatDate(row.deadline_date)}</td>
      <td className="px-2 py-1.5">{row.assignee_names.join(", ")}</td>
    </tr>
  );
}

/** Uma seção da caixa de entrada (spec 036 §6): cabeçalho colapsável com contador
 * (o colapso persiste por usuário — regra 9) e a tabela de tarefas da seção. */
export function InboxSection({
  section,
  count,
  collapsed,
  onToggleCollapsed,
  selectedIds,
  onToggleRow,
}: InboxSectionProps): JSX.Element {
  const { data, isLoading } = useQuery({
    queryKey: ["inbox", section],
    queryFn: () => listInbox(section),
    enabled: !collapsed,
  });

  const items = data?.items ?? [];

  return (
    <section className="rounded border border-default bg-surface">
      <button
        type="button"
        aria-expanded={!collapsed}
        onClick={onToggleCollapsed}
        className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-surface-muted"
      >
        <span className="text-sm font-semibold text-primary">{INBOX_SECTION_LABELS[section]}</span>
        <span className="rounded-full bg-surface-muted px-2 text-xs text-muted">
          {count} {collapsed ? "▸" : "▾"}
        </span>
      </button>
      {!collapsed && (
        <div className="border-t border-default">
          {isLoading && <p className="p-3 text-sm text-muted">Carregando…</p>}
          {!isLoading && items.length === 0 && <EmptyState title="Nenhuma tarefa aqui." />}
          {items.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="px-2 py-1" aria-label="Selecionar" />
                  <th className="px-2 py-1" aria-label="Favorita" />
                  <th className="px-2 py-1" aria-label="Prioridade" />
                  <th className="px-2 py-1" aria-label="Privada" />
                  <th className="px-2 py-1">Tarefa</th>
                  <th className="px-2 py-1">Partes</th>
                  <th className="px-2 py-1">Data</th>
                  <th className="px-2 py-1">Prazo fatal</th>
                  <th className="px-2 py-1">Responsáveis</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <InboxRowLine
                    key={row.post_id}
                    row={row}
                    selected={selectedIds.has(row.post_id)}
                    onToggle={() => onToggleRow(row.post_id)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}
