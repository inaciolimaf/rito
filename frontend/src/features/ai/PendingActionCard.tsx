import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { PendingActionData } from "@/features/ai/threads";

export interface PendingActionCardProps {
  action: PendingActionData;
  onDecide: (approved: boolean, humanInput?: Record<string, unknown>) => Promise<unknown>;
}

/** O agente propôs algo e parou (spec 082, regra 2). Nada acontece sem que alguém
 * clique — e recusar encerra a conversa, não a empurra para outra tentativa. */
export function PendingActionCard({ action, onDecide }: PendingActionCardProps): JSX.Element {
  const [reason, setReason] = React.useState("");
  const [deciding, setDeciding] = React.useState(false);

  async function decide(approved: boolean): Promise<void> {
    setDeciding(true);
    try {
      await onDecide(approved, approved ? {} : { reason: reason || "Recusado pelo usuário." });
    } finally {
      setDeciding(false);
    }
  }

  return (
    <section
      data-testid="pending-action"
      aria-label="Ação aguardando confirmação"
      className="space-y-3 rounded border border-warning bg-warning/10 p-4"
    >
      <div>
        <h3 className="font-medium text-primary">{action.title}</h3>
        {action.description && <p className="text-sm text-muted">{action.description}</p>}
      </div>

      <dl className="grid gap-1 text-sm">
        {Object.entries(action.preview).map(([key, value]) => (
          <div key={key} className="flex gap-2">
            <dt className="text-muted">{key}</dt>
            <dd className="text-primary">{String(value)}</dd>
          </div>
        ))}
      </dl>

      <div className="space-y-1">
        <Label htmlFor="pending-action-reason">Motivo (se recusar)</Label>
        <Input
          id="pending-action-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" disabled={deciding} onClick={() => decide(false)}>
          Recusar
        </Button>
        <Button type="button" disabled={deciding} onClick={() => decide(true)}>
          Confirmar
        </Button>
      </div>
    </section>
  );
}
