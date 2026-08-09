import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  DEFAULT_SECTION_ORDER,
  getInboxCounts,
  getInboxPreferences,
  putInboxPreferences,
  type InboxSectionKey,
} from "@/features/inbox/api";
import { BulkActionBar } from "@/features/inbox/BulkActionBar";
import { InboxSection } from "@/features/inbox/InboxSection";
import { InboxSettingsForm } from "@/features/inbox/InboxSettingsForm";
import { TaskscorePanel } from "@/features/taskscore/TaskscorePanel";
import { cn } from "@/lib/utils";

type HomeTab = "list" | "analytics";

const HOME_TABS: { value: HomeTab; label: string }[] = [
  { value: "list", label: "Lista" },
  { value: "analytics", label: "Desempenho" },
];

/** Caixa de entrada (spec 036 §6 — /home, aba Lista): as 6 seções na ordem do usuário
 * com contadores e colapso persistente (regras 8 e 9) e ações em massa (regra 6).
 * Aba Desempenho (spec 039 §6, /home?tab=analytics): painel Taskscore. */
export function InboxPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: HomeTab = searchParams.get("tab") === "analytics" ? "analytics" : "list";
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [settingsOpen, setSettingsOpen] = React.useState(false);

  const { data: counts } = useQuery({ queryKey: ["inbox-counts"], queryFn: getInboxCounts });
  const { data: preferences } = useQuery({
    queryKey: ["inbox-preferences"],
    queryFn: getInboxPreferences,
  });

  const savePreferences = useMutation({
    mutationFn: putInboxPreferences,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["inbox-preferences"] }),
  });

  const order = preferences?.section_order ?? DEFAULT_SECTION_ORDER;
  const collapsed = new Set(preferences?.collapsed_sections ?? []);

  async function invalidateInbox(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["inbox"] });
    await queryClient.invalidateQueries({ queryKey: ["inbox-counts"] });
  }

  function toggleRow(postId: string): void {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(postId)) {
        next.delete(postId);
      } else {
        next.add(postId);
      }
      return next;
    });
  }

  function toggleCollapsed(section: InboxSectionKey): void {
    const nextCollapsed = collapsed.has(section)
      ? [...collapsed].filter((item) => item !== section)
      : [...collapsed, section];
    // Regra 9: o colapso persiste por usuário junto com a ordem.
    savePreferences.mutate({ section_order: order, collapsed_sections: nextCollapsed });
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Meu Painel</h1>
        {tab === "list" && (
          <Button variant="outline" size="sm" onClick={() => setSettingsOpen((open) => !open)}>
            Configurar seções
          </Button>
        )}
      </div>

      <div
        role="tablist"
        aria-label="Seções do Meu Painel"
        className="flex gap-1 border-b border-default"
      >
        {HOME_TABS.map((item) => (
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
            onClick={() => setSearchParams(item.value === "list" ? {} : { tab: item.value })}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "analytics" ? (
        <TaskscorePanel />
      ) : (
        <>
          {settingsOpen && (
            <div className="rounded border border-default bg-surface p-4">
              <InboxSettingsForm
                initialOrder={order}
                onSave={async (nextOrder) => {
                  await savePreferences.mutateAsync({
                    section_order: nextOrder,
                    collapsed_sections: [...collapsed],
                  });
                  setSettingsOpen(false);
                }}
              />
            </div>
          )}

          <BulkActionBar
            selectedIds={[...selectedIds]}
            onClear={() => setSelectedIds(new Set())}
            onDone={() => void invalidateInbox()}
          />

          <div className="space-y-3">
            {order.map((section) => (
              <InboxSection
                key={section}
                section={section}
                count={counts?.[section] ?? 0}
                collapsed={collapsed.has(section)}
                onToggleCollapsed={() => toggleCollapsed(section)}
                selectedIds={selectedIds}
                onToggleRow={toggleRow}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
