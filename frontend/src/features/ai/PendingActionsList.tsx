import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { EmptyState } from "@/components/domain/EmptyState";
import { AIActionPreview } from "@/features/ai/AIActionPreview";
import {
  approveAiAction,
  listAiActions,
  rejectAiAction,
  type AiActionData,
} from "@/features/ai/actions";

/** As ações que a IA propôs e ainda esperam decisão (spec 084 §7). Cada uma decide
 * sozinha: aprovar quatro coisas de uma vez é o mesmo que não ler nenhuma. */
export function PendingActionsList(): JSX.Element {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["ai-actions", "pending"],
    queryFn: () => listAiActions("pending"),
  });

  const invalidate = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: ["ai-actions"] }).then(() => undefined);

  const approve = useMutation({
    mutationFn: (action: AiActionData) => approveAiAction(action.id),
    onSuccess: invalidate,
  });
  const reject = useMutation({
    mutationFn: (action: AiActionData) => rejectAiAction(action.id),
    onSuccess: invalidate,
  });

  if (isLoading) {
    return <div className="h-24 animate-pulse rounded bg-surface-muted" />;
  }
  const items = data?.items ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        title="Nenhuma ação aguardando você"
        description="Quando a IA propuser uma alteração, ela aparece aqui antes de acontecer."
      />
    );
  }
  return (
    <div className="space-y-3">
      {items.map((action) => (
        <AIActionPreview
          key={action.id}
          preview={action.preview}
          isDeciding={approve.isPending || reject.isPending}
          onApprove={() => approve.mutateAsync(action)}
          onReject={() => reject.mutateAsync(action)}
        />
      ))}
    </div>
  );
}
