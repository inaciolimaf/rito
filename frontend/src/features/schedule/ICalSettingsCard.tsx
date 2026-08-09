import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { enableIcal, getIcalStatus, icalFullUrl, regenerateIcal } from "@/features/schedule/api";

/** Cartão de sincronização com Google Agenda/Outlook (spec 037 §6): ativa o feed,
 * mostra a URL secreta para colar e regenera o token (regra 5: o anterior morre na
 * hora — por isso a confirmação). Sincronização unidirecional (regra 6). */
export function ICalSettingsCard(): JSX.Element {
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  const { data: status } = useQuery({ queryKey: ["ical-status"], queryFn: getIcalStatus });

  const invalidate = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: ["ical-status"] }).then(() => undefined);

  const enable = useMutation({ mutationFn: enableIcal, onSuccess: invalidate });
  const regenerate = useMutation({ mutationFn: regenerateIcal, onSuccess: invalidate });

  const fullUrl = status?.url ? icalFullUrl(status.url) : null;

  async function copyUrl(): Promise<void> {
    if (!fullUrl || !navigator.clipboard) return;
    await navigator.clipboard.writeText(fullUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <section
      data-testid="ical-settings-card"
      className="flex flex-col gap-2 rounded border border-default bg-surface p-3"
    >
      <h2 className="text-sm font-medium">Sincronizar com Google Agenda / Outlook</h2>
      <p className="text-xs text-muted">
        Assinatura somente leitura das suas tarefas marcadas com “Mostrar na agenda” (atualiza a
        cada hora; alterações feitas no calendário externo não voltam).
      </p>
      {status?.enabled && fullUrl ? (
        <div className="flex flex-wrap items-center gap-2">
          <code className="max-w-full flex-1 truncate rounded bg-surface-muted px-2 py-1 text-xs">
            {fullUrl}
          </code>
          <Button type="button" size="sm" variant="outline" onClick={() => void copyUrl()}>
            {copied ? "Copiado!" : "Copiar URL"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setConfirmOpen(true)}
            disabled={regenerate.isPending}
          >
            Regenerar link
          </Button>
        </div>
      ) : (
        <div>
          <Button
            type="button"
            size="sm"
            onClick={() => enable.mutate()}
            disabled={enable.isPending}
          >
            Ativar sincronização
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Regenerar link do calendário?"
        description="O link atual para de funcionar imediatamente. Você precisará assinar o novo link no Google Agenda ou Outlook."
        confirmLabel="Regenerar"
        onConfirm={() => regenerate.mutateAsync().then(() => undefined)}
      />
    </section>
  );
}
