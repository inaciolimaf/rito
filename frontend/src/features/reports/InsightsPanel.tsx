import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { EmptyState } from "@/components/domain/EmptyState";
import { Button } from "@/components/ui/button";
import { AskMetricsBox } from "@/features/reports/AskMetricsBox";
import { InsightCard } from "@/features/reports/InsightCard";
import { dismissInsight, listInsights, refreshInsights } from "@/features/reports/insights";

/** Aba de insights (spec 089 §7): o que perguntar e o que o sistema já percebeu. */
export function InsightsPanel(): JSX.Element {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["ai-insights"], queryFn: listInsights });

  const invalidate = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: ["ai-insights"] }).then(() => undefined);

  const dismiss = useMutation({ mutationFn: dismissInsight, onSuccess: invalidate });
  const refresh = useMutation({ mutationFn: refreshInsights, onSuccess: invalidate });

  const items = data?.items ?? [];
  return (
    <div className="space-y-4">
      <AskMetricsBox />

      <section className="space-y-2" aria-label="Avisos do sistema">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-primary">O que merece atenção</h3>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
          >
            Atualizar agora
          </Button>
        </div>

        {isLoading ? (
          <div className="h-24 animate-pulse rounded bg-surface-muted" />
        ) : items.length === 0 ? (
          <EmptyState
            title="Nada pedindo atenção agora"
            description="Prazos, processos parados e inadimplência aparecem aqui quando surgirem."
          />
        ) : (
          <div className="grid gap-2 md:grid-cols-2">
            {items.map((insight) => (
              <InsightCard
                key={insight.id}
                insight={insight}
                onDismiss={(id) => dismiss.mutate(id)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
